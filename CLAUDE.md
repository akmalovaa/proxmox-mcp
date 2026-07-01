# CLAUDE.md

## Project Overview

`proxmox-mcp` is a deliberately **minimal** MCP server for Proxmox VE — built for personal use, stdio transport only, no extra layers. Exposes 38 tools covering nodes, QEMU VMs, LXC containers, storage, cluster operations, and snapshots.

## Public listings

- **GHCR image**: `ghcr.io/akmalovaa/proxmox-mcp:latest` (multi-arch `amd64` + `arm64`). Preferred install path.
- **PyPI**: https://pypi.org/project/proxmox-ve-mcp/ — distribution name is `proxmox-ve-mcp` (the `proxmox-mcp` slot was already taken). Run via `uvx proxmox-ve-mcp`. The Python module is still imported as `proxmox_mcp` — `[tool.uv.build-backend] module-name` in `pyproject.toml` reconciles the two names.
- **Glama**: https://glama.ai/mcp/servers/akmalovaa/proxmox-mcp — builds the Dockerfile from main branch on Deploy.

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
├── glama.json                          # Glama maintainers file
├── .github/workflows/
│   ├── ci.yml                          # ruff + mypy + pytest on push/PR to main
│   └── docker-publish.yml              # Multi-arch GHCR publish on tag pushes 'X.Y.Z'
src/proxmox_mcp/
├── __init__.py
├── __main__.py                         # `uv run python -m proxmox_mcp`
├── server.py                           # FastMCP instance, tool registration, entry point
├── config.py                           # Settings class (env vars with PROXMOX_ prefix)
├── client.py                           # AppContext (lazy ProxmoxAPI property), lifespan
└── tools/
    ├── __init__.py                     # register_all() — imports and registers all tool modules
    ├── _common.py                      # _ctx, _tier, READ_ONLY/LIFECYCLE/DESTRUCTIVE annotations
    ├── nodes.py                        # 7 tools: list_nodes, get_node_status, networks, disks, tasks
    ├── vms.py                          # 14 tools: list/status/config/snapshots + lifecycle/clone
    ├── containers.py                   # 11 tools: list/status/config/snapshots + lifecycle
    ├── storage.py                      # 2 tools: list_storage, get_storage_content
    └── cluster.py                      # 4 tools: status, resources, backups, next_vmid
```

## Key Patterns

- **Lazy connect**: `AppContext.proxmox` is a `@property` that builds the `ProxmoxAPI` on first access. The lifespan only constructs `Settings()`. Reason: the server must start cleanly even when Proxmox is unreachable (e.g. CI tool-listing, registry sandboxes), so eager `proxmox.version.get()` was removed. Tool calls surface connection errors via the normal error path.
- **Three-tier access**: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`. Tools are gated **at registration time**, so a level only ever exposes the tools it allows — they never appear in the client's tool list otherwise:
  - `read` → 21 read-only GET tools
  - `lifecycle` → +13 start/stop/reboot/clone/create-snapshot (34 total)
  - `all` → +4 delete/rollback (38 total)
- **Registration gating**: `make_gate(mcp, risk_level)` (in `tools/_common.py`) returns a `@tool(...)` decorator used in place of `@mcp.tool(...)`. It infers the required tier from the `annotations=` kwarg (READ_ONLY→read, LIFECYCLE→lifecycle, DESTRUCTIVE→all) and skips registering any tool above the active level. `server.py` reads the level via `config.get_risk_level()` at import (separate from `Settings`, which needs `host`).
- **Tool registration**: each `tools/*.py` has a `register(mcp, risk_level)` function that builds `tool = make_gate(...)` then decorates functions with `@tool()`.
- **Context access**: `_ctx(ctx)` extracts `AppContext` from MCP context; `_tier(ctx, "lifecycle"|"all")` guards elevated ops at call time (defense in depth on top of registration gating) and logs ALLOW/DENY to stderr.
- **Return format**: all tools return `json.dumps(data, indent=2)` — no formatting, no emoji, raw JSON for LLM.

## Commands

