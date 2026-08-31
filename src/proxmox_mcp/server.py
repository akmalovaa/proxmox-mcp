import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from mcp.server.mcpserver import MCPServer
from mcp.types import Icon

from proxmox_mcp.client import lifespan
from proxmox_mcp.config import get_risk_level
from proxmox_mcp.tools import register_all

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

REPO_URL = "https://github.com/akmalovaa/proxmox-mcp"

INSTRUCTIONS = """\
Read-only access to a Proxmox VE cluster, plus guest lifecycle operations when the
operator has enabled them.

Discovery order: `list_nodes` gives the node names every other tool needs; `list_vms`
and `list_containers` give the (node, vmid) pairs. Never guess a node name or a VMID —
a wrong one comes back as a 404. `get_cluster_resources` is the cheapest single call
for a cluster-wide overview.

QEMU VMs and LXC containers are separate namespaces with separate tools: a VMID valid
for `get_vm_status` is not valid for `get_container_status`. A guest's IP addresses come
from `get_vm_network_interfaces` (needs the QEMU guest agent) or
`get_container_interfaces` — they are not in the config or status output.

Write operations return a UPID rather than a finished result; poll it with
`get_task_status` and read failures with `get_task_log`. Which of them exist depends on
PROXMOX_RISK_LEVEL, set by the operator: `read` exposes only reads, `lifecycle` adds
start/stop/reboot/clone/migrate/snapshot-create, `all` adds snapshot delete and
rollback. Tools above the active level are absent from this list, not merely refused.

Every tool returns raw Proxmox JSON.\
"""

try:
    __version__ = pkg_version("proxmox-ve-mcp")
except PackageNotFoundError:
    # Source checkout without an install. Same blank version MCPServer defaults to.
    __version__ = ""

mcp = MCPServer(
    "proxmox-mcp",
    title="Proxmox VE",
    version=__version__,
    instructions=INSTRUCTIONS,
    website_url=REPO_URL,
    icons=[
        Icon(
            src=f"{REPO_URL}/raw/main/docs/logo_512.png",
            mime_type="image/png",
            sizes=["512x512"],
        )
    ],
    lifespan=lifespan,
)
register_all(mcp, get_risk_level())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
