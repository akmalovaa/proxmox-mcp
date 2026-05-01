import json

from mcp.server.fastmcp import Context

from proxmox_mcp.client import AppContext


def _ctx(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


def _elevated(ctx: Context) -> None:
    if not _ctx(ctx).settings.allow_elevated:
        raise PermissionError(
            "This operation requires PROXMOX_ALLOW_ELEVATED=true"
        )


def _status_response(status: str, upid: str) -> str:
    return json.dumps({"status": status, "upid": upid})
