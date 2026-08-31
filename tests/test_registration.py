import asyncio

import pytest
from mcp.types import ToolAnnotations

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools._common import (
    DESTRUCTIVE,
    LIFECYCLE,
    READ_ONLY,
    _required_tier,
)
from tests.conftest import build_server

READ_TOOLS = {
    # nodes (10)
    "list_nodes", "get_node_status", "get_node_networks", "get_node_disks",
    "get_node_services", "get_node_updates", "get_node_rrd_data",
    "get_node_tasks", "get_task_status", "get_task_log",
    # vms read (6)
    "list_vms", "get_vm_status", "get_vm_config", "get_vm_network_interfaces",
    "get_vm_rrd_data", "list_vm_snapshots",
    # containers read (6)
    "list_containers", "get_container_status", "get_container_config",
    "get_container_interfaces", "get_container_rrd_data", "list_container_snapshots",
    # storage (2)
    "list_storage", "get_storage_content",
    # cluster (7)
    "get_cluster_status", "get_cluster_resources", "get_cluster_backups",
    "get_ha_status", "list_pools", "get_cluster_log", "get_next_vmid",
}

LIFECYCLE_TOOLS = {
    # vms (9)
    "start_vm", "stop_vm", "shutdown_vm", "reboot_vm", "suspend_vm", "resume_vm",
    "clone_vm", "migrate_vm", "create_vm_snapshot",
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
    tools = asyncio.run(build_server(risk_level).list_tools())
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
    assert len(_registered_tool_names("read")) == 31
    assert len(_registered_tool_names("lifecycle")) == 45
    assert len(_registered_tool_names("all")) == 49


def test_read_level_hides_destructive_tools() -> None:
    names = _registered_tool_names("read")
    assert not (names & DESTRUCTIVE_TOOLS)
    assert not (names & LIFECYCLE_TOOLS)


def test_every_tool_is_described_and_annotated() -> None:
    """Descriptions and titles are what the model picks tools by."""
    tools = asyncio.run(build_server("all").list_tools())
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert tool.title, f"{tool.name} has no title"
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        assert tool.annotations.open_world_hint, f"{tool.name} must be open-world"
        for param, schema in tool.input_schema.get("properties", {}).items():
            assert schema.get("description"), f"{tool.name}.{param} has no description"


@pytest.mark.parametrize(
    "annotations,expected",
    [
        (READ_ONLY, "read"),
        (LIFECYCLE, "lifecycle"),
        (DESTRUCTIVE, "all"),
        # Inferred from the fields, so a hand-built annotation lands correctly
        # instead of falling through to `read` the way identity matching did.
        (ToolAnnotations(read_only_hint=True), "read"),
        (ToolAnnotations(destructive_hint=True), "all"),
        (ToolAnnotations(read_only_hint=False, destructive_hint=False), "lifecycle"),
    ],
)
def test_required_tier_reads_annotation_fields(
    annotations: ToolAnnotations, expected: str
) -> None:
    assert _required_tier(annotations) == expected


def test_unannotated_tool_is_rejected() -> None:
    """Silently defaulting to `read` would expose an elevated tool at every tier."""
    with pytest.raises(ValueError, match="must pass annotations"):
        _required_tier(None)
