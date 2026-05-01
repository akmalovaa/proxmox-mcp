import inspect
import json
import logging
from typing import Literal

from mcp.server.fastmcp import Context

from proxmox_mcp.client import AppContext

Tier = Literal["lifecycle", "all"]

_TIER_ORDER = {"read": 0, "lifecycle": 1, "all": 2}

logger = logging.getLogger("proxmox_mcp.policy")


def _ctx(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


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
