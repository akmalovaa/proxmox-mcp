from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from proxmoxer import ProxmoxAPI

from proxmox_mcp.config import Settings


class AppContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._proxmox: ProxmoxAPI | None = None

    @property
    def proxmox(self) -> ProxmoxAPI:
        if self._proxmox is None:
            self._proxmox = ProxmoxAPI(**self.settings.get_proxmoxer_kwargs())
        return self._proxmox


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext(Settings())  # type: ignore[call-arg]
