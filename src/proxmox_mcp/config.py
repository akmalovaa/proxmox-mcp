import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Self, get_args

from mcp.server.transport_security import TransportSecuritySettings
from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("proxmox_mcp.config")

RiskLevel = Literal["read", "lifecycle", "all"]
Transport = Literal["stdio", "streamable-http"]

# Host header patterns accepted when the operator did not name any. The middleware
# matches either an exact string or a `base:*` prefix, so both forms are needed:
# a proxy may forward `Host: localhost` with no port at all.
_LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "[::1]", "127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOOPBACK_BINDS = {"127.0.0.1", "localhost", "::1", "[::1]"}

# Explicit opt-out of Host validation, for operators who terminate it elsewhere.
_ANY = "*"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def get_risk_level() -> RiskLevel:
    """Read PROXMOX_RISK_LEVEL from the environment for registration-time gating.

    Kept separate from ``Settings`` because tool registration happens at import,
    before (and without) a full ``Settings`` — which requires ``host`` — exists.
    """
    value = os.environ.get("PROXMOX_RISK_LEVEL", "read").lower()
    if value not in get_args(RiskLevel):
        raise ValueError(
            f"PROXMOX_RISK_LEVEL must be one of {get_args(RiskLevel)} (got '{value}')"
        )
    return value  # type: ignore[return-value]


def get_tools_allowlist() -> frozenset[str] | None:
    """Read PROXMOX_TOOLS_ALLOW — an operator-side narrowing of the tool surface.

    Intersects with the risk-level gate rather than replacing it: an allowlisted
    tool above the active tier still stays unregistered. ``None`` means "no
    allowlist", which is not the same as the empty set.
    """
    names = _env_csv("PROXMOX_TOOLS_ALLOW")
    return frozenset(names) if names else None


def get_redact_secrets() -> bool:
    """Whether to mask cloud-init passwords and SSH keys in every tool response.

    On by default: ``get_vm_config`` returns a ``cipassword`` hash and ``sshkeys``,
    and those land in the model's context — and, over HTTP, in anything that can
    reach the endpoint.
    """
    return _env_flag("PROXMOX_REDACT_SECRETS", True)


@dataclass(frozen=True)
class TransportConfig:
    """How the server is served. Read from the environment, not from ``Settings``.

    Same reason as ``get_risk_level``: ``main()`` must be able to start (and fail
    with a transport error) without a reachable Proxmox or complete credentials.
    The ``PROXMOX_MCP_`` prefix rather than ``PROXMOX_`` is deliberate — Kubernetes
    injects ``<SERVICE>_PORT`` for every Service with ``enableServiceLinks``, and a
    Service named ``proxmox`` would otherwise redefine ``PROXMOX_PORT``.
    """

    transport: Transport = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    json_response: bool = True
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()

    @property
    def is_http(self) -> bool:
        return self.transport == "streamable-http"

    def security(self) -> TransportSecuritySettings:
        """Host/Origin validation settings for the Streamable HTTP app.

        The SDK's default is ``enable_dns_rebinding_protection=False`` "for backwards
        compatibility", i.e. no validation at all — while the spec makes rejecting a
        foreign ``Origin`` a MUST. Any page in a browser on the same LAN could
        otherwise drive this server through DNS rebinding.
        """
        if _ANY in self.allowed_hosts:
            logger.warning(
                "PROXMOX_MCP_ALLOWED_HOSTS=* — Host and Origin validation disabled. "
                "Only safe when a proxy in front already does it."
            )
            return TransportSecuritySettings(enable_dns_rebinding_protection=False)

        hosts = list(self.allowed_hosts)
        if not hosts:
            if self.host not in _LOOPBACK_BINDS:
                raise ValueError(
                    f"PROXMOX_MCP_HOST={self.host} exposes the server beyond loopback, "
                    f"so PROXMOX_MCP_ALLOWED_HOSTS must list the Host headers to accept "
                    f"(e.g. 'proxmox-mcp.example.com,proxmox-mcp:8000'). Use '*' to "
                    f"disable the check when a proxy in front already validates it."
                )
            hosts = list(_LOOPBACK_HOSTS)

        # An absent Origin always passes (same-origin, curl, MCP clients); an empty
        # allow list therefore blocks exactly the cross-origin browser requests.
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=list(self.allowed_origins),
        )


