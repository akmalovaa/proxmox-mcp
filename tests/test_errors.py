"""Failures must reach the model as readable text, not a bare tool name.

The SDK only forwards the message of a ``ToolError``; anything else becomes an
``UnexpectedToolError`` whose text is withheld from the client (see
``mcp.server.mcpserver.exceptions``). Untranslated, a Proxmox 403 or a dead host
would arrive as nothing but ``Error executing tool <name>``.
"""

import pytest
import requests.exceptions as rex
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from proxmoxer.core import AuthenticationError, ResourceException

from tests.conftest import RecordingProxmox, build_server, call_tool, make_context

VM = {"node": "pve", "vmid": 101}


def _error_message(proxmox: RecordingProxmox, exc: Exception) -> str:
    proxmox.fail_with(exc)
    mcp = build_server("all")
    with pytest.raises(ToolError) as excinfo:
        call_tool(mcp, "list_nodes", {}, make_context(proxmox))
    # UnexpectedToolError subclasses ToolError but drops the text on the floor.
    assert not isinstance(excinfo.value, UnexpectedToolError)
    return str(excinfo.value)


@pytest.mark.parametrize(
    "exc,expected",
    [
        (ResourceException(401, "Unauthorized", ""), "privileges"),
        (ResourceException(403, "Forbidden", "permission denied"), "privileges"),
        (ResourceException(404, "Not Found", ""), "list_nodes"),
        (ResourceException(501, "Not Implemented", ""), "guest agent"),
        (ResourceException(500, "Internal Server Error", "boom"), "Proxmox API error"),
        (AuthenticationError("Couldn't authenticate user"), "PROXMOX_TOKEN_VALUE"),
        (rex.SSLError("bad cert"), "PROXMOX_VERIFY_SSL"),
        (rex.ConnectTimeout("timed out"), "Cannot reach Proxmox"),
        (rex.ConnectionError("refused"), "Cannot reach Proxmox"),
        (rex.ReadTimeout("slow"), "did not answer in time"),
    ],
)
def test_failures_are_translated(
    proxmox: RecordingProxmox, exc: Exception, expected: str
) -> None:
    assert expected in _error_message(proxmox, exc)


def test_connection_errors_name_the_host(proxmox: RecordingProxmox) -> None:
    """The model should be able to tell which host is unreachable."""
    assert "pve.test:8006" in _error_message(proxmox, rex.ConnectTimeout("timed out"))


def test_unknown_failures_keep_their_type_and_text(proxmox: RecordingProxmox) -> None:
    assert "RuntimeError: something odd" in _error_message(
        proxmox, RuntimeError("something odd")
    )


def test_tier_denial_reaches_the_model(proxmox: RecordingProxmox) -> None:
    """The call-time guard is useless if its reason never leaves the server."""
    mcp = build_server("all")
    ctx = make_context(proxmox, settings_level="read")

    with pytest.raises(ToolError) as excinfo:
        call_tool(mcp, "start_vm", VM, ctx)

    assert not isinstance(excinfo.value, UnexpectedToolError)
    message = str(excinfo.value)
    assert "start_vm" in message
    assert "PROXMOX_RISK_LEVEL=lifecycle" in message
    assert "current: read" in message
    assert proxmox.calls == [], "denied call must not reach the Proxmox API"
