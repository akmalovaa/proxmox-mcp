from typing import Annotated, Any

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

NodeArg = Annotated[str, Field(description="Node name where the VM resides.")]
VmidArg = Annotated[int, Field(description="QEMU VM numeric ID.", ge=100, le=999999999)]
SnapnameArg = Annotated[str, Field(description="Snapshot name.")]


def register(mcp: MCPServer, risk_level: RiskLevel) -> None:
    tool = make_gate(mcp, risk_level)

    # ── Read-only ──

    @tool(title="List VMs", annotations=READ_ONLY)
    def list_vms(
        ctx: Context,
        node: Annotated[
            str | None,
            Field(description="Optional node name. If omitted, lists VMs across the cluster."),
        ] = None,
    ) -> str:
        """List all QEMU VMs in the cluster, optionally filtered by node."""
        pve = _ctx(ctx).proxmox
        if node:
            vms = pve.nodes(node).qemu.get()
            vms = [{**vm, "node": node} for vm in vms]
        else:
            resources = pve.cluster.resources.get(type="vm")
            vms = [r for r in resources if r.get("type") == "qemu"]
        return _json(vms)

    @tool(title="VM status", annotations=READ_ONLY)
    def get_vm_status(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get current runtime status of a VM (running/stopped, CPU, memory, uptime)."""
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).qemu(vmid).status.current.get()
        return _json(status)

    @tool(title="VM config", annotations=READ_ONLY)
    def get_vm_config(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get VM configuration: hardware, boot order, disks, network, cloud-init, etc."""
        pve = _ctx(ctx).proxmox
        config = pve.nodes(node).qemu(vmid).config.get()
        return _json(config)

    @tool(title="VM IP addresses", annotations=READ_ONLY)
    def get_vm_network_interfaces(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Get a running VM's network interfaces and IP addresses via the QEMU guest agent.

        This is the only way to learn a VM's actual IP — get_vm_config shows the virtual
        NIC and its MAC, not the address the guest ended up with. Requires the VM to be
        running with qemu-guest-agent installed and `agent: 1` set in its config;
        otherwise Proxmox answers with an error rather than an empty list.
        """
        pve = _ctx(ctx).proxmox
        interfaces = pve.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
        return _json(interfaces)

    @tool(title="VM metrics history", annotations=READ_ONLY)
    def get_vm_rrd_data(
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
        """Get historical CPU, memory, disk and network metrics for a VM (RRD series)."""
        pve = _ctx(ctx).proxmox
        data = pve.nodes(node).qemu(vmid).rrddata.get(timeframe=timeframe, cf=cf)
        return _json(data)

    @tool(title="List VM snapshots", annotations=READ_ONLY)
    def list_vm_snapshots(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """List all snapshots of a VM."""
        pve = _ctx(ctx).proxmox
        snapshots = pve.nodes(node).qemu(vmid).snapshot.get()
        return _json(snapshots)

    # ── Lifecycle (PROXMOX_RISK_LEVEL=lifecycle) ──

    @tool(title="Start VM", annotations=LIFECYCLE)
    def start_vm(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Start a VM. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.start.post()
        return _status_response("starting", upid)

    @tool(title="Force-stop VM", annotations=LIFECYCLE)
    def stop_vm(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Force-stop a VM (like pulling the power). Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @tool(title="Shut down VM", annotations=LIFECYCLE)
    def shutdown_vm(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        timeout: Annotated[
            int,
            Field(
                description="Seconds to wait for ACPI shutdown before force-stop.",
                ge=1,
                le=3600,
            ),
        ] = 60,
    ) -> str:
        """Gracefully shutdown a VM via ACPI. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.shutdown.post(timeout=timeout)
        return _status_response("shutting_down", upid)

    @tool(title="Reboot VM", annotations=LIFECYCLE)
    def reboot_vm(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Reboot a VM via ACPI. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @tool(title="Suspend VM", annotations=LIFECYCLE)
    def suspend_vm(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Suspend a VM (pause execution, keep memory). Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.suspend.post()
        return _status_response("suspending", upid)

    @tool(title="Resume VM", annotations=LIFECYCLE)
    def resume_vm(ctx: Context, node: NodeArg, vmid: VmidArg) -> str:
        """Resume a suspended VM. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.resume.post()
        return _status_response("resuming", upid)

    @tool(title="Clone VM", annotations=LIFECYCLE)
    def clone_vm(
        ctx: Context,
        node: NodeArg,
        vmid: Annotated[
            int,
            Field(description="Source VM ID to clone from.", ge=100, le=999999999),
        ],
        newid: Annotated[
            int,
            Field(
                description="ID for the new cloned VM (must not be in use).",
                ge=100,
                le=999999999,
            ),
        ],
        name: Annotated[
            str | None, Field(description="Optional name for the cloned VM.")
        ] = None,
        full: Annotated[
            bool,
            Field(description="True = full clone (independent disks); False = linked clone."),
        ] = True,
    ) -> str:
        """Clone a VM into a new VM. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        # Proxmox API expects 0/1 for boolean params, not true/false.
        params: dict[str, Any] = {"newid": newid, "full": int(full)}
        if name:
            params["name"] = name
        upid = pve.nodes(node).qemu(vmid).clone.post(**params)
        return _status_response("cloning", upid)

    @tool(title="Migrate VM", annotations=LIFECYCLE)
    def migrate_vm(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        target: Annotated[
            str, Field(description="Name of the node to migrate the VM to.")
        ],
        online: Annotated[
            bool,
            Field(
                description=(
                    "Live-migrate a running VM instead of requiring it to be stopped. "
                    "Ignored by Proxmox if the VM is not running."
                )
            ),
        ] = True,
        with_local_disks: Annotated[
            bool,
            Field(
                description=(
                    "Also copy disks that live on node-local storage. Needed when the "
                    "VM is not entirely on shared storage; makes the migration much slower."
                )
            ),
        ] = False,
    ) -> str:
        """Migrate a VM to another node. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        # Proxmox API expects 0/1 for boolean params, and hyphenates this one.
        params: dict[str, Any] = {"target": target, "online": int(online)}
        if with_local_disks:
            params["with-local-disks"] = 1
        upid = pve.nodes(node).qemu(vmid).migrate.post(**params)
        return _status_response("migrating", upid)

    @tool(title="Create VM snapshot", annotations=LIFECYCLE)
    def create_vm_snapshot(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        snapname: SnapnameArg,
        description: Annotated[
            str, Field(description="Optional human-readable description of the snapshot.")
        ] = "",
    ) -> str:
        """Create a snapshot of a VM. Requires PROXMOX_RISK_LEVEL=lifecycle."""
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot.post(
            snapname=snapname, description=description
        )
        return _status_response("creating_snapshot", upid)

    # ── Destructive (PROXMOX_RISK_LEVEL=all) ──

    @tool(title="Delete VM snapshot", annotations=DESTRUCTIVE)
    def delete_vm_snapshot(
        ctx: Context,
        node: NodeArg,
        vmid: VmidArg,
        snapname: Annotated[str, Field(description="Snapshot name to delete (irreversible).")],
    ) -> str:
        """Delete a VM snapshot. Irreversible. Requires PROXMOX_RISK_LEVEL=all."""
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).delete()
        return _status_response("deleting_snapshot", upid)

    @tool(title="Roll back VM snapshot", annotations=DESTRUCTIVE)
    def rollback_vm_snapshot(
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
        """Roll back a VM to a snapshot. Discards changes made since the snapshot.

        Requires PROXMOX_RISK_LEVEL=all.
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).rollback.post()
        return _status_response("rolling_back", upid)
