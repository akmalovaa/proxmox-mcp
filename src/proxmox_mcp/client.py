import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from proxmoxer import ProxmoxAPI

from proxmox_mcp.config import Settings


class AppContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._proxmox: ProxmoxAPI | None = None
        # The SDK runs sync tool bodies on worker threads (anyio.to_thread), so
        # concurrent first calls would otherwise each build their own ProxmoxAPI —
        # two logins under password auth.
        self._lock = threading.Lock()

    @property
    def proxmox(self) -> ProxmoxAPI:
        if self._proxmox is None:
            with self._lock:
                if self._proxmox is None:
                    self._proxmox = ProxmoxAPI(**self.settings.get_proxmoxer_kwargs())
        return self._proxmox


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    yield AppContext(Settings())  # type: ignore[call-arg]
