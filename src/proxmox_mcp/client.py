from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from proxmoxer import ProxmoxAPI

from proxmox_mcp.config import Settings


@dataclass
class AppContext:
    proxmox: ProxmoxAPI
    settings: Settings


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()  # type: ignore[call-arg]
    proxmox = ProxmoxAPI(**settings.get_proxmoxer_kwargs())
    proxmox.version.get()
    yield AppContext(proxmox=proxmox, settings=settings)
