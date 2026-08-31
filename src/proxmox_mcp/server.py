import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from mcp.server.mcpserver import MCPServer

from proxmox_mcp.client import lifespan
from proxmox_mcp.config import get_risk_level
from proxmox_mcp.tools import register_all

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

try:
    __version__ = pkg_version("proxmox-ve-mcp")
except PackageNotFoundError:
    # Source checkout / the Docker image, which runs from PYTHONPATH=/app/src
    # without installing the project. Same blank version MCPServer defaults to.
    __version__ = ""

mcp = MCPServer("proxmox-mcp", version=__version__, lifespan=lifespan)
register_all(mcp, get_risk_level())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