def get_transport_config() -> TransportConfig:
    value = os.environ.get("PROXMOX_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
    if value == "sse":
        raise ValueError(
            "PROXMOX_MCP_TRANSPORT=sse is not supported: the HTTP+SSE transport is "
            "deprecated in the MCP spec. Use 'streamable-http'."
        )
    if value not in get_args(Transport):
        raise ValueError(
            f"PROXMOX_MCP_TRANSPORT must be one of {get_args(Transport)} (got '{value}')"
        )

    port = os.environ.get("PROXMOX_MCP_PORT", "8000").strip()
    try:
        port_number = int(port)
    except ValueError:
        raise ValueError(f"PROXMOX_MCP_PORT must be an integer (got '{port}')") from None

    path = os.environ.get("PROXMOX_MCP_PATH", "/mcp").strip() or "/mcp"
    if not path.startswith("/"):
        raise ValueError(f"PROXMOX_MCP_PATH must start with '/' (got '{path}')")

    return TransportConfig(
        transport=value,  # type: ignore[arg-type]
        host=os.environ.get("PROXMOX_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=port_number,
        path=path,
        json_response=_env_flag("PROXMOX_MCP_JSON_RESPONSE", True),
        allowed_hosts=tuple(_env_csv("PROXMOX_MCP_ALLOWED_HOSTS")),
        allowed_origins=tuple(_env_csv("PROXMOX_MCP_ALLOWED_ORIGINS")),
    )


class Settings(BaseSettings):
    model_config = {"env_prefix": "PROXMOX_"}

    host: str
    port: int = 8006
    verify_ssl: bool = False

    # Seconds per Proxmox HTTP request. Proxmoxer's own default is 5s, which a busy
    # /cluster/resources can exceed; the point of setting it at all is that a wedged
    # host must not pin an anyio worker thread forever.
    timeout: int = 15

    # Token auth (preferred)
    user: str = "root@pam"
    token_name: str | None = None
    token_value: str | None = None

    # Password auth (fallback)
    password: str | None = None

    # Risk tier for elevated operations:
    #   read      — only read-only tools
    #   lifecycle — + start/stop/reboot/clone/migrate/snapshot-create
    #   all       — + snapshot delete/rollback
    risk_level: RiskLevel = "read"

    @model_validator(mode="after")
    def _check_auth(self) -> Self:
        """Reject a half-filled token pair instead of silently using the password.

        A typo in ``PROXMOX_TOKEN_NAME`` used to fall through to password auth —
        which usually means running as ``root@pam`` with far more privilege than
        the token was meant to carry, and no sign that anything went wrong.
        """
        if bool(self.token_name) != bool(self.token_value):
            missing = "PROXMOX_TOKEN_VALUE" if self.token_name else "PROXMOX_TOKEN_NAME"
            raise ValueError(
                f"{missing} is missing — API token auth needs both PROXMOX_TOKEN_NAME "
                f"and PROXMOX_TOKEN_VALUE. Unset both to use PROXMOX_PASSWORD."
            )
        if not (self.token_name or self.password):
            raise ValueError(
                "Either PROXMOX_TOKEN_NAME + PROXMOX_TOKEN_VALUE or PROXMOX_PASSWORD "
                "must be set"
            )
        if self.token_name and self.password:
            logger.warning(
                "Both an API token and PROXMOX_PASSWORD are set — using the token."
            )
        if not self.verify_ssl:
            logger.warning(
                "PROXMOX_VERIFY_SSL=false — the Proxmox certificate is not checked. "
                "Fine for a self-signed homelab node, not for anything routed."
            )
        return self

    def get_proxmoxer_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "verify_ssl": self.verify_ssl,
            "user": self.user,
            "timeout": self.timeout,
        }
        if self.token_name and self.token_value:
            kwargs["token_name"] = self.token_name
            kwargs["token_value"] = self.token_value
        else:
            kwargs["password"] = self.password
            kwargs["backend"] = "https"
        return kwargs
