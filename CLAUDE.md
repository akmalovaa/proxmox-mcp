# CLAUDE.md

## Project Overview

`proxmox-mcp` is a deliberately **minimal** MCP server for Proxmox VE — built for personal use, no extra layers. stdio by default, Streamable HTTP behind one env var. Exposes 50 tools covering nodes, QEMU VMs, LXC containers, storage, cluster operations, snapshots, guest IP lookup, RRD metrics and server self-description.

## Public listings

- **GHCR image**: `ghcr.io/akmalovaa/proxmox-mcp:latest` (multi-arch `amd64` + `arm64`). Preferred install path.
- **PyPI**: https://pypi.org/project/proxmox-ve-mcp/ — distribution name is `proxmox-ve-mcp` (the `proxmox-mcp` slot was already taken). Run via `uvx proxmox-ve-mcp`. The Python module is still imported as `proxmox_mcp` — `[tool.uv.build-backend] module-name` in `pyproject.toml` reconciles the two names.
- **Glama**: https://glama.ai/mcp/servers/akmalovaa/proxmox-mcp — builds the Dockerfile from main branch on Deploy.
- **MCP Registry**: published as `io.github.akmalovaa/proxmox-mcp` (check with `curl "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.akmalovaa/proxmox-mcp"`). `server.json` declares both the pypi and oci packages; publishing is manual — see "Release flow".

## Tech Stack

- **Python 3.14** with **UV** package manager
- **MCP Python SDK 2.x** (`mcp.server.mcpserver.MCPServer`) — MCP server framework
- **Proxmoxer** — Proxmox REST API client
- **Pydantic Settings** — configuration from environment variables

## Project Structure

```
├── Dockerfile                          # Multi-stage: uv builds the venv (--extra sentry), runs as uid 10001, EXPOSE 8000
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
├── server.py                           # MCPServer instance (+ instructions/icons/cache_hints), health routes, transport dispatch
├── config.py                           # Settings (PROXMOX_) + TransportConfig (PROXMOX_MCP_) + risk/allowlist/redaction readers
├── client.py                           # AppContext (lazy, lock-guarded ProxmoxAPI), process-wide singleton, lifespan
├── telemetry.py                        # setup_sentry() — optional, inert without SENTRY_DSN
└── tools/
    ├── __init__.py                     # register_all() — builds the Policy, registers all modules
    ├── _common.py                      # Policy, gate, error normalization, _ctx/_tier/_json/_redact/_compact, annotations
    ├── nodes.py                        # 10 tools: status, networks, disks, services, updates, rrd, tasks
    ├── vms.py                          # 17 tools: read + IPs/rrd + lifecycle/clone/migrate + snapshots
    ├── containers.py                   # 13 tools: read + IPs/rrd + lifecycle + snapshots
    ├── storage.py                      # 2 tools: list_storage, get_storage_content
    ├── cluster.py                      # 7 tools: status, resources, backups, ha, pools, log, next_vmid
    └── server_info.py                  # 1 tool: get_server_info (risk level, versions, tool counts)
```

## Key Patterns

- **Lazy connect**: `AppContext.proxmox` is a `@property` that builds the `ProxmoxAPI` on first access, under a `threading.Lock` (double-checked). The lifespan only constructs `Settings()`. Reason: the server must start cleanly even when Proxmox is unreachable (e.g. CI tool-listing, registry sandboxes), so eager `proxmox.version.get()` was removed. The lock matters because the SDK runs sync tool bodies on `anyio.to_thread` workers — concurrent first calls would otherwise each build a client, which under password auth means several logins.
- **Three-tier access**: `PROXMOX_RISK_LEVEL` = `read` (default) / `lifecycle` / `all`. Tools are gated **at registration time**, so a level only ever exposes the tools it allows — they never appear in the client's tool list otherwise:
  - `read` → 32 read-only GET tools
  - `lifecycle` → +14 start/stop/reboot/clone/migrate/create-snapshot (46 total)
  - `all` → +4 delete/rollback (50 total)
