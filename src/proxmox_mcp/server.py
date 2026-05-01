import logging
import sys

from mcp.server.fastmcp import FastMCP

from proxmox_mcp.client import lifespan
from proxmox_mcp.tools import register_all

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

mcp = FastMCP("proxmox-mcp", lifespan=lifespan)
register_all(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
