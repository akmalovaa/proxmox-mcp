# CLAUDE.md

## Project Overview

`proxmox-mcp` is a deliberately **minimal** MCP server for Proxmox VE — built for personal use, stdio transport only, no extra layers. Exposes 38 tools covering nodes, QEMU VMs, LXC containers, storage, cluster operations, and snapshots.

## Public listings

- **GHCR image**: `ghcr.io/akmalovaa/proxmox-mcp:latest` (multi-arch `amd64` + `arm64`).
- **Smithery**: https://smithery.ai/server/akmalovaa/proxmox-mcp — releases at https://smithery.ai/servers/akmalovaa/proxmox-mcp/releases. Published via `mcpb pack .` → `smithery mcp publish ./proxmox-mcp.mcpb -n akmalovaa/proxmox-mcp`.
- **Glama**: https://glama.ai/mcp/servers/akmalovaa/proxmox-mcp — score/audit at https://glama.ai/mcp/servers/akmalovaa/proxmox-mcp/score. Builds the Dockerfile from main branch on Deploy.

## Tech Stack

- **Python 3.14** with **UV** package manager
- **FastMCP** (mcp SDK) — MCP server framework
- **Proxmoxer** — Proxmox REST API client
- **Pydantic Settings** — configuration from environment variables

## Project Structure

```
├── Dockerfile                          # python:3.14-slim + UV (binary copied from ghcr.io/astral-sh/uv)
├── compose.yaml                        # Dev-only: builds local image with build: .
├── .dockerignore
├── .env.example                        # Template for local dev env vars
├── manifest.json                       # MCPB manifest for Smithery (server.type=python, no tools[] — see "Smithery quirks")
├── smithery.yaml                       # Smithery startCommand + configSchema (docker run via GHCR)
├── .mcpbignore                         # Files excluded from .mcpb bundle (keeps it lean ~15kB)
├── glama.json                          # Glama maintainers file
├── .github/workflows/
│   ├── ci.yml                          # ruff + mypy + pytest on push/PR to main
│   └── docker-publish.yml              # Multi-arch GHCR publish on tag pushes '*.*.*'
src/proxmox_mcp/
├── __init__.py
├── __main__.py                         # `uv run python -m proxmox_mcp`
├── server.py                           # FastMCP instance, tool registration, entry point
├── config.py                           # Settings class (env vars with PROXMOX_ prefix)
├── client.py                           # AppContext (lazy ProxmoxAPI property), lifespan
└── tools/
    ├── __init__.py                     # register_all() — imports and registers all tool modules
    ├── nodes.py                        # 7 tools: list_nodes, get_node_status, networks, disks, tasks
    ├── vms.py                          # 14 tools: list/status/config/snapshots + lifecycle/clone
    ├── containers.py                   # 11 tools: list/status/config/snapshots + lifecycle
    ├── storage.py                      # 2 tools: list_storage, get_storage_content
    └── cluster.py                      # 4 tools: status, resources, backups, next_vmid
```

## Key Patterns

- **Lazy connect**: `AppContext.proxmox` is a `@property` that builds the `ProxmoxAPI` on first access. The lifespan only constructs `Settings()`. Reason: the server must start cleanly even when Proxmox is unreachable (e.g. Glama/Smithery sandboxes), so eager `proxmox.version.get()` was removed. Tool calls surface connection errors via the normal error path.
- **Three-tier access**: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`. `read` exposes only GETs; `lifecycle` adds start/stop/clone/create-snapshot; `all` adds delete/rollback snapshots.
- **Tool registration**: each `tools/*.py` has a `register(mcp)` function that decorates functions with `@mcp.tool()`
- **Context access**: `_ctx(ctx)` helper extracts `AppContext` from MCP context; `_tier(ctx, "lifecycle"|"all")` guards elevated ops and logs ALLOW/DENY to stderr
- **Return format**: all tools return `json.dumps(data, indent=2)` — no formatting, no emoji, raw JSON for LLM

## Commands

```bash
# Local dev
uv sync                          # Install dependencies
uv run proxmox-mcp               # Run server (stdio mode)
uv run python -m proxmox_mcp     # Alternative run

# Lint / type / test (mirrors CI)
uv run ruff check .
uv run mypy src/
uv run pytest -v

# Docker (local build)
docker build -t proxmox-mcp .
docker run -i --rm \
  -e PROXMOX_HOST -e PROXMOX_USER \
  -e PROXMOX_TOKEN_NAME -e PROXMOX_TOKEN_VALUE \
  proxmox-mcp

# Pre-built image (preferred for end users)
docker run -i --rm \
  -e PROXMOX_HOST -e PROXMOX_USER \
  -e PROXMOX_TOKEN_NAME -e PROXMOX_TOKEN_VALUE \
  ghcr.io/akmalovaa/proxmox-mcp:latest
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

## CI/CD

- **`.github/workflows/ci.yml`** — runs ruff, mypy, pytest on push/PR to `main`.
- **`.github/workflows/docker-publish.yml`** — builds and pushes multi-arch (`amd64` + `arm64`) image to `ghcr.io/akmalovaa/proxmox-mcp` on:
  - push of semver tag `X.Y.Z` (no `v` prefix) → tags `:X.Y.Z`, `:X.Y`, `:sha-<short>`, `:latest`
  - manual `workflow_dispatch` (on a tag ref) → same tagging as above
- SBOM + provenance generated by `docker/build-push-action@v7` (`sbom: true`, `provenance: true`) and attached to the image in GHCR. No separate GitHub Attestations step (`actions/attest-build-provenance` is unavailable for user-owned private repos).
- GHA cache (`type=gha`) used for Docker layers.

## Release flow

To cut a release: `git tag 1.2.3 && git push --tags`. `docker-publish.yml` will build and push `:1.2.3`, `:1.2`, `:sha-<short>` and move `:latest` to point at the new release. Pushes to `main` no longer trigger image builds — only tag pushes do.

## Republishing to Smithery

```bash
mcpb pack .                                                     # produces proxmox-mcp.mcpb (~15kB)
smithery mcp publish ./proxmox-mcp.mcpb -n akmalovaa/proxmox-mcp
```

Smithery quirks (already baked into our `manifest.json` — don't break them):

- `server.type` **must be `python`** — `uv` is in the official MCPB spec but Smithery's CLI only recognizes `python`/`node`/`binary`/`bun`. The actual run command (`uv run python -m proxmox_mcp`) is unaffected.
- **Do not add `tools[]` to manifest.** MCPB rejects `tools[].inputSchema` ("Unrecognized key"); Smithery backend rejects tools without `inputSchema` ("expected object, received undefined"). Conflict — easiest is to omit the `tools` key entirely. Tools are still announced dynamically via the MCP protocol when a client connects.
- `proxmox-mcp.mcpb` is a build artifact — gitignored via `*.mcpb`.
