"""What leaves the server: secrets masked, inventory rows trimmed.

Both are seams every tool passes through, so a regression here is a regression
everywhere at once.
"""

import json
from typing import Any

import pytest

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
