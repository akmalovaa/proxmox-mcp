"""Pin the Proxmox REST path every tool calls.

Proxmoxer builds URLs from attribute access, so a typo like ``status.stop`` →
``status.shutdown`` is invisible to the type checker and to a live smoke test that
only counts tools. These cases are the regression net for that.
"""

from typing import Any

import pytest

from tests.conftest import RecordingProxmox, build_server, call_tool, make_context

NODE = {"node": "pve"}
VM = {"node": "pve", "vmid": 101}
CT = {"node": "pve", "vmid": 102}
SNAP = {"snapname": "snap1"}

# (tool name, arguments, expected HTTP verb, expected path below /api2/json)
CASES: list[tuple[str, dict[str, Any], str, str]] = [
    # ── nodes ──
    ("list_nodes", {}, "get", "nodes"),
    ("get_node_status", NODE, "get", "nodes/pve/status"),
    ("get_node_networks", NODE, "get", "nodes/pve/network"),
    ("get_node_disks", NODE, "get", "nodes/pve/disks/list"),
    ("get_node_services", NODE, "get", "nodes/pve/services"),
    ("get_node_updates", NODE, "get", "nodes/pve/apt/update"),
    ("get_node_rrd_data", NODE, "get", "nodes/pve/rrddata"),
    ("get_node_tasks", NODE, "get", "nodes/pve/tasks"),
    ("get_task_status", NODE | {"upid": "UPID:x"}, "get", "nodes/pve/tasks/UPID:x/status"),
    ("get_task_log", NODE | {"upid": "UPID:x"}, "get", "nodes/pve/tasks/UPID:x/log"),
    # ── QEMU VMs ──
    ("list_vms", {}, "get", "cluster/resources"),
    ("list_vms", NODE, "get", "nodes/pve/qemu"),
    ("get_vm_status", VM, "get", "nodes/pve/qemu/101/status/current"),
    ("get_vm_config", VM, "get", "nodes/pve/qemu/101/config"),
    (
        "get_vm_network_interfaces",
        VM,
        "get",
        "nodes/pve/qemu/101/agent/network-get-interfaces",
    ),
    ("get_vm_rrd_data", VM, "get", "nodes/pve/qemu/101/rrddata"),
    ("list_vm_snapshots", VM, "get", "nodes/pve/qemu/101/snapshot"),
    ("start_vm", VM, "post", "nodes/pve/qemu/101/status/start"),
    ("stop_vm", VM, "post", "nodes/pve/qemu/101/status/stop"),
    ("shutdown_vm", VM, "post", "nodes/pve/qemu/101/status/shutdown"),
    ("reboot_vm", VM, "post", "nodes/pve/qemu/101/status/reboot"),
    ("suspend_vm", VM, "post", "nodes/pve/qemu/101/status/suspend"),
    ("resume_vm", VM, "post", "nodes/pve/qemu/101/status/resume"),
    ("clone_vm", VM | {"newid": 999}, "post", "nodes/pve/qemu/101/clone"),
    ("migrate_vm", VM | {"target": "pve2"}, "post", "nodes/pve/qemu/101/migrate"),
    ("create_vm_snapshot", VM | SNAP, "post", "nodes/pve/qemu/101/snapshot"),
    ("delete_vm_snapshot", VM | SNAP, "delete", "nodes/pve/qemu/101/snapshot/snap1"),
    (
        "rollback_vm_snapshot",
        VM | SNAP,
        "post",
        "nodes/pve/qemu/101/snapshot/snap1/rollback",
    ),
    # ── LXC containers ──
    ("list_containers", {}, "get", "cluster/resources"),
    ("list_containers", NODE, "get", "nodes/pve/lxc"),
    ("get_container_status", CT, "get", "nodes/pve/lxc/102/status/current"),
    ("get_container_config", CT, "get", "nodes/pve/lxc/102/config"),
    ("get_container_interfaces", CT, "get", "nodes/pve/lxc/102/interfaces"),
    ("get_container_rrd_data", CT, "get", "nodes/pve/lxc/102/rrddata"),
    ("list_container_snapshots", CT, "get", "nodes/pve/lxc/102/snapshot"),
    ("start_container", CT, "post", "nodes/pve/lxc/102/status/start"),
    ("stop_container", CT, "post", "nodes/pve/lxc/102/status/stop"),
    ("shutdown_container", CT, "post", "nodes/pve/lxc/102/status/shutdown"),
    ("reboot_container", CT, "post", "nodes/pve/lxc/102/status/reboot"),
    ("create_container_snapshot", CT | SNAP, "post", "nodes/pve/lxc/102/snapshot"),
    ("delete_container_snapshot", CT | SNAP, "delete", "nodes/pve/lxc/102/snapshot/snap1"),
    (
        "rollback_container_snapshot",
        CT | SNAP,
        "post",
        "nodes/pve/lxc/102/snapshot/snap1/rollback",
    ),
    # ── storage ──
    ("list_storage", {}, "get", "storage"),
    ("list_storage", NODE, "get", "nodes/pve/storage"),
    (
        "get_storage_content",
        NODE | {"storage": "local"},
        "get",
        "nodes/pve/storage/local/content",
    ),
    # ── cluster ──
    ("get_cluster_status", {}, "get", "cluster/status"),
    ("get_cluster_resources", {}, "get", "cluster/resources"),
    ("get_cluster_backups", {}, "get", "cluster/backup"),
    ("get_ha_status", {}, "get", "cluster/ha/status/current"),
    ("list_pools", {}, "get", "pools"),
    ("get_cluster_log", {}, "get", "cluster/log"),
    ("get_next_vmid", {}, "get", "cluster/nextid"),
]


