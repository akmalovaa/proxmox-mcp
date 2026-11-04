"""What leaves the server: secrets masked, inventory rows trimmed.

Both are seams every tool passes through, so a regression here is a regression
everywhere at once.
"""

import json
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from proxmox_mcp.tools._common import GUEST_FIELDS, _compact, _json
from tests.conftest import RecordingProxmox, build_server, call_tool, make_context

VM_CONFIG = {
    "name": "web-01",
    "cores": 2,
    "cipassword": "$5$rounds=5000$abcdefgh$hash",
    "sshkeys": "ssh-ed25519%20AAAAC3Nz...%20me%40host",
    "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0",
    "snapshots": [{"name": "pre-upgrade", "cipassword": "$5$other"}],
}


def _loads(result: str) -> Any:
    return json.loads(result)


def test_secrets_are_masked_by_default() -> None:
    out = _loads(_json(VM_CONFIG))
    assert out["cipassword"] == "***redacted***"
    assert out["sshkeys"] == "***redacted***"
    # The key survives, so the model can still see that cloud-init is configured.
    assert "cipassword" in out
    assert out["name"] == "web-01"
    assert out["net0"] == VM_CONFIG["net0"]


def test_redaction_reaches_nested_values() -> None:
    out = _loads(_json(VM_CONFIG))
    assert out["snapshots"][0]["cipassword"] == "***redacted***"
    assert out["snapshots"][0]["name"] == "pre-upgrade"


def test_redaction_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXMOX_REDACT_SECRETS", "false")
    assert _loads(_json(VM_CONFIG))["cipassword"] == VM_CONFIG["cipassword"]


def test_json_stays_compact() -> None:
    assert " " not in _json({"a": 1, "b": [2, 3]})


def test_compact_keeps_only_known_fields() -> None:
    rows = [{"vmid": 101, "name": "a", "netin": 999, "pressurecpusome": 0.1}]
    assert _compact(rows, GUEST_FIELDS) == [{"vmid": 101, "name": "a"}]


# One fat /cluster/resources row, as Proxmox actually sends it.
ROW = {
    "id": "qemu/101", "type": "qemu", "vmid": 101, "name": "web-01",
    "node": "pve", "status": "running", "uptime": 900,
    "cpu": 0.02, "maxcpu": 2, "mem": 1 << 30, "maxmem": 2 << 30,
    "netin": 123456, "netout": 654321, "diskread": 1, "diskwrite": 2,
    "pressurecpusome": 0.0, "pressureiofull": 0.0,
}


def _inventory() -> RecordingProxmox:
    proxmox = RecordingProxmox()
    proxmox.returns([dict(ROW)])
    return proxmox


@pytest.mark.parametrize("tool", ["list_vms", "get_cluster_resources"])
def test_listings_are_projected_by_default(tool: str) -> None:
    proxmox = _inventory()
    mcp = build_server("read")
    rows = _loads(call_tool(mcp, tool, {}, make_context(proxmox)).content[0].text)
    assert rows[0]["vmid"] == 101
    assert rows[0]["status"] == "running"
    assert "netin" not in rows[0]
    assert "pressureiofull" not in rows[0]


@pytest.mark.parametrize("tool", ["list_vms", "get_cluster_resources"])
def test_verbose_returns_every_field(tool: str) -> None:
    proxmox = _inventory()
    mcp = build_server("read")
    result = call_tool(mcp, tool, {"verbose": True}, make_context(proxmox))
    rows = _loads(result.content[0].text)
    assert rows[0] == ROW


# A short */rrddata series as Proxmox sends it: one row per step, every metric in
# every row, and a step with no data reduced to its timestamp.
SERIES = [
    {"time": 60, "cpu": 0.1, "mem": 100, "netin": 10, "pressurecpusome": 0},
    {"time": 120, "cpu": 0.3, "mem": 300, "netin": 30, "pressurecpusome": 0},
    {"time": 180, "cpu": 0.9, "mem": 200, "netin": 20, "pressurecpusome": 0},
    {"time": 240},
]
RRD_TOOLS = [
    ("get_node_rrd_data", {"node": "pve"}),
    ("get_vm_rrd_data", {"node": "pve", "vmid": 101}),
    ("get_container_rrd_data", {"node": "pve", "vmid": 102}),
]
RRD_IDS = [name for name, _ in RRD_TOOLS]


def _rrd_call(name: str, base: dict[str, Any], args: dict[str, Any]) -> tuple[Any, Any]:
    proxmox = RecordingProxmox()
    proxmox.returns([dict(row) for row in SERIES])
    result = call_tool(build_server("read"), name, base | args, make_context(proxmox))
    return _loads(result.content[0].text), proxmox.last["params"]


