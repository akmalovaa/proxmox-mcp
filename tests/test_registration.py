import asyncio

import pytest
from mcp.types import ToolAnnotations

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools._common import (
    DESTRUCTIVE,
    LIFECYCLE,
    READ_ONLY,
    _check_annotations,
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
    # server (1)
    "get_server_info",
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

# Annotated destructive, but admitted at the lifecycle tier: a force-stop loses
# whatever the guest had in flight, which the client must be told, while the
# operator still expects it under `lifecycle`.
DESTRUCTIVE_ANNOTATION_TOOLS = DESTRUCTIVE_TOOLS | {"stop_vm", "stop_container"}


def _tool_names(risk_level: RiskLevel) -> set[str]:
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
    assert _tool_names(risk_level) == expected


def test_tool_counts_per_tier() -> None:
    assert len(_tool_names("read")) == 32
    assert len(_tool_names("lifecycle")) == 46
    assert len(_tool_names("all")) == 50


def test_read_level_hides_destructive_tools() -> None:
    names = _tool_names("read")
    assert not (names & DESTRUCTIVE_TOOLS)
    assert not (names & LIFECYCLE_TOOLS)


def test_tool_list_order_is_deterministic() -> None:
    """Clients cache the tool list and LLM prompt caches key on it, so the order
    must not depend on anything that varies between processes."""
    first = [t.name for t in asyncio.run(build_server("all").list_tools())]
    second = [t.name for t in asyncio.run(build_server("all").list_tools())]
    assert first == second
    assert len(first) == len(set(first))


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


def test_annotations_are_independent_of_the_tier() -> None:
    """The two matrices are checked separately on purpose: a tool's admission tier
    is the operator's policy, its annotations are what the client is told."""
    tools = {t.name: t for t in asyncio.run(build_server("all").list_tools())}

    for name in READ_TOOLS:
        assert tools[name].annotations.read_only_hint is True, name

    for name in LIFECYCLE_TOOLS | DESTRUCTIVE_TOOLS:
        assert tools[name].annotations.read_only_hint is False, name

    for name, tool in tools.items():
        expected = name in DESTRUCTIVE_ANNOTATION_TOOLS
        assert bool(tool.annotations.destructive_hint) is expected, name


@pytest.mark.parametrize(
    "tier,annotations",
    [
        ("read", READ_ONLY),
        ("lifecycle", LIFECYCLE),
        ("lifecycle", DESTRUCTIVE),  # force-stop: destructive, but lifecycle-tier
        ("all", DESTRUCTIVE),
    ],
)
def test_valid_tier_annotation_pairs(tier: str, annotations: ToolAnnotations) -> None:
    _check_annotations(tier, annotations)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "tier,annotations,match",
    [
        (None, None, "must pass annotations"),
        ("lifecycle", READ_ONLY, "cannot require tier"),
        ("all", ToolAnnotations(), "must set read_only_hint=False"),
    ],
)
def test_invalid_tier_annotation_pairs(tier: str, annotations: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _check_annotations(tier or "read", annotations)  # type: ignore[arg-type]


def test_allowlist_narrows_within_the_tier() -> None:
    allow = frozenset({"list_nodes", "list_vms", "start_vm"})
    assert _tool_names_with_allow("read", allow) == {"list_nodes", "list_vms"}
    assert _tool_names_with_allow("all", allow) == set(allow)


def test_allowlist_rejects_unknown_names() -> None:
    """A typo would otherwise silently amputate the tool list."""
    with pytest.raises(ValueError, match="list_noeds"):
        _tool_names_with_allow("all", frozenset({"list_nodes", "list_noeds"}))


def _tool_names_with_allow(risk_level: RiskLevel, allow: frozenset[str]) -> set[str]:
    tools = asyncio.run(build_server(risk_level, allow=allow).list_tools())
    return {t.name for t in tools}
