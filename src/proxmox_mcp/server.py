from mcp.server.fastmcp import FastMCP

from proxmox_mcp.client import lifespan
from proxmox_mcp.tools import register_all

mcp = FastMCP("proxmox-mcp", lifespan=lifespan)
register_all(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
