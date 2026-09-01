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


_context: AppContext | None = None
_context_lock = threading.Lock()


def get_app_context() -> AppContext:
    """The one ``AppContext`` for this process, built on first use.

    Shared rather than per-lifespan so the ``/readyz`` route reuses the same
    connection the tools use — in stateless HTTP mode there is no request whose
    lifespan context a health check could borrow.
    """
    global _context
    if _context is None:
        with _context_lock:
            if _context is None:
                _context = AppContext(Settings())  # type: ignore[call-arg]
    return _context


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    yield get_app_context()