- **Tier ≠ annotations**: `@tool(tier=..., annotations=...)` takes both because they answer different questions. `tier` is the *operator's* admission policy; `annotations` is what the *client* is told a call does, so a host can decide whether to prompt. `stop_vm`/`stop_container` are `DESTRUCTIVE` (a force-stop loses in-flight guest state) but live at the `lifecycle` tier — the split exists for exactly that case. `_check_annotations` rejects only the misleading pairings: no annotations at all, `read_only_hint=True` above `read`, and an elevated tier without `read_only_hint=False`. `tests/test_registration.py` asserts the two matrices separately.
- **Registration gating**: `make_gate(mcp, policy)` (in `tools/_common.py`) returns a `@tool(...)` decorator used in place of `@mcp.tool(...)`. It skips registering any tool above `policy.risk_level` or outside `policy.allow`, and wraps the rest. `server.py` reads the level via `config.get_risk_level()` at import (separate from `Settings`, which needs `host`).
- **Policy snapshot**: `register_all(mcp, risk_level, allow)` builds one `Policy` and hands it to every module, then raises if `PROXMOX_TOOLS_ALLOW` named a tool that does not exist. It returns the `Policy`, which is what `get_server_info` reports — registration and the runtime guard therefore describe the same thing.
- **Tool registration**: each `tools/*.py` has a `register(mcp, policy)` function that builds `tool = make_gate(...)` then decorates functions with `@tool()`.
- **Context access**: `_ctx(ctx)` extracts `AppContext` from MCP context. The call-time tier guard lives in `make_gate`, not in the tool bodies: `_guard_tier` wraps every elevated tool and calls `_tier(ctx, required, name)` with the name passed explicitly. It used to read the name from `inspect.stack()[1]`, which reads every frame's source file from disk and would report the wrapper's name once anything wrapped the body.
- **Return format**: all tools return `_json(data)` from `_common.py` — compact `json.dumps` with `separators=(",", ":")`, no emoji, raw JSON for LLM. Indentation is pure token cost on large responses like `get_cluster_resources`. This is also why the tools return `str` rather than `dict`: with a real return annotation the SDK builds an `outputSchema` and `structuredContent`, but it renders the text content with `indent=2` and splits a list into one `TextContent` per item — several times the tokens, for structure the model does not read.
- **Compact listings**: `list_nodes`, `list_vms`, `list_containers` and `get_cluster_resources` project each row through `_compact()` by default (see `GUEST_FIELDS` / `NODE_FIELDS` / `RESOURCE_FIELDS`) and take `verbose=True` for the raw rows. A cluster-wide `get_cluster_resources` was ~10 KB of which most was per-second IO counters and PSI gauges.
- **Secret redaction**: `_json` runs `_redact()` unless `PROXMOX_REDACT_SECRETS=false` — `cipassword`, `password`, `sshkeys`, `ssh-public-keys` become `***redacted***` at any depth, key preserved. On by default because `get_vm_config` otherwise puts a cloud-init hash and the guest's SSH keys into the model's context and, over HTTP, into any client that can reach the endpoint.
- **Write envelope**: write tools return `_accepted(operation, node, upid, vmid=...)` → `{"state":"accepted",...,"poll_with":"get_task_status"}`. The old `{"status":"starting"}` read like a state the guest had already reached; Proxmox has only queued a task.
- **Error normalization**: `make_gate` wraps every registered tool in `_wrap_errors`, which re-raises whatever the body throws as an `mcp.server.mcpserver.exceptions.ToolError` carrying a sentence from `_describe()`. This is not cosmetic: the SDK forwards the message of a `ToolError` but replaces anything else with a bare `Error executing tool <name>`, so without the wrapper a 403, an unreachable host, and even the `_tier` denial all reach the model as no information at all. Covered by `tests/test_errors.py`.
- **Optional Sentry**: `telemetry.py:setup_sentry(version)` starts `sentry_sdk` with `MCPIntegration` only when `SENTRY_DSN` is set — otherwise `sentry_sdk` is never imported. It is called in `server.py` **before** `mcp = MCPServer(...)`, and that order is load-bearing: the integration instruments servers by patching `mcp.server.lowlevel.Server.__init__` from inside `sentry_sdk.init()`, so a server built earlier gets no middleware and reports nothing. `tests/test_telemetry.py` pins the ordering. Errors need a second hook: the SDK catches a tool's exception inside `mcpserver/server.py:_handle_call_tool` and returns an `isError` result *below* the Sentry middleware, so `_wrap_errors` calls `telemetry.report_exception` (a `sys.modules` lookup, so it costs nothing when Sentry is off) — tier denials are skipped, they are policy, not faults. The SDK is an optional extra (`proxmox-ve-mcp[sentry]`, in the Docker image, and in the dev group so CI covers it); a DSN without the package logs a warning and the server runs on. `SENTRY_SEND_DEFAULT_PII` defaults to false because span data would then carry tool arguments and results — `get_vm_config` returns ssh keys and cipassword hashes.
- **Server metadata**: `server.py` passes `instructions=` (discovery order, QEMU vs LXC namespaces, UPID polling, what the risk tiers do), plus `title`, `website_url` and `icons`. The instructions are the cheapest place to prevent guessed node names and VMIDs.
- **Cache hints**: `cache_hints={"tools/list": CacheHint(ttl_ms=3_600_000, scope="public"), ...}`. The tool list is fixed at import by the risk level and the allowlist and cannot change while the process lives; the SDK's default is `ttl_ms=0` ("already stale"), which over HTTP costs a round trip per client start. `public` is only accurate while every caller sees the same list — revisit if per-token authorization ever lands.
- **Transport**: `main()` reads `TransportConfig` from the environment (`PROXMOX_MCP_*`) and optional CLI flags, then either `mcp.run()` or `mcp.run(transport="streamable-http", ..., stateless_http=True, transport_security=...)`. The prefix is `PROXMOX_MCP_` rather than `PROXMOX_` because Kubernetes injects `<SERVICE>_PORT` for every linked Service. `stateless_http` is pinned, not configurable: sessions were removed from the protocol in 2026-07-28. `sse` is rejected with a message rather than passed through — the transport is deprecated upstream.
- **Transport security**: the SDK's `TransportSecurityMiddleware` defaults to `enable_dns_rebinding_protection=False` "for backwards compatibility", i.e. it validates nothing, while the spec makes rejecting a foreign `Origin` a MUST. `TransportConfig.security()` therefore defaults to loopback-only `allowed_hosts` and **refuses to start** on a non-loopback bind without an explicit `PROXMOX_MCP_ALLOWED_HOSTS`; `*` is the explicit opt-out. There is deliberately no authentication in-process — the SDK's `TokenVerifier` requires full `AuthSettings` with `issuer_url` and a `.well-known/oauth-protected-resource` route, which is a lot of machinery for a shared secret; the documented answer is a gateway.
- **Health routes**: `custom_route` (unauthenticated by design) serves `GET /healthz` — process only, never touches Proxmox, because a liveness probe that fails on a Proxmox outage restarts the pod in a loop — and `GET /readyz`, which runs `version.get()` on a worker thread and answers 503 with a `_describe()` sentence. `/readyz` needs a context outside any request, which is why `client.get_app_context()` is a process-wide singleton rather than per-lifespan.
- **Logging**: stderr only, via `logging.basicConfig(stream=sys.stderr)`. Deliberate, not an oversight: MCP's Logging feature (`notifications/message`, `logging/setLevel`) is deprecated in 2026-07-28 with stderr and OpenTelemetry as the replacements. Roots and Sampling are deprecated too — do not add them.

