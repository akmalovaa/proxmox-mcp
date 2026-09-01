from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from proxmox_mcp.tools._common import (
    READ_ONLY,
    RESOURCE_FIELDS,
    Policy,
    VerboseArg,
    _compact,
    _ctx,
    _json,
    make_gate,
)

ResourceType = Literal["vm", "storage", "node", "sdn"]


def register(mcp: MCPServer, policy: Policy) -> None:
    tool = make_gate(mcp, policy)

    @tool(tier="read", title="Cluster status", annotations=READ_ONLY)
    def get_cluster_status(ctx: Context) -> str:
        """Get overall cluster status: quorum state and node membership."""
        pve = _ctx(ctx).proxmox
        status = pve.cluster.status.get()
        return _json(status)

    @tool(tier="read", title="Cluster resources", annotations=READ_ONLY)
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
        verbose: VerboseArg = False,
    ) -> str:
        """List all resources in the cluster (VMs, containers, storage, nodes)."""
        pve = _ctx(ctx).proxmox
        params = {}
        if type:
            params["type"] = type
        resources = pve.cluster.resources.get(**params)
        return _json(resources if verbose else _compact(resources, RESOURCE_FIELDS))

    @tool(tier="read", title="Cluster backup jobs", annotations=READ_ONLY)
    def get_cluster_backups(ctx: Context) -> str:
        """List all backup jobs configured in the cluster (vzdump schedules)."""
        pve = _ctx(ctx).proxmox
        jobs = pve.cluster.backup.get()
        return _json(jobs)

    @tool(tier="read", title="HA status", annotations=READ_ONLY)
    def get_ha_status(ctx: Context) -> str:
        """Get current high-availability status: managed resources, their state and node.

        Returns an empty list on clusters where HA is not configured, which is the
        normal answer for a single-node install.
        """
        pve = _ctx(ctx).proxmox
        status = pve.cluster.ha.status.current.get()
        return _json(status)

    @tool(tier="read", title="List pools", annotations=READ_ONLY)
    def list_pools(ctx: Context) -> str:
        """List resource pools used to group VMs, containers and storage."""
        pve = _ctx(ctx).proxmox
        pools = pve.pools.get()
        return _json(pools)

    @tool(tier="read", title="Cluster log", annotations=READ_ONLY)
    def get_cluster_log(
        ctx: Context,
        limit: Annotated[
            int, Field(description="Maximum number of log entries to return.", ge=1, le=500)
        ] = 50,
    ) -> str:
        """Read the cluster-wide event log, newest first.

        Spans every node, unlike get_node_tasks — use it for "what happened recently"
        across the cluster, including logins and configuration changes.
        """
        pve = _ctx(ctx).proxmox
        entries = pve.cluster.log.get(max=limit)
        return _json(entries)

    @tool(tier="read", title="Next free VMID", annotations=READ_ONLY)
    def get_next_vmid(ctx: Context) -> str:
        """Get the next available VM/container ID in the cluster."""
        pve = _ctx(ctx).proxmox
        vmid = pve.cluster.nextid.get()
        return _json({"next_vmid": vmid})
