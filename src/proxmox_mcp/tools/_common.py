import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, Literal, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from proxmox_mcp.client import AppContext
from proxmox_mcp.config import RiskLevel

Tier = Literal["lifecycle", "all"]

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
    """Map a tool's annotations to the risk tier required to expose it."""
    if annotations is DESTRUCTIVE:
        return "all"
    if annotations is LIFECYCLE:
        return "lifecycle"
    return "read"


def make_gate(
    mcp: MCPServer, risk_level: RiskLevel
) -> Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """Return a drop-in ``@tool(...)`` decorator that gates registration by tier.

    The required tier is inferred from the ``annotations=`` kwarg (READ_ONLY /
    LIFECYCLE / DESTRUCTIVE), so a tool above ``risk_level`` is never registered
    and stays out of the client's tool list. ``_tier`` still guards at call time
    as defense in depth.
    """
    current = _TIER_ORDER[risk_level]

    def tool(**kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        enabled = current >= _TIER_ORDER[_required_tier(kwargs.get("annotations"))]

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return mcp.tool(**kwargs)(fn) if enabled else fn

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


def _status_response(status: str, upid: str) -> str:
    return json.dumps({"status": status, "upid": upid})
