"""Credential handling, with a scrubbed environment.

Without the scrub these tests would pass or fail depending on whether the
developer running them happens to have PROXMOX_* exported.
"""

import pytest

from proxmox_mcp.config import Settings, get_redact_secrets, get_risk_level, get_tools_allowlist

TOKEN = {"token_name": "mcp", "token_value": "secret"}


@pytest.fixture(autouse=True)
def _scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(__import__("os").environ):
        if name.startswith("PROXMOX_"):
            monkeypatch.delenv(name, raising=False)


def test_token_auth_is_preferred() -> None:
    kwargs = Settings(host="pve", **TOKEN).get_proxmoxer_kwargs()
    assert kwargs["token_name"] == "mcp"
    assert "password" not in kwargs
    assert kwargs["timeout"] == 15


def test_password_auth_falls_back_to_the_https_backend() -> None:
    kwargs = Settings(host="pve", password="hunter2").get_proxmoxer_kwargs()
    assert kwargs["password"] == "hunter2"
    assert kwargs["backend"] == "https"


@pytest.mark.parametrize("half", [{"token_name": "mcp"}, {"token_value": "secret"}])
def test_half_a_token_pair_is_rejected(half: dict[str, str]) -> None:
    """It used to fall through to password auth — usually root@pam, i.e. silently
    more privilege than the token was meant to carry."""
    with pytest.raises(ValueError, match="PROXMOX_TOKEN_"):
        Settings(host="pve", password="hunter2", **half)


def test_no_credentials_at_all_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be set"):
        Settings(host="pve")


def test_both_credentials_warns_and_uses_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="proxmox_mcp.config"):
        settings = Settings(host="pve", password="hunter2", **TOKEN)
    assert "using the token" in caplog.text
    assert "password" not in settings.get_proxmoxer_kwargs()


def test_disabled_tls_verification_is_announced(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="proxmox_mcp.config"):
        Settings(host="pve", **TOKEN)
    assert "PROXMOX_VERIFY_SSL=false" in caplog.text


def test_timeout_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROXMOX_TIMEOUT", "45")
    assert Settings(host="pve", **TOKEN).get_proxmoxer_kwargs()["timeout"] == 45


def test_risk_level_defaults_to_read_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_risk_level() == "read"
    monkeypatch.setenv("PROXMOX_RISK_LEVEL", "ALL")
    assert get_risk_level() == "all"
    monkeypatch.setenv("PROXMOX_RISK_LEVEL", "root")
    with pytest.raises(ValueError, match="PROXMOX_RISK_LEVEL"):
        get_risk_level()


def test_allowlist_is_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """None and the empty set mean different things: no allowlist vs. no tools."""
    assert get_tools_allowlist() is None
    monkeypatch.setenv("PROXMOX_TOOLS_ALLOW", " list_nodes , list_vms ")
    assert get_tools_allowlist() == frozenset({"list_nodes", "list_vms"})


def test_redaction_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_redact_secrets() is True
    monkeypatch.setenv("PROXMOX_REDACT_SECRETS", "0")
    assert get_redact_secrets() is False
