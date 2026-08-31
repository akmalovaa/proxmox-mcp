from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools._common import READ_ONLY, _ctx, _json, make_gate

ContentType = Literal["iso", "backup", "images", "rootdir", "vztmpl"]


def register(mcp: MCPServer, risk_level: RiskLevel) -> None:
    tool = make_gate(mcp, risk_level)

    @tool(title="List storage", annotations=READ_ONLY)
    def list_storage(
        ctx: Context,
        node: Annotated[
            str | None,
            Field(description="Optional node name. If omitted, lists all cluster-wide storage."),
        ] = None,
    ) -> str:
        """List storage pools with usage info, optionally filtered by node."""
        pve = _ctx(ctx).proxmox
        storage = pve.nodes(node).storage.get() if node else pve.storage.get()
        return _json(storage)

    @tool(title="Storage contents", annotations=READ_ONLY)
    def get_storage_content(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
        storage: Annotated[
            str, Field(description="Storage pool name (e.g. 'local', 'local-lvm', 'cephfs').")
        ],
        content: Annotated[
            ContentType | None,
            Field(
                description=(
                    "Filter by content type: 'iso' (ISO images), 'backup' (vzdump backups), "
                    "'images' (VM disks), 'rootdir' (LXC rootfs), 'vztmpl' (LXC templates)."
                )
            ),
        ] = None,
    ) -> str:
        """List contents of a storage pool: ISOs, disk images, backups, container templates."""
        pve = _ctx(ctx).proxmox
        params = {}
        if content:
            params["content"] = content
        items = pve.nodes(node).storage(storage).content.get(**params)
        return _json(items)
