"""The two things a client cannot infer: what this server allows, and whether it is up."""

import json
from typing import Any

import pytest
import requests.exceptions as rex

from tests.conftest import RecordingProxmox, build_server, call_tool, make_context


def _server_info(proxmox: RecordingProxmox, risk_level: str = "read", **kw: Any) -> dict:
    mcp = build_server(risk_level, **kw)  # type: ignore[arg-type]
    result = call_tool(mcp, "get_server_info", {}, make_context(proxmox, risk_level))  # type: ignore[arg-type]
    return json.loads(result.content[0].text)


def test_reports_the_boundary_the_client_cannot_see(proxmox: RecordingProxmox) -> None:
    """At `read` the elevated tools are absent rather than refused, so a short tool
    list and a locked-down server look identical from outside."""
    info = _server_info(proxmox, "read")
    assert info["risk_level"] == "read"
    assert info["tools_registered"] == 32
    assert info["tools_available_at_all_levels"] == 50
    assert info["proxmox_host"] == "pve.test:8006"
    assert info["proxmox_auth"] == "token"
    assert info["redact_secrets"] is True
    assert info["tools_allowlist"] is None


def test_reports_an_active_allowlist(proxmox: RecordingProxmox) -> None:
    info = _server_info(proxmox, "all", allow=frozenset({"get_server_info", "list_nodes"}))
    assert info["tools_allowlist"] == ["get_server_info", "list_nodes"]
    assert info["tools_registered"] == 2


def test_answers_even_when_proxmox_is_down(proxmox: RecordingProxmox) -> None:
    """Its whole point is being answerable before anything else works."""
    proxmox.fail_with(rex.ConnectionError("refused"))
    info = _server_info(proxmox)
    assert info["proxmox_version"] is None
    assert "ConnectionError" in info["proxmox_error"]
    assert info["risk_level"] == "read"


def test_credentials_never_appear(proxmox: RecordingProxmox) -> None:
    raw = json.dumps(_server_info(proxmox))
    assert "tok-must-not-leak" not in raw
    assert "token_value" not in raw


@pytest.mark.anyio
async def test_healthz_does_not_touch_proxmox() -> None:
    """A liveness probe that fails when Proxmox is down would restart the pod in a
    loop and fix nothing, so it must not depend on Proxmox at all."""
    from unittest.mock import patch

    from proxmox_mcp.server import healthz

    with patch("proxmox_mcp.client.ProxmoxAPI") as api:
        response = await healthz(None)  # type: ignore[arg-type]
    api.assert_not_called()
    assert response.status_code == 200
    assert json.loads(response.body)["status"] == "ok"


@pytest.mark.anyio
async def test_readyz_reports_proxmox_reachability() -> None:
    from unittest.mock import MagicMock, patch

    from proxmox_mcp.server import readyz

    app = MagicMock()
    app.proxmox.version.get.return_value = {"version": "8.4.1"}
    with patch("proxmox_mcp.server.get_app_context", return_value=app):
        ok = await readyz(None)  # type: ignore[arg-type]
    assert ok.status_code == 200
    assert json.loads(ok.body)["proxmox"] == {"version": "8.4.1"}

    app.proxmox.version.get.side_effect = rex.ConnectionError("refused")
    with patch("proxmox_mcp.server.get_app_context", return_value=app):
        down = await readyz(None)  # type: ignore[arg-type]
    assert down.status_code == 503
    assert "Cannot reach Proxmox" in json.loads(down.body)["reason"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
