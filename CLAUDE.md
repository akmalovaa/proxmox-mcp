# CLAUDE.md

## Project Overview

Proxmox MCP — MCP server for managing Proxmox VE clusters. Provides 40 tools for nodes, VMs (QEMU), containers (LXC), storage, ISO management, cluster operations, and snapshots.

## Tech Stack

- **Python 3.14** with **UV** package manager
- **FastMCP** (mcp SDK) — MCP server framework
- **Proxmoxer** — Proxmox REST API client
- **Pydantic Settings** — configuration from environment variables

## Project Structure

```
├── Dockerfile         # Multi-stage build with UV
├── .dockerignore
src/proxmox_mcp/
├── __init__.py
├── __main__.py        # `uv run python -m proxmox_mcp`
├── server.py          # FastMCP instance, tool registration, entry point
├── config.py          # Settings class (env vars with PROXMOX_ prefix)
├── client.py          # AppContext dataclass, lifespan (Proxmoxer connection)
└── tools/
    ├── __init__.py    # register_all() — imports and registers all tool modules
    ├── nodes.py       # 7 tools: list_nodes, get_node_status, networks, disks, tasks
    ├── vms.py         # 14 tools: list/status/config/snapshots + lifecycle/clone
    ├── containers.py  # 11 tools: list/status/config/snapshots + lifecycle
    ├── storage.py     # 4 tools: list_storage, get_storage_content, download_iso, delete_iso
    └── cluster.py     # 4 tools: status, resources, backups, next_vmid
```

## Key Patterns

- **Lifespan pattern**: Proxmoxer connection is created once in `client.py:lifespan()`, shared via `AppContext`
- **Three-tier access**: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`. `read` exposes only GETs; `lifecycle` adds start/stop/clone/create-snapshot; `all` adds delete/rollback snapshots.
- **Tool registration**: each `tools/*.py` has a `register(mcp)` function that decorates functions with `@mcp.tool()`
- **Context access**: `_ctx(ctx)` helper extracts `AppContext` from MCP context; `_tier(ctx, "lifecycle"|"all")` guards elevated ops and logs ALLOW/DENY to stderr
- **Return format**: all tools return `json.dumps(data, indent=2)` — no formatting, no emoji, raw JSON for LLM

## Commands

```bash
uv sync                          # Install dependencies
uv run proxmox-mcp               # Run server (stdio mode)
uv run python -m proxmox_mcp     # Alternative run

# Docker
docker build -t proxmox-mcp .
docker run -i --rm --env-file .env proxmox-mcp
```

## Configuration

All via environment variables (prefix `PROXMOX_`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROXMOX_HOST` | yes | — | Proxmox host IP/hostname |
| `PROXMOX_PORT` | no | 8006 | API port |
| `PROXMOX_VERIFY_SSL` | no | false | Verify SSL certificates |
| `PROXMOX_USER` | no | root@pam | API user |
| `PROXMOX_TOKEN_NAME` | yes* | — | API token name |
| `PROXMOX_TOKEN_VALUE` | yes* | — | API token value |
| `PROXMOX_PASSWORD` | yes* | — | Password (fallback if no token) |
| `PROXMOX_RISK_LEVEL` | no | read | `read`/`lifecycle`/`all` — see "Three-tier access" |

*Either token (name+value) or password is required.

## Adding New Tools

1. Create or edit a file in `src/proxmox_mcp/tools/`
2. Add a `register(mcp: FastMCP)` function with `@mcp.tool()` decorated handlers
3. Each tool gets `ctx: Context` as first param; use `_ctx(ctx).proxmox` for the API client
4. For elevated operations, call `_tier(ctx, "lifecycle")` or `_tier(ctx, "all")` at the start
5. Register the module in `tools/__init__.py`
