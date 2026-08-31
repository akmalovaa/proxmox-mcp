"""Shared fixtures: a fake Proxmox and a way to call tools without a live server."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from mcp.server.mcpserver import MCPServer

from proxmox_mcp.config import RiskLevel, Settings
from proxmox_mcp.tools import register_all

_VERBS = ("get", "post", "put", "delete")


class _State:
    """Shared by every node of one fluent chain — each segment builds a new object."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raises: Exception | None = None


class RecordingProxmox:
    """Stand-in for ``ProxmoxAPI`` that records the REST path each tool builds.

    Proxmoxer turns attribute access and calls into URL segments, so
    ``pve.nodes("pve").qemu(101).status.start.post()`` is only ever checked against
    a real cluster. Recording the segments lets the tests pin every endpoint.
    """

    def __init__(self, parts: tuple[str, ...] = (), state: _State | None = None):
        self._parts = parts
        self._state = state if state is not None else _State()

    def __getattr__(self, name: str) -> Any:
        if name in _VERBS:
            return lambda **params: self._record(name, params)
        return RecordingProxmox((*self._parts, name), self._state)

    def __call__(self, *args: Any) -> RecordingProxmox:
        return RecordingProxmox((*self._parts, *(str(a) for a in args)), self._state)

    def _record(self, method: str, params: dict[str, Any]) -> Any:
        self._state.calls.append(
            {"method": method, "path": "/".join(self._parts), "params": params}
        )
        if self._state.raises is not None:
            raise self._state.raises
        # A list keeps the handful of tools that post-process a response happy;
        # the tools under test only pass it through to json.dumps.
        return [] if method == "get" else "UPID:test"

    def fail_with(self, exc: Exception) -> None:
        """Make every subsequent API call raise ``exc``."""
        self._state.raises = exc

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._state.calls

    @property
    def last(self) -> dict[str, Any]:
        return self._state.calls[-1]


class _AppContext:
    def __init__(self, proxmox: RecordingProxmox, settings: Settings) -> None:
        self.proxmox = proxmox
        self.settings = settings


def build_server(risk_level: RiskLevel = "all") -> MCPServer:
    mcp: MCPServer = MCPServer("test")
    register_all(mcp, risk_level)
    return mcp


def make_context(proxmox: RecordingProxmox, settings_level: RiskLevel = "all") -> Any:
    """A context object shaped like the one the SDK injects into a tool."""
    settings = Settings(host="pve.test", token_name="t", token_value="v", risk_level=settings_level)
    ctx = MagicMock()
    ctx.request_context.lifespan_context = _AppContext(proxmox, settings)
    return ctx


def call_tool(mcp: MCPServer, name: str, args: dict[str, Any], ctx: Any) -> Any:
    """Invoke a tool through the SDK, so validation and error wrapping both run."""
    return asyncio.run(mcp.call_tool(name, args, context=ctx))


@pytest.fixture
def proxmox() -> RecordingProxmox:
    return RecordingProxmox()
