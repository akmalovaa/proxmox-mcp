# CLAUDE.md

## Project Overview

Proxmox MCP — MCP server for managing Proxmox VE clusters. Provides 39 tools for nodes, VMs (QEMU), containers (LXC), storage, cluster operations, snapshots, and command execution.

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
    ├── vms.py         # 15 tools: list/status/config/snapshots + lifecycle/clone/exec
    ├── containers.py  # 11 tools: list/status/config/snapshots + lifecycle
    ├── storage.py     # 2 tools: list_storage, get_storage_content
    └── cluster.py     # 4 tools: status, resources, backups, next_vmid
```

## Key Patterns

- **Lifespan pattern**: Proxmoxer connection is created once in `client.py:lifespan()`, shared via `AppContext`
- **Two-tier access**: read-only tools always available; elevated tools (start/stop/snapshot/exec) require `PROXMOX_ALLOW_ELEVATED=true`
- **Tool registration**: each `tools/*.py` has a `register(mcp)` function that decorates functions with `@mcp.tool()`
- **Context access**: `_ctx(ctx)` helper extracts `AppContext` from MCP context; `_elevated(ctx)` guards destructive ops
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
| `PROXMOX_ALLOW_ELEVATED` | no | false | Enable destructive operations |

*Either token (name+value) or password is required.

## Adding New Tools

1. Create or edit a file in `src/proxmox_mcp/tools/`
2. Add a `register(mcp: FastMCP)` function with `@mcp.tool()` decorated handlers
3. Each tool gets `ctx: Context` as first param; use `_ctx(ctx).proxmox` for the API client
4. For destructive operations, call `_elevated(ctx)` at the start
5. Register the module in `tools/__init__.py`
