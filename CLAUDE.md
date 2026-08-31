# CLAUDE.md

## Project Overview

`proxmox-mcp` is a deliberately **minimal** MCP server for Proxmox VE — built for personal use, stdio transport only, no extra layers. Exposes 49 tools covering nodes, QEMU VMs, LXC containers, storage, cluster operations, snapshots, guest IP lookup and RRD metrics.

## Public listings

- **GHCR image**: `ghcr.io/akmalovaa/proxmox-mcp:latest` (multi-arch `amd64` + `arm64`). Preferred install path.
- **PyPI**: https://pypi.org/project/proxmox-ve-mcp/ — distribution name is `proxmox-ve-mcp` (the `proxmox-mcp` slot was already taken). Run via `uvx proxmox-ve-mcp`. The Python module is still imported as `proxmox_mcp` — `[tool.uv.build-backend] module-name` in `pyproject.toml` reconciles the two names.
- **Glama**: https://glama.ai/mcp/servers/akmalovaa/proxmox-mcp — builds the Dockerfile from main branch on Deploy.
- **MCP Registry**: `server.json` declares the pypi + oci packages under the name `io.github.akmalovaa/proxmox-mcp`, which is what the `<!-- mcp-name: ... -->` marker at the top of README.md validates ownership for. Publishing is manual — see "Release flow".

## Tech Stack

- **Python 3.14** with **UV** package manager
- **MCP Python SDK 2.x** (`mcp.server.mcpserver.MCPServer`) — MCP server framework
- **Proxmoxer** — Proxmox REST API client
- **Pydantic Settings** — configuration from environment variables

## Project Structure

```
├── Dockerfile                          # Multi-stage: uv builds the venv, runtime runs as uid 10001
├── compose.yaml                        # Dev-only: builds local image with build: .
├── .dockerignore                       # Deny-all + allowlist; keeps docs/ out of the context
├── .env.example                        # Template for local dev env vars
├── glama.json                          # Glama maintainers file
├── server.json                         # MCP Registry manifest (pypi + oci packages)
├── .github/
│   ├── dependabot.yml                  # Monthly uv / actions / docker bumps
│   └── workflows/
│       ├── ci.yml                      # ruff + mypy + pytest + Docker build & stdio smoke test
│       └── docker-publish.yml          # Multi-arch GHCR publish on tag pushes 'X.Y.Z'
src/proxmox_mcp/
├── __init__.py
├── __main__.py                         # `uv run python -m proxmox_mcp`
├── server.py                           # MCPServer instance (+ instructions/icons), registration, entry point
├── config.py                           # Settings class (env vars with PROXMOX_ prefix)
├── client.py                           # AppContext (lazy, lock-guarded ProxmoxAPI), lifespan
└── tools/
    ├── __init__.py                     # register_all() — imports and registers all tool modules
    ├── _common.py                      # gate, error normalization, _ctx/_tier/_json, annotations
    ├── nodes.py                        # 10 tools: status, networks, disks, services, updates, rrd, tasks
    ├── vms.py                          # 17 tools: read + IPs/rrd + lifecycle/clone/migrate + snapshots
    ├── containers.py                   # 13 tools: read + IPs/rrd + lifecycle + snapshots
    ├── storage.py                      # 2 tools: list_storage, get_storage_content
    └── cluster.py                      # 7 tools: status, resources, backups, ha, pools, log, next_vmid
```

## Key Patterns

