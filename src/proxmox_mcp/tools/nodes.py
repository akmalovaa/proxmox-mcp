import json
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from proxmox_mcp.tools._common import READ_ONLY, _ctx


def register(mcp: FastMCP) -> None:

    @mcp.tool(annotations=READ_ONLY)
    def list_nodes(ctx: Context) -> str:
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
        return json.dumps(result, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_node_status(
        ctx: Context,
        node: Annotated[str, Field(description="Node name (e.g. 'pve', 'node1').")],
    ) -> str:
        """Get detailed status of a node: CPU, memory, disk, load average, kernel version."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).status.get()
        return json.dumps(status, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_node_networks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List network interfaces on a node."""
        pve = _ctx(ctx).proxmox
        networks = pve.nodes(node).network.get()
        return json.dumps(networks, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_node_disks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
    ) -> str:
        """List physical disks on a node."""
        pve = _ctx(ctx).proxmox
        disks = pve.nodes(node).disks.list.get()
        return json.dumps(disks, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_node_tasks(
        ctx: Context,
        node: Annotated[str, Field(description="Node name.")],
        limit: Annotated[
            int, Field(description="Maximum number of tasks to return.", ge=1, le=500)
        ] = 20,
    ) -> str:
        """List recent tasks on a node."""
        pve = _ctx(ctx).proxmox
        tasks = pve.nodes(node).tasks.get(limit=limit)
        return json.dumps(tasks, indent=2)

    @mcp.tool(annotations=READ_ONLY)
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
        return json.dumps(status, indent=2)

    @mcp.tool(annotations=READ_ONLY)
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
        return json.dumps(log, indent=2)
