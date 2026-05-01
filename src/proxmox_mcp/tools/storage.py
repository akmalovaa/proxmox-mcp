import json
from typing import Literal

from mcp.server.fastmcp import FastMCP, Context

from proxmox_mcp.tools._common import _ctx

ContentType = Literal["iso", "backup", "images", "rootdir", "vztmpl"]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_storage(ctx: Context, node: str | None = None) -> str:
        """List storage pools with usage info. Optionally filter by node.

        Args:
            node: Filter by node name. If omitted, lists all cluster storage.
        """
        pve = _ctx(ctx).proxmox
        if node:
            storage = pve.nodes(node).storage.get()
        else:
            storage = pve.storage.get()
        return json.dumps(storage, indent=2)

    @mcp.tool()
    def get_storage_content(
        ctx: Context, node: str, storage: str, content: ContentType | None = None
    ) -> str:
        """List contents of a storage pool (ISOs, disk images, backups, etc).

        Args:
            node: Node name
            storage: Storage pool name (e.g. 'local', 'local-lvm')
            content: Filter by content type: 'iso', 'backup', 'images', 'rootdir', 'vztmpl'
        """
        pve = _ctx(ctx).proxmox
        params = {}
        if content:
            params["content"] = content
        items = pve.nodes(node).storage(storage).content.get(**params)
        return json.dumps(items, indent=2)
