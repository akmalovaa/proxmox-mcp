import functools
import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, cast

import requests.exceptions as rex
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from proxmoxer.core import AuthenticationError, ResourceException
from pydantic import Field

from proxmox_mcp.client import AppContext
from proxmox_mcp.config import RiskLevel, get_redact_secrets
from proxmox_mcp.telemetry import report_exception

# Same three values as the operator's PROXMOX_RISK_LEVEL — aliased rather than
# restated so the two cannot drift apart.
Tier = RiskLevel

# RRD metric windows accepted by every Proxmox */rrddata endpoint.
Timeframe = Literal["hour", "day", "week", "month", "year"]
RrdCf = Literal["AVERAGE", "MAX"]

_TIER_ORDER = {"read": 0, "lifecycle": 1, "all": 2}

logger = logging.getLogger("proxmox_mcp.policy")

# MCP tool annotations — what the *client* is told a call does, so a host can decide
# whether to ask the user first. Deliberately separate from the `tier=` the same
# decorator takes: that is the operator's admission policy. A force-stop is
# destructive to the guest but still belongs to the lifecycle tier.
# open_world_hint=True for all — every tool talks to the external Proxmox API.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)
LIFECYCLE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
# Non-idempotent and lossy from the guest's point of view: a force-stop drops
# whatever was in flight, a rollback discards everything since the snapshot.
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)

# Config keys whose values must not reach the model, a log, or an HTTP client.
# `get_vm_config` returns a cloud-init password hash and the guest's SSH keys.
_SECRET_KEYS = frozenset({"cipassword", "password", "sshkeys", "ssh-public-keys"})
_REDACTED = "***redacted***"


@dataclass
class Policy:
    """Everything that decides whether a tool is registered at all.

    One snapshot shared by every ``register()``, so the risk gate and the operator
    allowlist are applied identically and the result can be reported back through
    ``get_server_info``.
    """

    risk_level: RiskLevel
    allow: frozenset[str] | None = None
    #: every tool that offered itself for registration, allowlisted or not
    seen: set[str] = field(default_factory=set)
    #: the subset that actually made it into the tool list
    registered: set[str] = field(default_factory=set)

    def unknown_allowlist_entries(self) -> set[str]:
        return set(self.allow or ()) - self.seen


def _check_annotations(tier: Tier, annotations: ToolAnnotations | None) -> None:
    """Reject the one tier/annotation pairing that would mislead a client.

    Everything else is left free on purpose — ``destructive_hint=True`` at the
    ``lifecycle`` tier is exactly the combination this split exists to allow.
    """
    if annotations is None:
        raise ValueError(
            "every tool must pass annotations=READ_ONLY | LIFECYCLE | DESTRUCTIVE"
        )
    if annotations.read_only_hint and tier != "read":
        raise ValueError(
            f"a tool annotated read_only_hint=True cannot require tier={tier!r}"
        )
    if tier != "read" and annotations.read_only_hint is not False:
        raise ValueError(
            f"a tool requiring tier={tier!r} must set read_only_hint=False — it is "
            f"the most reliable machine-readable warning a client gets"
        )


def _endpoint(kwargs: dict[str, Any]) -> str:
    """Best-effort ``host:port`` of the configured Proxmox, for error messages."""
    ctx = kwargs.get("ctx")
    if ctx is None:
        return "the configured Proxmox host"
    try:
        settings = _ctx(cast(Context, ctx)).settings
    except Exception:  # noqa: BLE001 - diagnostics must never mask the real error
        return "the configured Proxmox host"
    return f"{settings.host}:{settings.port}"