@pytest.mark.parametrize("name,base", RRD_TOOLS, ids=RRD_IDS)
def test_rrd_series_is_untouched_by_default(name: str, base: dict[str, Any]) -> None:
    rows, _ = _rrd_call(name, base, {})
    assert rows == SERIES


@pytest.mark.parametrize("name,base", RRD_TOOLS, ids=RRD_IDS)
def test_rrd_narrowing_is_not_sent_to_proxmox(name: str, base: dict[str, Any]) -> None:
    """rrddata takes only timeframe and cf; anything else would be a 400."""
    args = {"fields": ["cpu"], "max_points": 2, "summary": True}
    _, params = _rrd_call(name, base, args)
    assert params == {"timeframe": "day", "cf": "AVERAGE"}


@pytest.mark.parametrize("name,base", RRD_TOOLS, ids=RRD_IDS)
def test_rrd_fields_keep_time_and_named_metrics(name: str, base: dict[str, Any]) -> None:
    rows, _ = _rrd_call(name, base, {"fields": ["cpu"]})
    assert rows == [
        {"time": 60, "cpu": 0.1},
        {"time": 120, "cpu": 0.3},
        {"time": 180, "cpu": 0.9},
        {"time": 240},
    ]


def test_rrd_unknown_field_names_what_is_available() -> None:
    proxmox = RecordingProxmox()
    proxmox.returns([dict(row) for row in SERIES])
    with pytest.raises(ToolError) as excinfo:
        call_tool(
            build_server("read"),
            "get_vm_rrd_data",
            {"node": "pve", "vmid": 101, "fields": ["memory"]},
            make_context(proxmox),
        )
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "['memory']" in str(excinfo.value)
    assert "cpu, mem, netin" in str(excinfo.value)


def test_rrd_fields_on_an_empty_series_is_not_an_error() -> None:
    proxmox = RecordingProxmox()
    proxmox.returns([])
    args = {"node": "pve", "fields": ["cpu"]}
    result = call_tool(build_server("read"), "get_node_rrd_data", args, make_context(proxmox))
    assert _loads(result.content[0].text) == []


def test_rrd_max_points_averages_neighbours_under_average() -> None:
    rows, _ = _rrd_call("get_vm_rrd_data", RRD_TOOLS[1][1], {"max_points": 2, "fields": ["cpu"]})
    assert rows == [{"time": 60, "cpu": pytest.approx(0.2)}, {"time": 180, "cpu": 0.9}]


def test_rrd_max_points_keeps_spikes_under_max() -> None:
    args = {"max_points": 1, "cf": "MAX", "fields": ["cpu", "mem"]}
    rows, params = _rrd_call("get_vm_rrd_data", RRD_TOOLS[1][1], args)
    assert params["cf"] == "MAX"
    assert rows == [{"time": 60, "cpu": 0.9, "mem": 300}]


def test_rrd_max_points_above_the_sample_count_changes_nothing() -> None:
    rows, _ = _rrd_call("get_node_rrd_data", RRD_TOOLS[0][1], {"max_points": 10})
    assert rows == SERIES


def test_rrd_max_points_must_be_positive() -> None:
    with pytest.raises(ToolError):
        _rrd_call("get_node_rrd_data", RRD_TOOLS[0][1], {"max_points": 0})


@pytest.mark.parametrize("name,base", RRD_TOOLS, ids=RRD_IDS)
def test_rrd_summary_reduces_each_metric(name: str, base: dict[str, Any]) -> None:
    out, _ = _rrd_call(name, base, {"summary": True, "fields": ["cpu", "mem"]})
    assert out["samples"] == 4
    assert (out["from"], out["to"]) == (60, 240)
    assert out["fields"]["cpu"] == {
        "min": 0.1,
        "max": 0.9,
        "avg": pytest.approx(0.4333, abs=1e-4),
        "last": 0.9,
    }
    assert out["fields"]["mem"] == {"min": 100, "max": 300, "avg": 200, "last": 200}
    assert set(out["fields"]) == {"cpu", "mem"}


def test_rrd_summary_ignores_max_points() -> None:
    out, _ = _rrd_call("get_node_rrd_data", RRD_TOOLS[0][1], {"summary": True, "max_points": 1})
    assert out["samples"] == 4
    assert out["fields"]["netin"]["max"] == 30


def test_rrd_summary_of_an_empty_series() -> None:
    proxmox = RecordingProxmox()
    proxmox.returns([])
    args = {"node": "pve", "summary": True}
    result = call_tool(build_server("read"), "get_node_rrd_data", args, make_context(proxmox))
    assert _loads(result.content[0].text) == {
        "samples": 0, "from": None, "to": None, "fields": {}
    }