## Commands

```bash
# Local dev
uv sync                          # Install dependencies
uv sync --extra sentry           # + sentry-sdk (optional telemetry)
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
| `PROXMOX_TIMEOUT` | no | 15 | Seconds per API request |
| `PROXMOX_RISK_LEVEL` | no | read | `read`/`lifecycle`/`all` — see "Three-tier access" |
| `PROXMOX_TOOLS_ALLOW` | no | — | CSV of tool names to register, intersected with the tier |
| `PROXMOX_REDACT_SECRETS` | no | true | Mask `cipassword`/`sshkeys` in every response |

*Either token (name+value) or password is required. A half-filled token pair is a
startup error, not a silent fallback to the password.

Transport, read from `os.environ` by `get_transport_config()` (never through `Settings`,
which needs `host`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXMOX_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`; `sse` is rejected |
| `PROXMOX_MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `PROXMOX_MCP_PORT` | `8000` | HTTP port |
| `PROXMOX_MCP_PATH` | `/mcp` | `streamable_http_path` |
| `PROXMOX_MCP_JSON_RESPONSE` | `true` | JSON instead of SSE |
| `PROXMOX_MCP_ALLOWED_HOSTS` | — | CSV; required for a non-loopback bind, `*` opts out |
| `PROXMOX_MCP_ALLOWED_ORIGINS` | — | CSV; empty means same-origin only |

Optional Sentry reporting (standard `SENTRY_*` names, read by `telemetry.py` and by sentry-sdk itself):

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_DSN` | — | Unset = no telemetry, SDK not imported |
| `SENTRY_ENVIRONMENT` | `production` | Environment label |
| `SENTRY_TRACES_SAMPLE_RATE` | `1.0` | Share of tool calls traced; unparsable value warns and falls back |
| `SENTRY_SEND_DEFAULT_PII` | `false` | Tool arguments/results as span data — leaks guest config |
| `SENTRY_RELEASE` | `proxmox-ve-mcp@<version>` | Overrides the release tag |

