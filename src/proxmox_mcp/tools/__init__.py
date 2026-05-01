from mcp.server.fastmcp import FastMCP

from proxmox_mcp.tools.cluster import register as register_cluster
from proxmox_mcp.tools.containers import register as register_containers
from proxmox_mcp.tools.nodes import register as register_nodes
from proxmox_mcp.tools.storage import register as register_storage
from proxmox_mcp.tools.vms import register as register_vms


def register_all(mcp: FastMCP) -> None:
    register_nodes(mcp)
    register_vms(mcp)
    register_containers(mcp)
    register_storage(mcp)
    register_cluster(mcp)
