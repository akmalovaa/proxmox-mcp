import json
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from proxmox_mcp.tools._common import (
    DESTRUCTIVE,
    LIFECYCLE,
    READ_ONLY,
    _ctx,
    _status_response,
    _tier,
)

NodeArg = Annotated[str, Field(description="Node name where the container resides.")]
VmidArg = Annotated[int, Field(description="LXC container numeric ID.", ge=100, le=999999999)]
SnapnameArg = Annotated[str, Field(description="Snapshot name.")]


def register(mcp: FastMCP) -> None:

    # ── Read-only ──

    @mcp.tool(annotations=READ_ONLY)
    def list_containers(
        ctx: Context,
        node: Annotated[
            str | None,
            Field(
                description="Optional node name. If omitted, lists containers across the cluster."
            ),
        ] = None,
    ) -> str:
        """List all LXC containers in the cluster, optionally filtered by node."""
        pve = _ctx(ctx).proxmox
        if node:
            cts = pve.nodes(node).lxc.get()
            cts = [{**ct, "node": node} for ct in cts]
        else:
            resources = pve.cluster.resources.get(type="vm")
            cts = [r for r in resources if r.get("type") == "lxc"]
        return json.dumps(cts, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_container_status(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get current runtime status of an LXC container (running/stopped, CPU, memory)."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).lxc(vmid).status.current.get()
        return json.dumps(status, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def get_container_config(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get LXC container configuration: rootfs, network, resources, hostname."""
        pve = _ctx(ctx).proxmox
        config = pve.nodes(node).lxc(vmid).config.get()
        return json.dumps(config, indent=2)

    @mcp.tool(annotations=READ_ONLY)
    def list_container_snapshots(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """List all snapshots of an LXC container."""
        pve = _ctx(ctx).proxmox
        snapshots = pve.nodes(node).lxc(vmid).snapshot.get()
        return json.dumps(snapshots, indent=2)

    # ── Lifecycle (PROXMOX_RISK_LEVEL=lifecycle) ──

    @mcp.tool(annotations=LIFECYCLE)
    def start_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Start an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.start.post()
        return _status_response("starting", upid)

    @mcp.tool(annotations=LIFECYCLE)
    def stop_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Force-stop an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @mcp.tool(annotations=LIFECYCLE)
    def shutdown_container(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        timeout: Annotated[
            int,
            Field(
                description="Seconds to wait for graceful shutdown before force-stop.",
                ge=1,
                le=3600,
            ),
        ] = 60,
    ) -> str:
        """Gracefully shutdown an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.shutdown.post(timeout=timeout)
        return _status_response("shutting_down", upid)

    @mcp.tool(annotations=LIFECYCLE)
    def reboot_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Reboot an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @mcp.tool(annotations=LIFECYCLE)
    def create_container_snapshot(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        snapname: SnapnameArg,
        description: Annotated[
            str, Field(description="Optional human-readable description of the snapshot.")
        ] = "",
    ) -> str:
        """Create a snapshot of an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot.post(
            snapname=snapname, description=description
        )
        return _status_response("creating_snapshot", upid)

    # ── Destructive (PROXMOX_RISK_LEVEL=all) ──

    @mcp.tool(annotations=DESTRUCTIVE)
    def delete_container_snapshot(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        snapname: Annotated[str, Field(description="Snapshot name to delete (irreversible).")],
    ) -> str:
        """Delete an LXC container snapshot. Irreversible. Requires PROXMOX_RISK_LEVEL=all."""
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot(snapname).delete()
        return _status_response("deleting_snapshot", upid)

    @mcp.tool(annotations=DESTRUCTIVE)
    def rollback_container_snapshot(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        snapname: Annotated[
            str,
            Field(
                description=(
                    "Snapshot name to roll back to. Discards all changes since then."
                )
            ),
        ],
    ) -> str:
        """Roll back an LXC container to a snapshot. Discards changes since then.

        Requires PROXMOX_RISK_LEVEL=all.
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).snapshot(snapname).rollback.post()
        return _status_response("rolling_back", upid)