def _describe(exc: Exception, where: str) -> str:
    """Turn a Proxmoxer/requests failure into one actionable line for the model.

    Without this every failure reaches the client as a bare
    ``Error executing tool <name>``: the SDK withholds the text of anything that
    is not a ``ToolError`` (see ``mcp.server.mcpserver.exceptions``), so even the
    risk-level denial below would otherwise never be seen by the model.
    """
    if isinstance(exc, PermissionError):
        return str(exc)

    if isinstance(exc, ResourceException):
        code = exc.status_code
        detail = f"{code} {exc.status_message}: {exc.content}".strip()
        if code in (401, 403):
            return (
                f"Proxmox denied the request ({detail}). The API user or token lacks "
                f"the privileges this endpoint needs — check the role assigned to it "
                f"under Datacenter > Permissions, and that a privilege-separated "
                f"token has its own ACL entry for the path it needs."
            )
        if code == 404:
            return (
                f"Proxmox has no such resource ({detail}). Verify the node name and "
                f"VM/container ID with list_nodes, list_vms or list_containers."
            )
        if code == 501:
            return (
                f"Proxmox cannot serve this endpoint ({detail}). For guest-agent tools "
                f"this usually means the QEMU guest agent is not installed or not "
                f"enabled for that VM."
            )
        return f"Proxmox API error ({detail})."

    if isinstance(exc, AuthenticationError):
        return (
            f"Proxmox rejected the credentials for {where}: {exc}. Check PROXMOX_USER "
            f"plus PROXMOX_TOKEN_NAME/PROXMOX_TOKEN_VALUE (or PROXMOX_PASSWORD)."
        )

    if isinstance(exc, rex.SSLError):
        return (
            f"TLS verification failed for {where}. Proxmox ships a self-signed "
            f"certificate by default — set PROXMOX_VERIFY_SSL=false or install a "
            f"trusted certificate."
        )

    if isinstance(exc, rex.ConnectTimeout | rex.ConnectionError):
        return (
            f"Cannot reach Proxmox at {where} — the host is down, unreachable from "
            f"here, or the API port is closed."
        )

    if isinstance(exc, rex.Timeout):
        return f"Proxmox at {where} accepted the connection but did not answer in time."

    if isinstance(exc, ValueError):
        return str(exc)

    return f"{type(exc).__name__}: {exc}"


def _wrap_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Re-raise anything the tool body throws as a ``ToolError`` the model can read."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:
            # A tier denial is the policy working as intended, not a fault to report.
            if not isinstance(exc, PermissionError):
                report_exception(exc)
            raise ToolError(_describe(exc, _endpoint(kwargs))) from exc

    return wrapper


