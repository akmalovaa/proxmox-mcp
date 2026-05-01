import asyncio

from mcp.server.fastmcp import FastMCP

from proxmox_mcp.tools import register_all

EXPECTED_TOOLS = {
    # nodes (7)
    "list_nodes", "get_node_status", "get_node_networks", "get_node_disks",
    "get_node_tasks", "get_task_status", "get_task_log",
    # vms (14)
    "list_vms", "get_vm_status", "get_vm_config", "list_vm_snapshots",
    "start_vm", "stop_vm", "shutdown_vm", "reboot_vm", "suspend_vm", "resume_vm",
    "clone_vm", "create_vm_snapshot", "delete_vm_snapshot", "rollback_vm_snapshot",
    # containers (11)
    "list_containers", "get_container_status", "get_container_config",
    "list_container_snapshots", "start_container", "stop_container",
    "shutdown_container", "reboot_container", "create_container_snapshot",
    "delete_container_snapshot", "rollback_container_snapshot",
    # storage (4)
    "list_storage", "get_storage_content", "download_iso", "delete_iso",
    # cluster (4)
    "get_cluster_status", "get_cluster_resources", "get_cluster_backups",
    "get_next_vmid",
}


def _registered_tool_names() -> set[str]:
    mcp = FastMCP("test")
    register_all(mcp)
    tools = asyncio.run(mcp.list_tools())
    return {t.name for t in tools}


def test_all_expected_tools_registered() -> None:
    assert _registered_tool_names() == EXPECTED_TOOLS


def test_tool_count_is_40() -> None:
    assert len(_registered_tool_names()) == 40
