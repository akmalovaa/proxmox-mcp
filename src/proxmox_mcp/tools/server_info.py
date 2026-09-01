import os
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from proxmox_mcp.config import get_redact_secrets
from proxmox_mcp.tools._common import READ_ONLY, Policy, _ctx, _json, make_gate


def register(mcp: MCPServer, policy: Policy) -> None:
    tool = make_gate(mcp, policy)

    @tool(tier="read", title="Server info", annotations=READ_ONLY)
    def get_server_info(ctx: Context) -> str:
        """Report this MCP server's own configuration: risk level, versions, tool count.

        The risk level is not otherwise observable: tools above it are absent from
        the list rather than refused, so a short list and a locked-down server look
        identical from the outside. `proxmox_version` is best-effort — it is null
        when Proxmox is unreachable, which is itself the answer to "is the backend
        up?".
        """
        app = _ctx(ctx)
        settings = app.settings

        proxmox_version: Any = None
        proxmox_error: str | None = None
        try:
            proxmox_version = app.proxmox.version.get()
        except Exception as exc:  # noqa: BLE001 - this tool must answer regardless
            proxmox_error = f"{type(exc).__name__}: {exc}"

        info: dict[str, Any] = {
            "server_version": mcp.version or "unknown",
            "risk_level": policy.risk_level,
            "tools_registered": len(policy.registered),
            "tools_available_at_all_levels": len(policy.seen),
            "tools_allowlist": sorted(policy.allow) if policy.allow else None,
            "redact_secrets": get_redact_secrets(),
            "transport": os.environ.get("PROXMOX_MCP_TRANSPORT", "stdio"),
            "proxmox_host": f"{settings.host}:{settings.port}",
            "proxmox_user": settings.user,
            "proxmox_auth": "token" if settings.token_name else "password",
            "proxmox_version": proxmox_version,
        }
        if proxmox_error:
            info["proxmox_error"] = proxmox_error
        return _json(info)
