"""The lazy connection is built from worker threads, so it must be built once."""

import threading
import time
from typing import Any
from unittest.mock import patch

from proxmox_mcp.client import AppContext
from proxmox_mcp.config import Settings


def _settings() -> Settings:
    return Settings(host="pve.test", token_name="t", token_value="v")


def test_concurrent_first_access_builds_one_connection() -> None:
    """The SDK runs sync tool bodies on anyio worker threads: several tool calls can
    race on the first access, and under password auth each extra build is a login."""
    built = []

    def slow_build(**kwargs: Any) -> object:
        # Widen the window an unsynchronized check-then-create would fall through.
        time.sleep(0.05)
        client = object()
        built.append(client)
        return client

    app = AppContext(_settings())
    seen: list[object] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        seen.append(app.proxmox)

    with patch("proxmox_mcp.client.ProxmoxAPI", side_effect=slow_build):
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(built) == 1
    assert len(seen) == 8
    assert all(client is built[0] for client in seen)


def test_connection_is_reused_across_accesses() -> None:
    app = AppContext(_settings())
    with patch("proxmox_mcp.client.ProxmoxAPI", side_effect=lambda **kw: object()) as api:
        first = app.proxmox
        second = app.proxmox
    assert first is second
    assert api.call_count == 1


def test_connection_is_not_built_until_first_use() -> None:
    """The server must start even when Proxmox is unreachable."""
    with patch("proxmox_mcp.client.ProxmoxAPI") as api:
        AppContext(_settings())
    api.assert_not_called()
