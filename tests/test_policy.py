import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from proxmox_mcp.config import RiskLevel, Settings
from proxmox_mcp.tools._common import _tier


@dataclass
class _AppContext:
    proxmox: Any
    settings: Settings


def _make_ctx(level: RiskLevel) -> Any:
    settings = Settings(host="x", token_name="t", token_value="v", risk_level=level)
    app = _AppContext(proxmox=MagicMock(), settings=settings)
    request_context = MagicMock()
    request_context.lifespan_context = app
    ctx = MagicMock()
    ctx.request_context = request_context
    return ctx


def caller_lifecycle(ctx: Any) -> None:
    _tier(ctx, "lifecycle")


def caller_all(ctx: Any) -> None:
    _tier(ctx, "all")


@pytest.mark.parametrize(
    "level,fn,should_pass",
    [
        ("read", caller_lifecycle, False),
        ("read", caller_all, False),
        ("lifecycle", caller_lifecycle, True),
        ("lifecycle", caller_all, False),
        ("all", caller_lifecycle, True),
        ("all", caller_all, True),
    ],
)
def test_tier_enforcement(level: RiskLevel, fn: Any, should_pass: bool) -> None:
    ctx = _make_ctx(level)
    if should_pass:
        fn(ctx)
    else:
        with pytest.raises(PermissionError):
            fn(ctx)


def test_denial_message_includes_tool_name_and_required_tier() -> None:
    ctx = _make_ctx("read")
    with pytest.raises(PermissionError, match="caller_lifecycle.*lifecycle.*read"):
        caller_lifecycle(ctx)


def test_logs_allow_and_deny(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="proxmox_mcp.policy"):
        caller_lifecycle(_make_ctx("lifecycle"))
        with pytest.raises(PermissionError):
            caller_all(_make_ctx("lifecycle"))

    messages = [r.getMessage() for r in caplog.records]
    assert any("ALLOW" in m and "caller_lifecycle" in m for m in messages)
    assert any("DENY" in m and "caller_all" in m for m in messages)
