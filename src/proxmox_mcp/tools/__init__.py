from mcp.server.mcpserver import MCPServer

from proxmox_mcp.config import RiskLevel
from proxmox_mcp.tools._common import Policy
from proxmox_mcp.tools.cluster import register as register_cluster
from proxmox_mcp.tools.containers import register as register_containers
from proxmox_mcp.tools.nodes import register as register_nodes
from proxmox_mcp.tools.server_info import register as register_server_info
from proxmox_mcp.tools.storage import register as register_storage
from proxmox_mcp.tools.vms import register as register_vms


def register_all(
    mcp: MCPServer, risk_level: RiskLevel, allow: frozenset[str] | None = None
) -> Policy:
    """Register every tool module against one policy snapshot and return it.

    The returned ``Policy`` is what ``get_server_info`` reports, so a client can
    read the server's own boundary instead of inferring it from which tools are
    missing.
    """
    policy = Policy(risk_level=risk_level, allow=allow)
    register_nodes(mcp, policy)
    register_vms(mcp, policy)
    register_containers(mcp, policy)
    register_storage(mcp, policy)
    register_cluster(mcp, policy)
    register_server_info(mcp, policy)

    unknown = policy.unknown_allowlist_entries()
    if unknown:
        raise ValueError(
            f"PROXMOX_TOOLS_ALLOW names tools that do not exist: "
            f"{', '.join(sorted(unknown))}"
        )
    return policy
