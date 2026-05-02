import json
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from proxmox_mcp.tools._common import READ_ONLY, _ctx

ResourceType = Literal["vm", "storage", "node", "sdn"]


def register(mcp: FastMCP) -> None:

    @mcp.tool(annotations=READ_ONLY)
    def get_cluster_status(ctx: Context) -> str:
        """Get overall cluster status: quorum state and node membership."""
        pve = _ctx(ctx).proxmox
        status = pve.cluster.status.get()
        return json.dumps(status, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_cluster_resources(
        ctx: Context,
        type: Annotated[
            ResourceType | None,
            Field(
                description=(
                    "Filter by resource type: 'vm' (QEMU + LXC), 'storage', 'node', 'sdn'."
                )
            ),
        ] = None,
    ) -> str:
        """List all resources in the cluster (VMs, containers, storage, nodes)."""
        pve = _ctx(ctx).proxmox
        params = {}
        if type:
            params["type"] = type
        resources = pve.cluster.resources.get(**params)
        return json.dumps(resources, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_cluster_backups(ctx: Context) -> str:
        """List all backup jobs configured in the cluster (vzdump schedules)."""
        pve = _ctx(ctx).proxmox
        jobs = pve.cluster.backup.get()
        return json.dumps(jobs, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_next_vmid(ctx: Context) -> str:
        """Get the next available VM/container ID in the cluster."""
        pve = _ctx(ctx).proxmox
        vmid = pve.cluster.nextid.get()
        return json.dumps({"next_vmid": vmid})