## Adding New Tools

1. Create or edit a file in `src/proxmox_mcp/tools/`.
2. Add a `register(mcp: MCPServer, policy: Policy)` function; build `tool = make_gate(mcp, policy)` and decorate handlers with `@tool(tier=..., title=..., annotations=...)` (not `@mcp.tool()`) so they are gated and wrapped for errors.
3. Each tool gets `ctx: Context` as first param; use `_ctx(ctx).proxmox` for the API client.
4. Pick `tier=` and `annotations=` independently: the tier is what an operator must enable, the annotation is what the client is warned about. The call-time guard is added automatically for any tier above `read` — do not call `_tier` from a tool body.
5. Register the module in `tools/__init__.py` (pass `policy` through).
6. Add a case to `CASES` in `tests/test_endpoints.py` and the right set in `tests/test_registration.py`. `test_every_tool_has_an_endpoint_case` fails if you skip step 6, by design — proxmoxer builds URLs from attribute access, so a wrong path is invisible to ruff, mypy and a tool-count check alike.

### Tool quality patterns

- **Descriptions** — every `@mcp.tool()` has a one-line docstring (extra details after a blank line). The SDK does **not** parse Google-style `Args:` sections — keep the docstring focused on the tool's purpose, not parameters.
- **Parameter descriptions** — every parameter uses `Annotated[T, Field(description="...")]` from `pydantic`. This is the only way descriptions land in `input_schema.properties[*].description`.
- **Titles** — every tool passes `title="..."`, the spec-preferred human-readable name clients display (distinct from the snake_case `name`).
- **Annotations** — every tool passes `annotations=READ_ONLY | LIFECYCLE | DESTRUCTIVE` (constants in `tools/_common.py`). All three set `open_world_hint=True` (serialized as `openWorldHint` on the wire) because every tool calls the external Proxmox API. Annotations describe the effect on the guest, *not* the tier — `_check_annotations` enforces only the pairings that would mislead a client.
  - `READ_ONLY` — all GETs (`list_*`, `get_*`), tier `read`
  - `LIFECYCLE` — start/shutdown/reboot/suspend/resume/clone/migrate/create-snapshot, tier `lifecycle`
  - `DESTRUCTIVE` — force-stop (tier `lifecycle`), delete/rollback (tier `all`)
