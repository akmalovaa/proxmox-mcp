"""The call-time tier guard, as it is actually reached: through the gate wrapper.

Registration is what keeps an elevated tool out of the tool list; this is the
second check that stops it running if it ever gets listed anyway — for instance
when the process is started at one tier and PROXMOX_RISK_LEVEL says another.
"""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from proxmox_mcp.config import RiskLevel, Settings
from proxmox_mcp.tools._common import _tier
from tests.conftest import RecordingProxmox, build_server, call_tool, make_context

VM = {"node": "pve", "vmid": 101}
SNAP = VM | {"snapname": "snap1"}


def _bare_ctx(level: RiskLevel) -> Any:
    settings = Settings(host="x", token_name="t", token_value="v", risk_level=level)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = MagicMock(settings=settings)
    return ctx


@pytest.mark.parametrize(
    "level,required,should_pass",
    [
        ("read", "lifecycle", False),
        ("read", "all", False),
        ("lifecycle", "lifecycle", True),
        ("lifecycle", "all", False),
        ("all", "lifecycle", True),
        ("all", "all", True),
    ],
)
def test_tier_enforcement(level: RiskLevel, required: str, should_pass: bool) -> None:
    ctx = _bare_ctx(level)
    if should_pass:
        _tier(ctx, required, "some_tool")  # type: ignore[arg-type]
    else:
        with pytest.raises(PermissionError):
            _tier(ctx, required, "some_tool")  # type: ignore[arg-type]


def test_denial_message_includes_tool_name_and_required_tier() -> None:
    with pytest.raises(PermissionError, match="stop_vm.*lifecycle.*read"):
        _tier(_bare_ctx("read"), "lifecycle", "stop_vm")


@pytest.mark.parametrize(
    "tool,args,required",
    [
        ("start_vm", VM, "lifecycle"),
        ("stop_container", VM, "lifecycle"),
        ("delete_vm_snapshot", SNAP, "all"),
        ("rollback_container_snapshot", SNAP, "all"),
    ],
)
def test_registered_tools_are_guarded_at_call_time(
    proxmox: RecordingProxmox, tool: str, args: dict[str, Any], required: str
) -> None:
    """Registered at `all`, but the running settings say `read`."""
    mcp = build_server("all")
    with pytest.raises(ToolError, match=f"{tool}.*{required}"):
        call_tool(mcp, tool, args, make_context(proxmox, settings_level="read"))
    assert proxmox.calls == [], "a denied call must not reach the Proxmox API"


def test_read_tools_are_not_guarded(proxmox: RecordingProxmox) -> None:
    """A read tool carries no guard at all — nothing to deny, nothing to log."""
    mcp = build_server("all")
    call_tool(mcp, "list_nodes", {}, make_context(proxmox, settings_level="read"))
    assert proxmox.last["path"] == "nodes"


def test_logs_allow_and_deny(
    proxmox: RecordingProxmox, caplog: pytest.LogCaptureFixture
) -> None:
    """The decision is only auditable if it reaches stderr under the real name."""
    mcp = build_server("all")
    with caplog.at_level(logging.INFO, logger="proxmox_mcp.policy"):
        call_tool(mcp, "start_vm", VM, make_context(proxmox, settings_level="all"))
        with pytest.raises(ToolError):
            call_tool(mcp, "start_vm", VM, make_context(proxmox, settings_level="read"))

    messages = [r.getMessage() for r in caplog.records]
    assert any("ALLOW" in m and "tool=start_vm" in m for m in messages)
    assert any("DENY" in m and "tool=start_vm" in m for m in messages)
