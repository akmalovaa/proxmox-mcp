# Build the virtualenv in a throwaway stage so uv never ships in the final image.
FROM python:3.14-slim AS builder

# Pinned: `latest` would make every rebuild of an old tag a different image.
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first — this layer is reused until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra sentry --no-install-project

# Then the project itself, so importlib.metadata can report a real version
# over MCP instead of the empty-string fallback.
COPY README.md LICENSE ./
COPY src/ src/
RUN uv sync --frozen --no-dev --extra sentry --no-editable


FROM python:3.14-slim

# How the MCP Registry verifies this image belongs to the server declared in
# server.json — the value must match its "name" field exactly.
LABEL io.modelcontextprotocol.server.name="io.github.akmalovaa/proxmox-mcp"

# stdio transport needs no ports and no writable state, so drop root.
RUN useradd --create-home --uid 10001 mcp

WORKDIR /app
COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv

USER mcp
ENV PATH="/app/.venv/bin:$PATH"

CMD ["proxmox-ve-mcp"]