- **Naming** — snake_case `verb_noun` (`list_vms`, `get_vm_status`, `start_container`, `delete_container_snapshot`).

Validation snippet (run after edits) — confirms descriptions land in `input_schema` and annotations are attached:

```bash
# PROXMOX_RISK_LEVEL=all exposes every tool so the snippet validates all 50.
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
  - `docker` — builds the Dockerfile without pushing, drives a real MCP handshake over stdio against the image, then runs it again with `PROXMOX_MCP_TRANSPORT=streamable-http` and checks `/healthz`, `/readyz`, the `tools/list` envelope (including `ttlMs`), and that a foreign `Origin` gets 403 and a foreign `Host` gets 421. The HTTP job is what would have caught a deployment reaching into `proxmox_mcp.server.mcp` directly.
- **`.github/dependabot.yml`** — monthly grouped bumps for uv deps, GitHub Actions and the Docker base/uv images.
- **`.github/workflows/docker-publish.yml`** — builds and pushes multi-arch (`amd64` + `arm64`) image to `ghcr.io/akmalovaa/proxmox-mcp` on:
  - push of semver tag `X.Y.Z` (no `v` prefix) → tags `:X.Y.Z`, `:X.Y`, `:sha-<short>`, `:latest`
  - manual `workflow_dispatch` (on a tag ref) → same tagging as above
- SBOM + provenance generated by `docker/build-push-action@v7` (`sbom: true`, `provenance: true`) and attached to the image in GHCR.
- GHA cache (`type=gha`) used for Docker layers.

## Release flow

1. Bump `version` in `pyproject.toml` **and** in `server.json` — two `version` fields there (top level + the pypi package) plus the `:X.Y.Z` tag in the oci `identifier`. The oci package carries **no** `version` field of its own; see step 6. `tests/test_release_metadata.py` fails if any of them disagree, if the two package entries document different environment variables, or if `config.py` reads a variable `server.json` never mentions.
2. `uv lock` to refresh the lockfile (skipping this is what blew up tag 1.0.5; CI's `--locked` now catches it).
3. Commit + push to `main`.
4. `uv build && uv publish dist/proxmox_ve_mcp-X.Y.Z*` — pushes the wheel to PyPI. Token is read from `~/.pypirc` (set `UV_PUBLISH_TOKEN` env var from there since `uv publish` does not read pypirc directly).
5. `git tag X.Y.Z && git push --tags` — `docker-publish.yml` builds and pushes `:X.Y.Z`, `:X.Y`, `:sha-<short>` and moves `:latest` to the new release.
6. *(optional)* Publish to the MCP Registry: `mcp-publisher login github` (interactive device flow), then `mcp-publisher publish` from the repo root. Deliberately not automated — publishing stays a manual, local step, same as PyPI.

   **Run it last.** The registry fetches both artifacts to verify ownership, so PyPI `X.Y.Z` and GHCR `:X.Y.Z` must already exist:
   - **pypi** — verified by the `<!-- mcp-name: io.github.akmalovaa/proxmox-mcp -->` marker on line 1 of README.md, which becomes the PyPI description. Keep it there.
   - **oci** — verified by `LABEL io.modelcontextprotocol.server.name` in the Dockerfile, which must equal `name` in `server.json`.

   Two rules cost a rejected publish on 2.1.1 and are **not in the JSON schema**, so `mcp-publisher validate` passes anyway and only the server rejects them: an oci package must have neither `registryBaseUrl` nor `version` — both live inside `identifier` (`ghcr.io/owner/image:X.Y.Z`). The pypi package keeps both fields.