@pytest.mark.parametrize("name,args,method,path", CASES, ids=[f"{c[0]}-{c[3]}" for c in CASES])
def test_tool_calls_expected_endpoint(
    proxmox: RecordingProxmox, name: str, args: dict[str, Any], method: str, path: str
) -> None:
    mcp = build_server("all")
    call_tool(mcp, name, args, make_context(proxmox))
    assert proxmox.last["method"] == method
    assert proxmox.last["path"] == path


def test_every_tool_has_an_endpoint_case() -> None:
    """A new tool must arrive with a path case, or this fails."""
    import asyncio

    registered = {t.name for t in asyncio.run(build_server("all").list_tools())}
    assert registered == {c[0] for c in CASES}


def test_boolean_params_are_sent_as_proxmox_expects(proxmox: RecordingProxmox) -> None:
    """Proxmox wants 0/1, not JSON true/false, and hyphenates with-local-disks."""
    mcp = build_server("all")
    ctx = make_context(proxmox)

    call_tool(mcp, "clone_vm", VM | {"newid": 999, "full": True}, ctx)
    assert proxmox.last["params"] == {"newid": 999, "full": 1}

    call_tool(mcp, "clone_vm", VM | {"newid": 999, "full": False, "name": "copy"}, ctx)
    assert proxmox.last["params"] == {"newid": 999, "full": 0, "name": "copy"}

    call_tool(
        mcp,
        "migrate_vm",
        VM | {"target": "pve2", "online": True, "with_local_disks": True},
        ctx,
    )
    assert proxmox.last["params"] == {"target": "pve2", "online": 1, "with-local-disks": 1}

    call_tool(mcp, "migrate_vm", VM | {"target": "pve2", "online": False}, ctx)
    assert proxmox.last["params"] == {"target": "pve2", "online": 0}

    call_tool(mcp, "get_node_tasks", NODE | {"errors_only": True}, ctx)
    assert proxmox.last["params"] == {"limit": 20, "errors": 1}

    call_tool(mcp, "get_node_tasks", NODE, ctx)
    assert proxmox.last["params"] == {"limit": 20}


def test_rrd_defaults_and_overrides(proxmox: RecordingProxmox) -> None:
    mcp = build_server("all")
    ctx = make_context(proxmox)

    call_tool(mcp, "get_node_rrd_data", NODE, ctx)
    assert proxmox.last["params"] == {"timeframe": "day", "cf": "AVERAGE"}

    call_tool(mcp, "get_vm_rrd_data", VM | {"timeframe": "week", "cf": "MAX"}, ctx)
    assert proxmox.last["params"] == {"timeframe": "week", "cf": "MAX"}


def test_cluster_log_limit_maps_to_max(proxmox: RecordingProxmox) -> None:
    """The Proxmox parameter is `max`; the tool exposes it as `limit`."""
    mcp = build_server("all")
    call_tool(mcp, "get_cluster_log", {"limit": 5}, make_context(proxmox))
    assert proxmox.last["params"] == {"max": 5}