- **Lazy connect**: `AppContext.proxmox` is a `@property` that builds the `ProxmoxAPI` on first access, under a `threading.Lock` (double-checked). The lifespan only constructs `Settings()`. Reason: the server must start cleanly even when Proxmox is unreachable (e.g. CI tool-listing, registry sandboxes), so eager `proxmox.version.get()` was removed. The lock matters because the SDK runs sync tool bodies on `anyio.to_thread` workers — concurrent first calls would otherwise each build a client, which under password auth means several logins.
- **Three-tier access**: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`. Tools are gated **at registration time**, so a level only ever exposes the tools it allows — they never appear in the client's tool list otherwise:
  - `read` → 31 read-only GET tools
  - `lifecycle` → +14 start/stop/reboot/clone/migrate/create-snapshot (45 total)
  - `all` → +4 delete/rollback (49 total)
- **Registration gating**: `make_gate(mcp, risk_level)` (in `tools/_common.py`) returns a `@tool(...)` decorator used in place of `@mcp.tool(...)`. It infers the required tier from the `annotations=` kwarg (READ_ONLY→read, LIFECYCLE→lifecycle, DESTRUCTIVE→all) and skips registering any tool above the active level. `server.py` reads the level via `config.get_risk_level()` at import (separate from `Settings`, which needs `host`).
- **Tool registration**: each `tools/*.py` has a `register(mcp, risk_level)` function that builds `tool = make_gate(...)` then decorates functions with `@tool()`.
- **Context access**: `_ctx(ctx)` extracts `AppContext` from MCP context; `_tier(ctx, "lifecycle"|"all")` guards elevated ops at call time (defense in depth on top of registration gating) and logs ALLOW/DENY to stderr.
- **Return format**: all tools return `_json(data)` from `_common.py` — compact `json.dumps` with `separators=(",", ":")`, no emoji, raw JSON for LLM. Indentation is pure token cost on large responses like `get_cluster_resources`.
- **Error normalization**: `make_gate` wraps every registered tool in `_wrap_errors`, which re-raises whatever the body throws as an `mcp.server.mcpserver.exceptions.ToolError` carrying a sentence from `_describe()`. This is not cosmetic: the SDK forwards the message of a `ToolError` but replaces anything else with a bare `Error executing tool <name>`, so without the wrapper a 403, an unreachable host, and even the `_tier` denial all reach the model as no information at all. Covered by `tests/test_errors.py`.
- **Server metadata**: `server.py` passes `instructions=` (discovery order, QEMU vs LXC namespaces, UPID polling, what the risk tiers do), plus `title`, `website_url` and `icons`. The instructions are the cheapest place to prevent guessed node names and VMIDs.

## Commands

```bash
# Local dev
uv sync                          # Install dependencies
uv run python -m proxmox_mcp     # Run server (stdio mode)
uv run proxmox-ve-mcp            # Same thing via the script entry-point

# Lint / type / test (mirrors CI)
uv sync --locked --group dev     # --locked fails if uv.lock is stale vs pyproject.toml
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
2. Add a `register(mcp: MCPServer, risk_level: RiskLevel)` function; build `tool = make_gate(mcp, risk_level)` and decorate handlers with `@tool(title=..., annotations=...)` (not `@mcp.tool()`) so they are gated by tier and wrapped for errors.
3. Each tool gets `ctx: Context` as first param; use `_ctx(ctx).proxmox` for the API client.
4. For elevated operations, call `_tier(ctx, "lifecycle")` or `_tier(ctx, "all")` at the start (call-time guard on top of the registration gate).
5. Register the module in `tools/__init__.py` (pass `risk_level` through).
6. Add a case to `CASES` in `tests/test_endpoints.py` and the right set in `tests/test_registration.py`. `test_every_tool_has_an_endpoint_case` fails if you skip step 6, by design — proxmoxer builds URLs from attribute access, so a wrong path is invisible to ruff, mypy and a tool-count check alike.

### Tool quality patterns

- **Descriptions** — every `@mcp.tool()` has a one-line docstring (extra details after a blank line). The SDK does **not** parse Google-style `Args:` sections — keep the docstring focused on the tool's purpose, not parameters.
- **Parameter descriptions** — every parameter uses `Annotated[T, Field(description="...")]` from `pydantic`. This is the only way descriptions land in `input_schema.properties[*].description`.
- **Titles** — every tool passes `title="..."`, the spec-preferred human-readable name clients display (distinct from the snake_case `name`).
- **Annotations** — every tool passes `annotations=READ_ONLY | LIFECYCLE | DESTRUCTIVE` (constants in `tools/_common.py`). `_required_tier` reads the annotation *fields*, not object identity, so a hand-built `ToolAnnotations` still lands in the right tier; omitting annotations raises at registration rather than silently exposing the tool at every level. All three set `open_world_hint=True` (serialized as `openWorldHint` on the wire) because every tool calls the external Proxmox API. The annotation also drives registration gating (see "Registration gating"), so picking the right one is what places a tool in the correct tier.
  - `READ_ONLY` — all GETs (`list_*`, `get_*`)
  - `LIFECYCLE` — start/stop/reboot/shutdown/suspend/resume/clone/create-snapshot
  - `DESTRUCTIVE` — delete/rollback (data loss possible)
- **Naming** — snake_case `verb_noun` (`list_vms`, `get_vm_status`, `start_container`, `delete_container_snapshot`).

Validation snippet (run after edits) — confirms descriptions land in `input_schema` and annotations are attached:

```bash
# PROXMOX_RISK_LEVEL=all exposes every tool so the snippet validates all 49.
uv run python -c "
import asyncio, os
os.environ.update(PROXMOX_HOST='x', PROXMOX_TOKEN_NAME='x', PROXMOX_TOKEN_VALUE='x', PROXMOX_RISK_LEVEL='all')
from proxmox_mcp.server import mcp
async def m():
    tools = await mcp.list_tools()
    p = sum(1 for t in tools for x in t.input_schema.get('properties', {}).values() if x.get('description'))
    n = sum(len(t.input_schema.get('properties', {})) for t in tools)
    a = sum(1 for t in tools if t.annotations)
    print(f'tools: {len(tools)}, params w/ desc: {p}/{n}, annotated: {a}/{len(tools)}')
asyncio.run(m())
"
```

## CI/CD

- **`.github/workflows/ci.yml`** — two jobs on push/PR to `main`:
  - `check` — `uv sync --locked` (catches a stale lockfile, which is what broke tag 1.0.5), then ruff, mypy, pytest.
  - `docker` — builds the Dockerfile without pushing and drives a real MCP handshake over stdio against the image, so a broken build surfaces on the PR instead of mid-release.
- **`.github/dependabot.yml`** — monthly grouped bumps for uv deps, GitHub Actions and the Docker base/uv images.
- **`.github/workflows/docker-publish.yml`** — builds and pushes multi-arch (`amd64` + `arm64`) image to `ghcr.io/akmalovaa/proxmox-mcp` on:
  - push of semver tag `X.Y.Z` (no `v` prefix) → tags `:X.Y.Z`, `:X.Y`, `:sha-<short>`, `:latest`
  - manual `workflow_dispatch` (on a tag ref) → same tagging as above
- SBOM + provenance generated by `docker/build-push-action@v7` (`sbom: true`, `provenance: true`) and attached to the image in GHCR.
- GHA cache (`type=gha`) used for Docker layers.

## Release flow

1. Bump `version` in `pyproject.toml` **and** the three `version` fields in `server.json` (server + both packages, including the `:X.Y.Z` tag in the oci identifier).
2. `uv lock` to refresh the lockfile (skipping this is what blew up tag 1.0.5; CI's `--locked` now catches it).
3. Commit + push to `main`.
4. `uv build && uv publish dist/proxmox_ve_mcp-X.Y.Z*` — pushes the wheel to PyPI. Token is read from `~/.pypirc` (set `UV_PUBLISH_TOKEN` env var from there since `uv publish` does not read pypirc directly).
5. `git tag X.Y.Z && git push --tags` — `docker-publish.yml` builds and pushes `:X.Y.Z`, `:X.Y`, `:sha-<short>` and moves `:latest` to the new release.
6. *(optional)* Publish to the MCP Registry with `mcp-publisher login github && mcp-publisher publish`, run locally from the repo root. It validates `server.json` against the `<!-- mcp-name: ... -->` marker in README.md. Deliberately not automated — publishing stays a manual, local step, same as PyPI.
