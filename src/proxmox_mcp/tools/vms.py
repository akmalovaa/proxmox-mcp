import asyncio
import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from proxmoxer import ResourceException

from proxmox_mcp.tools._common import _ctx, _elevated, _status_response


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

    # ── Elevated ──

    @mcp.tool()
    def start_vm(ctx: Context, node: str, vmid: int) -> str:
        """Start a VM. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.start.post()
        return _status_response("starting", upid)

    @mcp.tool()
    def stop_vm(ctx: Context, node: str, vmid: int) -> str:
        """Force-stop a VM (like pulling the power). Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.stop.post()
        return _status_response("stopping", upid)

    @mcp.tool()
    def shutdown_vm(ctx: Context, node: str, vmid: int, timeout: int = 60) -> str:
        """Gracefully shutdown a VM via ACPI. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
            timeout: Seconds to wait before force-stop (default 60)
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.shutdown.post(timeout=timeout)
        return _status_response("shutting_down", upid)

    @mcp.tool()
    def reboot_vm(ctx: Context, node: str, vmid: int) -> str:
        """Reboot a VM via ACPI. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.reboot.post()
        return _status_response("rebooting", upid)

    @mcp.tool()
    def suspend_vm(ctx: Context, node: str, vmid: int) -> str:
        """Suspend a VM. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.suspend.post()
        return _status_response("suspending", upid)

    @mcp.tool()
    def resume_vm(ctx: Context, node: str, vmid: int) -> str:
        """Resume a suspended VM. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID number
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).status.resume.post()
        return _status_response("resuming", upid)

    @mcp.tool()
    def clone_vm(
        ctx: Context, node: str, vmid: int, newid: int, name: str | None = None, full: bool = True
    ) -> str:
        """Clone a VM. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: Source VM ID
            newid: New VM ID for the clone
            name: Name for the cloned VM
            full: Full clone (true) or linked clone (false)
        """
        _elevated(ctx)
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
        """Create a snapshot of a VM. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name
            description: Optional description
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot.post(
            snapname=snapname, description=description
        )
        return _status_response("creating_snapshot", upid)

    @mcp.tool()
    def delete_vm_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Delete a VM snapshot. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name to delete
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).delete()
        return _status_response("deleting_snapshot", upid)

    @mcp.tool()
    def rollback_vm_snapshot(ctx: Context, node: str, vmid: int, snapname: str) -> str:
        """Rollback a VM to a snapshot. Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID
            snapname: Snapshot name to rollback to
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        upid = pve.nodes(node).qemu(vmid).snapshot(snapname).rollback.post()
        return _status_response("rolling_back", upid)

    @mcp.tool()
    async def exec_vm_command(
        ctx: Context, node: str, vmid: int, command: str, timeout_s: int = 10
    ) -> str:
        """Execute a command inside a VM via QEMU Guest Agent.

        The VM must have qemu-guest-agent running.
        Requires PROXMOX_ALLOW_ELEVATED=true.

        Args:
            node: Node name
            vmid: VM ID
            command: Shell command to execute
            timeout_s: How long to wait for completion before returning still_running (default 10)
        """
        _elevated(ctx)
        pve = _ctx(ctx).proxmox
        result = await asyncio.to_thread(
            pve.nodes(node).qemu(vmid).agent.exec.post, command=["sh", "-c", command]
        )
        pid = result.get("pid")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            await asyncio.sleep(1)
            try:
                output = await asyncio.to_thread(
                    pve.nodes(node).qemu(vmid).agent("exec-status").get, pid=pid
                )
            except ResourceException:
                continue
            if output.get("exited"):
                return json.dumps(output, indent=2)

        return json.dumps({
            "pid": pid,
            "status": "still_running",
            "note": "Command exceeded timeout_s; result is no longer retrievable via this tool.",
        })
