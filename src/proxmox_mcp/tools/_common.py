import functools
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, Literal, cast

import requests.exceptions as rex
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from proxmoxer.core import AuthenticationError, ResourceException

from proxmox_mcp.client import AppContext
from proxmox_mcp.config import RiskLevel
from proxmox_mcp.telemetry import report_exception

Tier = Literal["lifecycle", "all"]

# RRD metric windows accepted by every Proxmox */rrddata endpoint.
Timeframe = Literal["hour", "day", "week", "month", "year"]
RrdCf = Literal["AVERAGE", "MAX"]

_TIER_ORDER = {"read": 0, "lifecycle": 1, "all": 2}

logger = logging.getLogger("proxmox_mcp.policy")

# MCP tool annotations (hints for clients).
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
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)


def _required_tier(annotations: ToolAnnotations | None) -> str:
    """Map a tool's annotations to the risk tier required to expose it.

    Read from the annotation *fields* rather than by identity with the constants
    above, so a hand-built ``ToolAnnotations`` lands in the right tier instead of
    silently falling through to ``read``.
    """
    if annotations is None:
        raise ValueError(
            "every tool must pass annotations=READ_ONLY | LIFECYCLE | DESTRUCTIVE — "
            "the tier gate is derived from them"
        )
    if annotations.read_only_hint:
        return "read"
    if annotations.destructive_hint:
        return "all"
    return "lifecycle"


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
                f"the privileges this endpoint needs — check its role and, for tokens, "
                f"that Privilege Separation is off."
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


def make_gate(
    mcp: MCPServer, risk_level: RiskLevel
) -> Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """Return a drop-in ``@tool(...)`` decorator that gates registration by tier.

    The required tier is inferred from the ``annotations=`` kwarg (READ_ONLY /
    LIFECYCLE / DESTRUCTIVE), so a tool above ``risk_level`` is never registered
    and stays out of the client's tool list. ``_tier`` still guards at call time
    as defense in depth. Registered tools are wrapped by ``_wrap_errors`` so
    Proxmox failures reach the model as readable text.
    """
    current = _TIER_ORDER[risk_level]

    def tool(**kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        enabled = current >= _TIER_ORDER[_required_tier(kwargs.get("annotations"))]

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if not enabled:
                return fn
            registered = cast(Callable[..., Any], mcp.tool(**kwargs)(_wrap_errors(fn)))
            return registered

        return decorator

    return tool


def _ctx(ctx: Context) -> AppContext:
    return cast(AppContext, ctx.request_context.lifespan_context)


def _tier(ctx: Context, required: Tier) -> None:
    tool_name = inspect.stack()[1].function
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


def _json(data: Any) -> str:
    """Serialize a Proxmox response compactly — indentation is pure token cost."""
    return json.dumps(data, separators=(",", ":"), default=str)


def _status_response(status: str, upid: str) -> str:
    return _json({"status": status, "upid": upid})
