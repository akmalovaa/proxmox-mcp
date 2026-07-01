from mcp.server.fastmcp import FastMCP

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools.cluster import register as register_cluster
from proxmox_mcp.tools.containers import register as register_containers
from proxmox_mcp.tools.nodes import register as register_nodes
from proxmox_mcp.tools.storage import register as register_storage
from proxmox_mcp.tools.vms import register as register_vms


def register_all(mcp: FastMCP, risk_level: RiskLevel) -> None:
    register_nodes(mcp, risk_level)
    register_vms(mcp, risk_level)
    register_containers(mcp, risk_level)
    register_storage(mcp, risk_level)
    register_cluster(mcp, risk_level)
