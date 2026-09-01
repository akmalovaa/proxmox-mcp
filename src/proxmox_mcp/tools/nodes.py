from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from proxmox_mcp.tools._common import (
    NODE_FIELDS,
    READ_ONLY,
    Policy,
    RrdCf,
    Timeframe,
    VerboseArg,
    _compact,
    _ctx,
    _json,
    make_gate,
)


def register(mcp: MCPServer, policy: Policy) -> None:
    tool = make_gate(mcp, policy)

    @tool(tier="read", title="List nodes", annotations=READ_ONLY)
    def list_nodes(ctx: Context, verbose: VerboseArg = False) -> str:
        """List all nodes in the Proxmox cluster with status, CPU, memory, and uptime."""
        pve = _ctx(ctx).proxmox
        nodes = pve.nodes.get()
        result = []
        for node in nodes:
            enriched = dict(node)
            maxmem = node.get("maxmem")
            if maxmem:
                enriched["mem_usage_pct"] = round(node.get("mem", 0) / maxmem * 100, 1)
            if "cpu" in node:
                enriched["cpu_usage_pct"] = round(node["cpu"] * 100, 1)
            result.append(enriched)
        return _json(result if verbose else _compact(result, NODE_FIELDS))

    @tool(tier="read", title="Node status", annotations=READ_ONLY)
    def get_node_status(
        ctx: Context,
        node: Annotated[str, Field(description="Node name (e.g. 'pve', 'node1').")],
    ) -> str:
        """Get detailed status of a node: CPU, memory, disk, load average, kernel version."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).status.get()
        return _json(status)

    @tool(tier="read", title="Node networks", annotations=READ_ONLY)
    def get_node_networks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List network interfaces on a node."""
        pve = _ctx(ctx).proxmox
        networks = pve.nodes(node).network.get()
        return _json(networks)

    @tool(tier="read", title="Node disks", annotations=READ_ONLY)
    def get_node_disks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List physical disks on a node."""
        pve = _ctx(ctx).proxmox
        disks = pve.nodes(node).disks.list.get()
        return _json(disks)

    @tool(tier="read", title="Node services", annotations=READ_ONLY)
    def get_node_services(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List Proxmox system services on a node with their running state.

        Covers pveproxy, pvedaemon, pve-cluster, pvestatd, corosync and friends —
        use it when the node is up but the cluster or web UI misbehaves.
        """
        pve = _ctx(ctx).proxmox
        services = pve.nodes(node).services.get()
        return _json(services)

    @tool(tier="read", title="Node updates", annotations=READ_ONLY)
    def get_node_updates(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List pending APT package updates on a node.

        Reads the cached package index; it does not run `apt update`, so results are
        as fresh as the node's last refresh.
        """
        pve = _ctx(ctx).proxmox
        updates = pve.nodes(node).apt.update.get()
        return _json(updates)

    @tool(tier="read", title="Node metrics history", annotations=READ_ONLY)
    def get_node_rrd_data(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
        timeframe: Annotated[
            Timeframe,
            Field(description="Window of history to return, counting back from now."),
        ] = "day",
        cf: Annotated[
            RrdCf,
            Field(
                description=(
                    "How each sample bucket is condensed: 'AVERAGE' for typical load, "
                    "'MAX' to catch spikes that averaging hides."
                )
            ),
        ] = "AVERAGE",
    ) -> str:
        """Get historical CPU, memory, disk and network metrics for a node (RRD series).

        Use this for questions about the past — "was it swapping last night", "when did
        load spike" — which get_node_status cannot answer, as it only reports right now.
        """
        pve = _ctx(ctx).proxmox
        data = pve.nodes(node).rrddata.get(timeframe=timeframe, cf=cf)
        return _json(data)

    @tool(tier="read", title="Node tasks", annotations=READ_ONLY)
    def get_node_tasks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
        limit: Annotated[
            int, Field(description="Maximum number of tasks to return.", ge=1, le=500)
        ] = 20,
        errors_only: Annotated[
            bool,
            Field(description="Return only tasks that ended in an error."),
        ] = False,
    ) -> str:
        """List recent tasks on a node, newest first, optionally only failed ones."""
        pve = _ctx(ctx).proxmox
        params: dict[str, Any] = {"limit": limit}
        if errors_only:
            # Proxmox expects 0/1 for boolean query params, not true/false.
            params["errors"] = 1
        tasks = pve.nodes(node).tasks.get(**params)
        return _json(tasks)

    @tool(tier="read", title="Task status", annotations=READ_ONLY)
    def get_task_status(
        ctx: Context,
        node: Annotated[str, Field(description="Node name where the task runs.")],
        upid: Annotated[
            str,
            Field(description="Task UPID string returned by a previous operation."),
        ],
    ) -> str:
        """Get status of a specific task by its UPID."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).tasks(upid).status.get()
        return _json(status)

    @tool(tier="read", title="Task log", annotations=READ_ONLY)
    def get_task_log(
        ctx: Context,
        node: Annotated[str, Field(description="Node name where the task runs.")],
        upid: Annotated[str, Field(description="Task UPID string.")],
        limit: Annotated[
            int, Field(description="Maximum number of log lines.", ge=1, le=1000)
        ] = 50,
    ) -> str:
        """Get log output from a specific task."""
        pve = _ctx(ctx).proxmox
        log = pve.nodes(node).tasks(upid).log.get(limit=limit)
        return _json(log)
