from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools._common import (
    DESTRUCTIVE,
    LIFECYCLE,
    READ_ONLY,
    RrdCf,
    Timeframe,
    _ctx,
    _json,
    _status_response,
    _tier,
    make_gate,
)

NodeArg = Annotated[str, Field(description="Node name where the container resides.")]
VmidArg = Annotated[int, Field(description="LXC container numeric ID.", ge=100, le=999999999)]
SnapnameArg = Annotated[str, Field(description="Snapshot name.")]


def register(mcp: MCPServer, risk_level: RiskLevel) -> None:
    tool = make_gate(mcp, risk_level)

    # ── Read-only ──

    @tool(title="List containers", annotations=READ_ONLY)
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
        return _json(cts)

    @tool(title="Container status", annotations=READ_ONLY)
    def get_container_status(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get current runtime status of an LXC container (running/stopped, CPU, memory)."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).lxc(vmid).status.current.get()
        return _json(status)

    @tool(title="Container config", annotations=READ_ONLY)
    def get_container_config(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get LXC container configuration: rootfs, network, resources, hostname."""
        pve = _ctx(ctx).proxmox
        config = pve.nodes(node).lxc(vmid).config.get()
        return _json(config)

    @tool(title="Container IP addresses", annotations=READ_ONLY)
    def get_container_interfaces(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get a running LXC container's network interfaces and IP addresses.

        This is the way to learn a container's actual IP — get_container_config shows
        the configured net device (which may be DHCP), not the address in use. No guest
        agent is needed, but the container must be running.
        """
        pve = _ctx(ctx).proxmox
        interfaces = pve.nodes(node).lxc(vmid).interfaces.get()
        return _json(interfaces)

    @tool(title="Container metrics history", annotations=READ_ONLY)
    def get_container_rrd_data(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
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
        """Get historical CPU, memory, disk and network metrics for a container (RRD series)."""
        pve = _ctx(ctx).proxmox
        data = pve.nodes(node).lxc(vmid).rrddata.get(timeframe=timeframe, cf=cf)
        return _json(data)

    @tool(title="List container snapshots", annotations=READ_ONLY)
    def list_container_snapshots(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """List all snapshots of an LXC container."""
        pve = _ctx(ctx).proxmox
        snapshots = pve.nodes(node).lxc(vmid).snapshot.get()
        return _json(snapshots)

    # ── Lifecycle (PROXMOX_RISK_LEVEL=lifecycle) ──

    @tool(title="Start container", annotations=LIFECYCLE)
    def start_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Start an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.start.post()
        return _status_response("starting", upid)

    @tool(title="Force-stop container", annotations=LIFECYCLE)
    def stop_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Force-stop an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @tool(title="Shut down container", annotations=LIFECYCLE)
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

    @tool(title="Reboot container", annotations=LIFECYCLE)
    def reboot_container(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Reboot an LXC container. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).lxc(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @tool(title="Create container snapshot", annotations=LIFECYCLE)
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

    @tool(title="Delete container snapshot", annotations=DESTRUCTIVE)
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

    @tool(title="Roll back container snapshot", annotations=DESTRUCTIVE)
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
