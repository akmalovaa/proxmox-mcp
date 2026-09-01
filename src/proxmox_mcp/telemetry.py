"""Optional Sentry reporting. Inert unless SENTRY_DSN is set."""

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _traces_sample_rate() -> float:
    raw = os.environ.get("SENTRY_TRACES_SAMPLE_RATE")
    if raw is None:
        return 1.0
    try:
        return float(raw)
    except ValueError:
        logger.warning("SENTRY_TRACES_SAMPLE_RATE is not a number (%r) — using 1.0", raw)
        return 1.0


def _release(version: str | None) -> str | None:
    return os.environ.get("SENTRY_RELEASE") or (f"proxmox-ve-mcp@{version}" if version else None)


def setup_sentry(version: str | None = None) -> bool:
    """Start Sentry if SENTRY_DSN is set, and report whether it was started.

    Call this *before* building the MCPServer: MCPIntegration instruments servers by
    patching ``mcp.server.lowlevel.Server.__init__`` from inside ``sentry_sdk.init()``,
    so a server constructed earlier is never wired up and reports nothing.

    SENTRY_ENVIRONMENT, SENTRY_RELEASE and SENTRY_DEBUG are read by sentry-sdk itself.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.mcp import MCPIntegration
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed — install the 'sentry' "
            "extra (uvx --from 'proxmox-ve-mcp[sentry]' proxmox-ve-mcp). "
            "Continuing without Sentry."
        )
        return False

    sample_rate = _traces_sample_rate()
    sentry_sdk.init(
        dsn=dsn,
        release=_release(version),
        traces_sample_rate=sample_rate,
        # PII puts tool arguments and results into span data, and get_vm_config alone
        # returns ssh keys and cipassword hashes. Opt in deliberately.
        send_default_pii=_flag("SENTRY_SEND_DEFAULT_PII"),
        integrations=[MCPIntegration()],
    )
    logger.info("Sentry enabled (traces_sample_rate=%s)", sample_rate)
    return True


def report_exception(exc: BaseException) -> None:
    """Capture a tool failure as a Sentry issue. A no-op unless Sentry is running.

    MCPIntegration cannot see these: the SDK catches a tool's exception inside its
    own call-tool handler and returns an isError result, below the middleware. The
    sys.modules lookup keeps this free — and import-free — while Sentry is off.
    """
    sentry_sdk: Any = sys.modules.get("sentry_sdk")
    if sentry_sdk is None:
        return
    sentry_sdk.capture_exception(exc)
