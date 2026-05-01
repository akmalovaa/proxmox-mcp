import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from proxmox_mcp.tools._common import _ctx, _status_response, _tier


def register(mcp: FastMCP) -> None:

    # ── Read-only ──

    @mcp.tool()
    def list_vms(ctx: Context, node: str | None = None) -> str:
        """List all QEMU VMs. Optionally filter by node.

        Args:
            node: Filter by node name. If omitted, lists VMs from all nodes.
        """
        pve = _ctx(ctx).proxmox
        if node:
            vms = pve.nodes(node).qemu.get()
            vms = [{**vm, "node": node} for vm in vms]
        else:
            resources = pve.cluster.resources.get(type="vm")
            vms = [r for r in resources if r.get("type") == "qemu"]
        return json.dumps(vms, indent=2)

    @mcp.tool()
    def get_vm_status(ctx: Context, node: str, vmid: int) -> str:
        """Get current status of a VM (running, stopped, cpu, memory, etc).

        Args:
            node: Node name where the VM resides
            vmid: VM ID number
        """
        pve = _ctx(ctx).proxmox
        status = pve.nodes(node).qemu(vmid).status.current.get()
        return json.dumps(status, indent=2)

    @mcp.tool()
    def get_vm_config(ctx: Context, node: str, vmid: int) -> str:
        """Get VM configuration (hardware, boot order, disks, network, etc).

        Args:
            node: Node name
            vmid: VM ID number
        """
        pve = _ctx(ctx).proxmox
        config = pve.nodes(node).qemu(vmid).config.get()
        return json.dumps(config, indent=2)

    @mcp.tool()
    def list_vm_snapshots(ctx: Context, node: str, vmid: int) -> str:
        """List all snapshots of a VM.

        Args:
            node: Node name
            vmid: VM ID number
        """
        pve = _ctx(ctx).proxmox
        snapshots = pve.nodes(node).qemu(vmid).snapshot.get()
        return json.dumps(snapshots, indent=2)

    # ── Lifecycle (PROXMOX_RISK_LEVEL=lifecycle) ──

    @mcp.tool()
    def start_vm(ctx: Context, node: str, vmid: int) -> str:
        """Start a VM. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.start.post()
        return _status_response("starting", upid)

    @mcp.tool()
    def stop_vm(ctx: Context, node: str, vmid: int) -> str:
        """Force-stop a VM (like pulling the power). Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @mcp.tool()
    def shutdown_vm(ctx: Context, node: str, vmid: int, timeout: int = 60) -> str:
        """Gracefully shutdown a VM via ACPI. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
            timeout: Seconds to wait before force-stop (default 60)
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.shutdown.post(timeout=timeout)
        return _status_response("shutting_down", upid)

    @mcp.tool()
    def reboot_vm(ctx: Context, node: str, vmid: int) -> str:
        """Reboot a VM via ACPI. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @mcp.tool()
    def suspend_vm(ctx: Context, node: str, vmid: int) -> str:
        """Suspend a VM. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.suspend.post()
        return _status_response("suspending", upid)

    @mcp.tool()
    def resume_vm(ctx: Context, node: str, vmid: int) -> str:
        """Resume a suspended VM. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.resume.post()
        return _status_response("resuming", upid)

    @mcp.tool()
    def clone_vm(
        ctx: Context, node: str, vmid: int, newid: int, name: str | None = None, full: bool = True
    ) -> str:
        """Clone a VM. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: Source VM ID
            newid: New VM ID for the clone
            name: Name for the cloned VM
            full: Full clone (true) or linked clone (false)
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        # Proxmox API expects 0/1 for boolean params, not true/false.
        params: dict[str, Any] = {"newid": newid, "full": int(full)}
        if name:
            params["name"] = name
        upid = pve.nodes(node).qemu(vmid).clone.post(**params)
        return _status_response("cloning", upid)

    @mcp.tool()
    def create_vm_snapshot(
        ctx: Context, node: str, vmid: int, snapname: str, description: str = ""
    ) -> str:
        """Create a snapshot of a VM. Requires PROXMOX_RISK_LEVEL=lifecycle.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name
            description: Optional description
        """
        _tier(ctx, "lifecycle")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot.post(
            snapname=snapname, description=description
        )
        return _status_response("creating_snapshot", upid)

    # ── Destructive (PROXMOX_RISK_LEVEL=all) ──

    @mcp.tool()
    def delete_vm_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Delete a VM snapshot. Requires PROXMOX_RISK_LEVEL=all.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name to delete
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).delete()
        return _status_response("deleting_snapshot", upid)

    @mcp.tool()
    def rollback_vm_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Rollback a VM to a snapshot. Requires PROXMOX_RISK_LEVEL=all.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name to rollback to
        """
        _tier(ctx, "all")
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).rollback.post()
        return _status_response("rolling_back", upid)