def _guard_tier(fn: Callable[..., Any], name: str, required: Tier) -> Callable[..., Any]:
    """Re-check the tier at call time, on top of the registration gate.

    Belt and braces: registration is what keeps an elevated tool out of the tool
    list, this is what stops it running if it ever gets there anyway.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = kwargs.get("ctx")
        if ctx is None:
            ctx = next((a for a in args if hasattr(a, "request_context")), None)
        if ctx is None:  # pragma: no cover - the SDK always injects it
            raise RuntimeError(f"{name} was called without an MCP context")
        _tier(cast(Context, ctx), required, name)
        return fn(*args, **kwargs)

    return wrapper


def make_gate(
    mcp: MCPServer, policy: Policy
) -> Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """Return a drop-in ``@tool(...)`` decorator that gates registration.

    ``tier=`` is the operator's admission policy and ``annotations=`` is what the
    client is told about the call — two different questions, so the decorator takes
    both. A tool above ``policy.risk_level``, or outside ``policy.allow``, is never
    registered and stays out of the client's tool list. Registered elevated tools
    are additionally guarded at call time, and every tool is wrapped by
    ``_wrap_errors`` so Proxmox failures reach the model as readable text.
    """
    current = _TIER_ORDER[policy.risk_level]

    def tool(
        *, tier: Tier = "read", **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        _check_annotations(tier, kwargs.get("annotations"))
        allowed_tier = current >= _TIER_ORDER[tier]

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = kwargs.get("name") or fn.__name__
            policy.seen.add(name)
            if not allowed_tier or (policy.allow is not None and name not in policy.allow):
                return fn
            body = fn if tier == "read" else _guard_tier(fn, name, tier)
            policy.registered.add(name)
            return cast(Callable[..., Any], mcp.tool(**kwargs)(_wrap_errors(body)))

        return decorator

    return tool


def _ctx(ctx: Context) -> AppContext:
    return cast(AppContext, ctx.request_context.lifespan_context)


def _tier(ctx: Context, required: Tier, tool_name: str) -> None:
    """Raise unless the running risk level covers ``required``.

    The name is passed in rather than read off the call stack: ``inspect.stack()``
    reads every frame's source file from disk, and a wrapper between the tool body
    and this call would put the wrong name into the log and the refusal.
    """
    current = _ctx(ctx).settings.risk_level
    allowed = _TIER_ORDER[current] >= _TIER_ORDER[required]
    logger.info(
        "%s tool=%s required=%s current=%s",
        "ALLOW" if allowed else "DENY", tool_name, required, current,
    )
    if not allowed:
        raise PermissionError(
            f"{tool_name} requires PROXMOX_RISK_LEVEL={required} "
            f"or higher (current: {current})"
        )


def _redact(data: Any) -> Any:
    """Recursively mask secret-bearing config keys, keeping the shape intact.

    The key stays so the model can still see that a cloud-init password or an SSH
    key is configured; only the value goes.
    """
    if isinstance(data, Mapping):
        return {
            key: _REDACTED if str(key).lower() in _SECRET_KEYS else _redact(value)
            for key, value in data.items()
        }
    if isinstance(data, list | tuple):
        return [_redact(item) for item in data]
    return data


def _json(data: Any) -> str:
    """Serialize a Proxmox response compactly — indentation is pure token cost."""
    if get_redact_secrets():
        data = _redact(data)
    return json.dumps(data, separators=(",", ":"), default=str)


def _compact(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    """Keep only ``keys`` from each row, in the order Proxmox returned them.

    Inventory listings are the bulk of what a diagnostic session reads, and most of
    each row is per-second counters (``netin``, ``diskwrite``, ``pressure*``) that
    no decision is made on. Every tool that projects also takes ``verbose=True``.
    """
    wanted = set(keys)
    return [{k: v for k, v in row.items() if k in wanted} for row in rows]


def _accepted(operation: str, node: str, upid: str, **ids: Any) -> str:
    """Envelope for a write: Proxmox has queued a task, nothing has happened yet.

    The old ``{"status": "starting"}`` read like a state the guest was already in.
    ``poll_with`` names the tool that turns the UPID into an actual outcome.
    """
    return _json(
        {
            "state": "accepted",
            "operation": operation,
            "node": node,
            **ids,
            "upid": upid,
            "poll_with": "get_task_status",
        }
    )


# Fields the compact default of each inventory listing keeps. What is dropped is
# per-second counters (netin/netout/diskread/diskwrite) and PSI pressure gauges:
# real data, but nothing a triage decision turns on, and several times the volume
# of what is kept.
GUEST_FIELDS = (
    "vmid", "name", "node", "type", "status", "lock", "template", "tags",
    "uptime", "cpu", "maxcpu", "mem", "maxmem", "maxdisk", "pool", "hastate",
)
NODE_FIELDS = (
    "node", "status", "level", "uptime", "cpu", "maxcpu", "cpu_usage_pct",
    "mem", "maxmem", "mem_usage_pct", "disk", "maxdisk",
)
RESOURCE_FIELDS = (
    "id", "type", "node", "name", "vmid", "status", "lock", "template", "tags",
    "uptime", "cpu", "maxcpu", "mem", "maxmem", "disk", "maxdisk",
    "storage", "plugintype", "shared", "content", "hastate", "pool",
)

VerboseArg = Annotated[
    bool,
    Field(
        description=(
            "Return every field Proxmox sends instead of the compact subset "
            "(identity, status, uptime, cpu and memory). The full rows are several "
            "times larger and are mostly per-second IO counters."
        )
    ),
]
