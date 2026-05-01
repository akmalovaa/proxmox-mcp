import json

from mcp.server.fastmcp import Context, FastMCP

from proxmox_mcp.tools._common import _ctx, _status_response, _tier


def register(mcp: FastMCP) -> None:

    # ── Read-only ──

    @mcp.tool()
    def list_containers(ctx: Context, node: str | None = None) -> str:
        """List all LXC containers. Optionally filter by node.

        Args:
            node: Filter by node name. If omitted, lists containers from all nodes.
        """
        pve = _ctx(ctx).proxmox
        if node:
            cts = pve.nodes(node).lxc.get()
            cts = [{**ct, "node": node} for ct in cts]
        else:
            resources = pve.cluster.resources.get(type="vm")
            cts = [r for r in resources if r.get("type") == "lxc"]
        return json.dumps(cts, indent=2)

    @mcp.tool()
    def get_container_status(ctx: Context, node: str, vmid: int) -> str:
        """Get current status of an LXC container.

        Args:
            node: Node name
            vmid: Container ID number
        """
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).lxc(vmid).status.current.get()
        return json.dumps(status, indent=2)

    @mcp.tool()
    def get_container_config(ctx: Context, node: str, vmid: int) -> str:
        """Get LXC container configuration.

        Args:
            node: Node name
            vmid: Container ID number
        """
        pve = _ctx(ctx).proxmox
        config = pve.nodes(node).lxc(vmid).config.get()
        return json.dumps(config, indent=2)

    @mcp.tool()
    def list_container_snapshots(ctx: Context, node: str, vmid: int) -> str:
        """List all snapshots of an LXC container.

        Args:
            node: Node name
            vmid: Container ID number
        """
        pve = _ctx(ctx).proxmox
        snapshots = pve.nodes(node).lxc(vmid).snapshot.get()
        return json.dumps(snapshots, indent=2)

    # ── Lifecycle (PROXMOX_RISK_LEVEL=lifecycle) ──

    @mcp.tool()
    def start_container(ctx: Context, node: str, vmid: int) -> str:
        """Start an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Container ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.start.post()
        return _status_response("starting", upid)

    @mcp.tool()
    def stop_container(ctx: Context, node: str, vmid: int) -> str:
        """Force-stop an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Container ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @mcp.tool()
    def shutdown_container(ctx: Context, node: str, vmid: int, timeout: int = 60) -> str:
        """Gracefully shutdown an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Container ID number
            timeout: Seconds to wait before force-stop (default 60)
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.shutdown.post(timeout=timeout)
        return _status_response("shutting_down", upid)

    @mcp.tool()
    def reboot_container(ctx: Context, node: str, vmid: int) -> str:
        """Reboot an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Container ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @mcp.tool()
    def create_container_snapshot(
        ctx: Context, node: str, vmid: int, snapname: str, description: str = ""
    ) -> str:
        """Create a snapshot of an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Container ID
            snapname: Snapshot name
            description: Optional description
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot.post(
            snapname=snapname, description=description
        )
        return _status_response("creating_snapshot", upid)

    # ── Destructive (PROXMOX_RISK_LEVEL=all) ──

    @mcp.tool()
    def delete_container_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Delete an LXC container snapshot. Requires PROXMOX_RISK_LEVEL=all.

        Args:
            node: Node name
            vmid: Container ID
            snapname: Snapshot name to delete
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot(snapname).delete()
        return _status_response("deleting_snapshot", upid)

    @mcp.tool()
    def rollback_container_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Rollback an LXC container to a snapshot. Requires PROXMOX_RISK_LEVEL=all.

        Args:
            node: Node name
            vmid: Container ID
            snapname: Snapshot name to rollback to
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot(snapname).rollback.post()
        return _status_response("rolling_back", upid)
