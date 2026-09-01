"""Transport selection and the Host/Origin validation that comes with HTTP mode.

The SDK ships DNS-rebinding protection off "for backwards compatibility", while
the spec makes rejecting a foreign Origin a MUST. Without a test the regression
is invisible: the server keeps working, it just stops protecting.
"""

import pytest

from proxmox_mcp.config import TransportConfig, get_transport_config

HTTP_ENV = {"PROXMOX_MCP_TRANSPORT": "streamable-http"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PROXMOX_MCP_TRANSPORT", "PROXMOX_MCP_HOST", "PROXMOX_MCP_PORT",
        "PROXMOX_MCP_PATH", "PROXMOX_MCP_JSON_RESPONSE",
        "PROXMOX_MCP_ALLOWED_HOSTS", "PROXMOX_MCP_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_stdio() -> None:
    config = get_transport_config()
    assert config.transport == "stdio"
    assert not config.is_http
    # Loopback, not 0.0.0.0: turning HTTP on must not by itself publish the server.
    assert config.host == "127.0.0.1"


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXMOX_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PROXMOX_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PROXMOX_MCP_PORT", "9000")
    monkeypatch.setenv("PROXMOX_MCP_PATH", "/proxmox")
    monkeypatch.setenv("PROXMOX_MCP_JSON_RESPONSE", "false")
    monkeypatch.setenv("PROXMOX_MCP_ALLOWED_HOSTS", "mcp.example.com, mcp:8000")

    config = get_transport_config()
    assert config.is_http
    assert (config.host, config.port, config.path) == ("0.0.0.0", 9000, "/proxmox")
    assert config.json_response is False
    assert config.allowed_hosts == ("mcp.example.com", "mcp:8000")


@pytest.mark.parametrize(
    "env,match",
    [
        ({"PROXMOX_MCP_TRANSPORT": "sse"}, "deprecated"),
        ({"PROXMOX_MCP_TRANSPORT": "http"}, "must be one of"),
        (HTTP_ENV | {"PROXMOX_MCP_PORT": "eight"}, "must be an integer"),
        (HTTP_ENV | {"PROXMOX_MCP_PATH": "mcp"}, "must start with"),
    ],
)
def test_invalid_settings_fail_at_startup(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], match: str
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=match):
        get_transport_config()


def test_loopback_bind_defaults_to_loopback_hosts() -> None:
    security = TransportConfig(transport="streamable-http").security()
    assert security.enable_dns_rebinding_protection
    assert "127.0.0.1:*" in security.allowed_hosts
    # Empty means "same-origin only", which is the safe default: an absent Origin
    # (curl, MCP clients) passes, every cross-origin browser request does not.
    assert security.allowed_origins == []


def test_public_bind_requires_an_explicit_host_list() -> None:
    """Otherwise `-e PROXMOX_MCP_HOST=0.0.0.0` would silently publish an
    unvalidated endpoint, which is the case the spec's MUST is about."""
    with pytest.raises(ValueError, match="PROXMOX_MCP_ALLOWED_HOSTS"):
        TransportConfig(transport="streamable-http", host="0.0.0.0").security()


def test_public_bind_with_explicit_hosts() -> None:
    security = TransportConfig(
        transport="streamable-http",
        host="0.0.0.0",
        allowed_hosts=("mcp.example.com",),
        allowed_origins=("https://mcp.example.com",),
    ).security()
    assert security.enable_dns_rebinding_protection
    assert security.allowed_hosts == ["mcp.example.com"]
    assert security.allowed_origins == ["https://mcp.example.com"]


def test_wildcard_is_an_explicit_opt_out() -> None:
    """For operators whose proxy already validates Host — but it has to be typed."""
    security = TransportConfig(
        transport="streamable-http", host="0.0.0.0", allowed_hosts=("*",)
    ).security()
    assert security.enable_dns_rebinding_protection is False


@pytest.mark.parametrize(
    "host,origin,expected",
    [
        ("127.0.0.1:8000", None, None),                     # no Origin: same-origin
        ("127.0.0.1:8000", "http://evil.example", 403),     # cross-origin browser
        ("evil.example", None, 421),                        # rebound DNS name
        ("localhost", "http://localhost:5173", 403),        # not on the allow list
    ],
)
def test_middleware_enforces_the_settings(
    host: str, origin: str | None, expected: int | None
) -> None:
    from mcp.server.transport_security import TransportSecurityMiddleware

    middleware = TransportSecurityMiddleware(
        TransportConfig(transport="streamable-http").security()
    )
    headers = {"host": host}
    if origin:
        headers["origin"] = origin

    class _Request:
        pass

    request = _Request()
    request.headers = headers  # type: ignore[attr-defined]

    import asyncio

    response = asyncio.run(middleware.validate_request(request))  # type: ignore[arg-type]
    assert (response.status_code if response else None) == expected
