import json

from mcp.server.fastmcp import Context, FastMCP

from proxmox_mcp.tools._common import _ctx


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_nodes(ctx: Context) -> str:
        """List all nodes in the Proxmox cluster with their status, CPU, memory, and uptime."""
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

    @mcp.tool()
    def get_node_status(ctx: Context, node: str) -> str:
        """Get detailed status of a node: CPU, memory, disk, load average, kernel version.

        Args:
            node: Node name (e.g. 'pve', 'node1')
        """
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).status.get()
        return json.dumps(status, indent=2)

    @mcp.tool()
    def get_node_networks(ctx: Context, node: str) -> str:
        """List network interfaces on a node.

        Args:
            node: Node name
        """
        pve = _ctx(ctx).proxmox
        networks = pve.nodes(node).network.get()
        return json.dumps(networks, indent=2)

    @mcp.tool()
    def get_node_disks(ctx: Context, node: str) -> str:
        """List physical disks on a node.

        Args:
            node: Node name
        """
        pve = _ctx(ctx).proxmox
        disks = pve.nodes(node).disks.list.get()
        return json.dumps(disks, indent=2)

    @mcp.tool()
    def get_node_tasks(ctx: Context, node: str, limit: int = 20) -> str:
        """List recent tasks on a node.

        Args:
            node: Node name
            limit: Maximum number of tasks to return (default 20)
        """
        pve = _ctx(ctx).proxmox
        tasks = pve.nodes(node).tasks.get(limit=limit)
        return json.dumps(tasks, indent=2)

    @mcp.tool()
    def get_task_status(ctx: Context, node: str, upid: str) -> str:
        """Get status of a specific task by its UPID.

        Args:
            node: Node name where the task runs
            upid: Task UPID string
        """
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).tasks(upid).status.get()
        return json.dumps(status, indent=2)

    @mcp.tool()
    def get_task_log(ctx: Context, node: str, upid: str, limit: int = 50) -> str:
        """Get log output from a specific task.

        Args:
            node: Node name where the task runs
            upid: Task UPID string
            limit: Maximum number of log lines (default 50)
        """
        pve = _ctx(ctx).proxmox
        log = pve.nodes(node).tasks(upid).log.get(limit=limit)
        return json.dumps(log, indent=2)