```bash
# Local dev
uv sync                          # Install dependencies
uv run python -m proxmox_mcp     # Run server (stdio mode)
uv run proxmox-ve-mcp            # Same thing via the script entry-point

# Lint / type / test (mirrors CI)
uv run ruff check .
uv run mypy src/
uv run pytest -v

# Build wheel
uv build                         # dist/*.whl + *.tar.gz

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

1. Create or edit a file in `src/proxmox_mcp/tools/`.
2. Add a `register(mcp: FastMCP, risk_level: RiskLevel)` function; build `tool = make_gate(mcp, risk_level)` and decorate handlers with `@tool()` (not `@mcp.tool()`) so they are gated by tier.
3. Each tool gets `ctx: Context` as first param; use `_ctx(ctx).proxmox` for the API client.
4. For elevated operations, call `_tier(ctx, "lifecycle")` or `_tier(ctx, "all")` at the start (call-time guard on top of the registration gate).
5. Register the module in `tools/__init__.py` (pass `risk_level` through).

### Tool quality patterns

- **Descriptions** — every `@mcp.tool()` has a one-line docstring (extra details after a blank line). FastMCP does **not** parse Google-style `Args:` sections — keep the docstring focused on the tool's purpose, not parameters.
- **Parameter descriptions** — every parameter uses `Annotated[T, Field(description="...")]` from `pydantic`. This is the only way descriptions land in `inputSchema.properties[*].description`.
- **Annotations** — every tool passes `annotations=READ_ONLY | LIFECYCLE | DESTRUCTIVE` (constants in `tools/_common.py`). All three set `openWorldHint=True` because every tool calls the external Proxmox API. The annotation also drives registration gating (see "Registration gating"), so picking the right one is what places a tool in the correct tier.
  - `READ_ONLY` — all GETs (`list_*`, `get_*`)
  - `LIFECYCLE` — start/stop/reboot/shutdown/suspend/resume/clone/create-snapshot
  - `DESTRUCTIVE` — delete/rollback (data loss possible)
- **Naming** — snake_case `verb_noun` (`list_vms`, `get_vm_status`, `start_container`, `delete_container_snapshot`).

Validation snippet (run after edits) — confirms descriptions land in `inputSchema` and annotations are attached:

```bash
# PROXMOX_RISK_LEVEL=all exposes every tool so the snippet validates all 38.
uv run python -c "
import asyncio, os
os.environ.update(PROXMOX_HOST='x', PROXMOX_TOKEN_NAME='x', PROXMOX_TOKEN_VALUE='x', PROXMOX_RISK_LEVEL='all')
from proxmox_mcp.server import mcp
async def m():
    tools = await mcp.list_tools()
    p = sum(1 for t in tools for x in t.inputSchema.get('properties', {}).values() if x.get('description'))
    n = sum(len(t.inputSchema.get('properties', {})) for t in tools)
    a = sum(1 for t in tools if t.annotations)
    print(f'tools: {len(tools)}, params w/ desc: {p}/{n}, annotated: {a}/{len(tools)}')
asyncio.run(m())
"
```

## CI/CD

- **`.github/workflows/ci.yml`** — runs ruff, mypy, pytest on push/PR to `main`.
- **`.github/workflows/docker-publish.yml`** — builds and pushes multi-arch (`amd64` + `arm64`) image to `ghcr.io/akmalovaa/proxmox-mcp` on:
  - push of semver tag `X.Y.Z` (no `v` prefix) → tags `:X.Y.Z`, `:X.Y`, `:sha-<short>`, `:latest`
  - manual `workflow_dispatch` (on a tag ref) → same tagging as above
- SBOM + provenance generated by `docker/build-push-action@v7` (`sbom: true`, `provenance: true`) and attached to the image in GHCR.
- GHA cache (`type=gha`) used for Docker layers.

## Release flow

1. Bump `version` in `pyproject.toml`.
2. `uv lock` to refresh the lockfile (skipping this is what blew up tag 1.0.5).
3. Commit + push to `main`.
4. `uv build && uv publish dist/proxmox_ve_mcp-X.Y.Z*` — pushes the wheel to PyPI. Token is read from `~/.pypirc` (set `UV_PUBLISH_TOKEN` env var from there since `uv publish` does not read pypirc directly).
5. `git tag X.Y.Z && git push --tags` — `docker-publish.yml` builds and pushes `:X.Y.Z`, `:X.Y`, `:sha-<short>` and moves `:latest` to the new release.
