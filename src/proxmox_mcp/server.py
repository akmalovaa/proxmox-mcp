import argparse
import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import anyio.to_thread
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.server import CacheHint
from mcp.types import Icon
from starlette.requests import Request
from starlette.responses import JSONResponse

from proxmox_mcp.client import get_app_context, lifespan
from proxmox_mcp.config import (
    TransportConfig,
    get_risk_level,
    get_tools_allowlist,
    get_transport_config,
)
from proxmox_mcp.telemetry import setup_sentry
from proxmox_mcp.tools import register_all

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("proxmox_mcp.server")

REPO_URL = "https://github.com/akmalovaa/proxmox-mcp"

INSTRUCTIONS = """\
Read-only access to a Proxmox VE cluster, plus guest lifecycle operations when the
operator has enabled them.

Discovery order: `list_nodes` gives the node names every other tool needs; `list_vms`
and `list_containers` give the (node, vmid) pairs. Never guess a node name or a VMID —
a wrong one comes back as a 404. `get_cluster_resources` is the cheapest single call
for a cluster-wide overview. `get_server_info` reports this server's own risk level
and versions.

QEMU VMs and LXC containers are separate namespaces with separate tools: a VMID valid
for `get_vm_status` is not valid for `get_container_status`. A guest's IP addresses come
from `get_vm_network_interfaces` (needs the QEMU guest agent) or
`get_container_interfaces` — they are not in the config or status output.

Write operations return a UPID rather than a finished result; poll it with
`get_task_status` and read failures with `get_task_log`. Which of them exist depends on
PROXMOX_RISK_LEVEL, set by the operator: `read` exposes only reads, `lifecycle` adds
start/stop/reboot/clone/migrate/snapshot-create, `all` adds snapshot delete and
rollback. Tools above the active level are absent from this list, not merely refused.

Every tool returns raw Proxmox JSON. The inventory listings return a compact subset of
each row by default; pass `verbose=true` for every field Proxmox sends.\
"""

try:
    __version__ = pkg_version("proxmox-ve-mcp")
except PackageNotFoundError:
    # Source checkout without an install. Same blank version MCPServer defaults to.
    __version__ = ""

# Before MCPServer(...), not after: the Sentry integration instruments servers by
# patching Server.__init__, so anything built ahead of sentry_sdk.init() is silent.
setup_sentry(__version__)

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
    # The tool list is fixed at import by the risk level and the allowlist, so it
    # cannot change while the process lives. The SDK's default hint is ttl_ms=0,
    # i.e. "already stale", which over HTTP means a round trip per client start.
    # `public` is accurate only while every caller sees the same list — revisit if
    # this server ever grows per-token authorization.
    cache_hints={
        "tools/list": CacheHint(ttl_ms=3_600_000, scope="public"),
        "server/discover": CacheHint(ttl_ms=3_600_000, scope="public"),
    },
)
policy = register_all(mcp, get_risk_level(), get_tools_allowlist())


# Health routes exist on the Streamable HTTP app only; in stdio mode nothing serves
# them. They are unauthenticated by design (see MCPServer.custom_route).
@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> JSONResponse:
    """Liveness: the process is up and serving. Deliberately never touches Proxmox —
    a liveness probe that fails when Proxmox is down would restart this pod in a
    loop and fix nothing."""
    return JSONResponse({"status": "ok", "version": __version__ or "unknown"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(request: Request) -> JSONResponse:
    """Readiness: Proxmox answered. This is the probe that should gate traffic."""
    from proxmox_mcp.tools._common import _describe

    try:
        app = get_app_context()
        version = await anyio.to_thread.run_sync(lambda: app.proxmox.version.get())
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not raise
        where = "the configured Proxmox host"
        return JSONResponse(
            {"status": "unavailable", "reason": _describe(exc, where)}, status_code=503
        )
    return JSONResponse({"status": "ready", "proxmox": version})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="proxmox-ve-mcp",
        description="MCP server for Proxmox VE. Every flag has a PROXMOX_MCP_* "
        "environment equivalent, which is what a container deployment should use.",
    )
    parser.add_argument("--version", action="version", version=__version__ or "unknown")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", help="HTTP bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="HTTP port (default 8000)")
    parser.add_argument("--path", help="Streamable HTTP endpoint path (default /mcp)")
    return parser.parse_args(argv)


def _resolve(args: argparse.Namespace) -> TransportConfig:
    """Environment first, then flags on top — the flags are the interactive path."""
    config = get_transport_config()
    overrides = {k: v for k, v in vars(args).items() if k != "version" and v is not None}
    return TransportConfig(**{**vars(config), **overrides})


def main(argv: list[str] | None = None) -> None:
    config = _resolve(_parse_args(argv))
    if not config.is_http:
        mcp.run()
        return

    security = config.security()
    logger.info(
        "serving streamable-http on %s:%s%s (risk_level=%s, tools=%d, "
        "dns_rebinding_protection=%s)",
        config.host, config.port, config.path, policy.risk_level,
        len(policy.registered), security.enable_dns_rebinding_protection,
    )
    mcp.run(
        transport="streamable-http",
        host=config.host,
        port=config.port,
        streamable_http_path=config.path,
        json_response=config.json_response,
        # Pinned, not configurable: sessions were removed from the protocol in
        # 2026-07-28, so the session-ful mode is a downgrade to an older revision.
        # It also lets several clients share one URL and survives a rolling update.
        stateless_http=True,
        transport_security=security,
    )


if __name__ == "__main__":
    main()
