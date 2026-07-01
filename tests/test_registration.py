import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools import register_all

READ_TOOLS = {
    # nodes (7)
    "list_nodes", "get_node_status", "get_node_networks", "get_node_disks",
    "get_node_tasks", "get_task_status", "get_task_log",
    # vms read (4)
    "list_vms", "get_vm_status", "get_vm_config", "list_vm_snapshots",
    # containers read (4)
    "list_containers", "get_container_status", "get_container_config",
    "list_container_snapshots",
    # storage (2)
    "list_storage", "get_storage_content",
    # cluster (4)
    "get_cluster_status", "get_cluster_resources", "get_cluster_backups",
    "get_next_vmid",
}

LIFECYCLE_TOOLS = {
    # vms (8)
    "start_vm", "stop_vm", "shutdown_vm", "reboot_vm", "suspend_vm", "resume_vm",
    "clone_vm", "create_vm_snapshot",
    # containers (5)
    "start_container", "stop_container", "shutdown_container", "reboot_container",
    "create_container_snapshot",
}

DESTRUCTIVE_TOOLS = {
    # vms (2)
    "delete_vm_snapshot", "rollback_vm_snapshot",
    # containers (2)
    "delete_container_snapshot", "rollback_container_snapshot",
}


def _registered_tool_names(risk_level: RiskLevel) -> set[str]:
    mcp = FastMCP("test")
    register_all(mcp, risk_level)
    tools = asyncio.run(mcp.list_tools())
    return {t.name for t in tools}


@pytest.mark.parametrize(
    "risk_level,expected",
    [
        ("read", READ_TOOLS),
        ("lifecycle", READ_TOOLS | LIFECYCLE_TOOLS),
        ("all", READ_TOOLS | LIFECYCLE_TOOLS | DESTRUCTIVE_TOOLS),
    ],
)
def test_tools_registered_per_tier(risk_level: RiskLevel, expected: set[str]) -> None:
    assert _registered_tool_names(risk_level) == expected


def test_tool_counts_per_tier() -> None:
    assert len(_registered_tool_names("read")) == 21
    assert len(_registered_tool_names("lifecycle")) == 34
    assert len(_registered_tool_names("all")) == 38


def test_read_level_hides_destructive_tools() -> None:
    names = _registered_tool_names("read")
    assert not (names & DESTRUCTIVE_TOOLS)
    assert not (names & LIFECYCLE_TOOLS)
