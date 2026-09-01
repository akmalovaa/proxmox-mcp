"""The Sentry hook: silent unless SENTRY_DSN is set, and never fatal."""

import importlib
import logging
import sys
from typing import Any

import pytest
import requests.exceptions as rex
from mcp.server.mcpserver.exceptions import ToolError

from proxmox_mcp.telemetry import setup_sentry
from tests.conftest import RecordingProxmox, build_server, call_tool, make_context

DSN = "https://public@sentry.invalid/1"

_SENTRY_ENV = (
    "SENTRY_DSN",
    "SENTRY_TRACES_SAMPLE_RATE",
    "SENTRY_SEND_DEFAULT_PII",
    "SENTRY_RELEASE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real SENTRY_DSN in the developer's shell must not reach the tests."""
    for name in _SENTRY_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def init_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record the options ``setup_sentry`` builds without starting a real client."""
    import sentry_sdk

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    return calls


def test_without_a_dsn_sentry_is_never_initialised(init_calls: list[dict[str, Any]]) -> None:
    assert setup_sentry("2.1.1") is False
    assert init_calls == []


def test_a_dsn_enables_the_mcp_integration(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    from sentry_sdk.integrations.mcp import MCPIntegration

    monkeypatch.setenv("SENTRY_DSN", DSN)

    assert setup_sentry("2.1.1") is True

    (options,) = init_calls
    assert options["dsn"] == DSN
    assert any(isinstance(i, MCPIntegration) for i in options["integrations"])


def test_tool_arguments_stay_out_of_sentry_by_default(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    """PII carries tool inputs and results — get_vm_config alone leaks ssh keys."""
    monkeypatch.setenv("SENTRY_DSN", DSN)

    setup_sentry(None)

    assert init_calls[0]["send_default_pii"] is False


def test_pii_can_be_switched_on(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setenv("SENTRY_SEND_DEFAULT_PII", "true")

    setup_sentry(None)

    assert init_calls[0]["send_default_pii"] is True


def test_traces_are_fully_sampled_by_default(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)

    setup_sentry(None)

    assert init_calls[0]["traces_sample_rate"] == 1.0


def test_traces_sample_rate_comes_from_the_env(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")

    setup_sentry(None)

    assert init_calls[0]["traces_sample_rate"] == 0.25


def test_an_unparsable_sample_rate_warns_instead_of_killing_the_server(
    monkeypatch: pytest.MonkeyPatch,
    init_calls: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "half")

    with caplog.at_level(logging.WARNING, logger="proxmox_mcp.telemetry"):
        assert setup_sentry(None) is True

    assert init_calls[0]["traces_sample_rate"] == 1.0
    assert any("SENTRY_TRACES_SAMPLE_RATE" in r.getMessage() for r in caplog.records)


def test_the_release_is_tagged_with_the_package_version(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)

    setup_sentry("2.1.1")

    assert init_calls[0]["release"] == "proxmox-ve-mcp@2.1.1"


def test_an_explicit_sentry_release_wins(
    monkeypatch: pytest.MonkeyPatch, init_calls: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setenv("SENTRY_RELEASE", "proxmox-ve-mcp@from-ci")

    setup_sentry("2.1.1")

    assert init_calls[0]["release"] == "proxmox-ve-mcp@from-ci"


def test_a_missing_sentry_sdk_does_not_stop_the_server(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """sentry-sdk is an optional extra, so a DSN alone is no guarantee it is installed."""
    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)

    with caplog.at_level(logging.WARNING, logger="proxmox_mcp.telemetry"):
        assert setup_sentry("2.1.1") is False

    assert any("sentry-sdk" in r.getMessage() for r in caplog.records)


def test_the_server_module_initialises_sentry_before_building_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCPIntegration instruments by patching Server.__init__ at init() time.

    An MCPServer constructed before that patch lands carries no Sentry middleware
    and reports nothing — a failure mode invisible to every other test here.
    """
    import sentry_sdk
    from mcp.server.lowlevel import Server

    def fake_init(**kwargs: Any) -> None:
        """The one thing real init() does that matters here: install the patches."""
        for integration in kwargs["integrations"]:
            integration.setup_once()

    monkeypatch.setenv("SENTRY_DSN", DSN)
    monkeypatch.setattr(sentry_sdk, "init", fake_init)
    original_server_init = Server.__init__

    server = importlib.import_module("proxmox_mcp.server")
    try:
        importlib.reload(server)
        middleware = server.mcp._lowlevel_server.middleware
        assert any(getattr(m, "__name__", "") == "_sentry_middleware" for m in middleware)
    finally:
        Server.__init__ = original_server_init  # type: ignore[method-assign]
        monkeypatch.undo()
        importlib.reload(server)


def _events_for(
    proxmox: RecordingProxmox, tool: str, args: dict[str, Any], level: str
) -> list[Any]:
    """Run one tool against a real Sentry client that keeps its envelopes in memory."""
    import sentry_sdk
    from sentry_sdk.transport import Transport

    events: list[Any] = []

    class Recorder(Transport):
        def capture_envelope(self, envelope: Any) -> None:
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    with sentry_sdk.isolation_scope() as scope:
        scope.set_client(
            sentry_sdk.Client(dsn=DSN, transport=Recorder(), default_integrations=False)
        )
        with pytest.raises(ToolError):
            call_tool(build_server("all"), tool, args, make_context(proxmox, settings_level=level))
    return events


def test_a_failing_tool_becomes_a_sentry_issue(proxmox: RecordingProxmox) -> None:
    """MCPIntegration alone reports nothing: the SDK turns a tool exception into an
    isError result inside its own handler (mcpserver/server.py), below the middleware.
    """
    proxmox.fail_with(rex.ConnectionError("refused"))

    events = _events_for(proxmox, "list_nodes", {}, "all")

    raised = [v["type"] for e in events for v in e.get("exception", {}).get("values", [])]
    assert "ConnectionError" in raised


def test_a_risk_level_denial_is_not_reported(proxmox: RecordingProxmox) -> None:
    """A denied call is the policy working, not a fault — issues would be noise."""
    events = _events_for(proxmox, "start_vm", {"node": "pve", "vmid": 101}, "read")

    assert events == []
