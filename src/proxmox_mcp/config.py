import os
from typing import Any, Literal, get_args

from pydantic_settings import BaseSettings

RiskLevel = Literal["read", "lifecycle", "all"]


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


class Settings(BaseSettings):
    model_config = {"env_prefix": "PROXMOX_"}

    host: str
    port: int = 8006
    verify_ssl: bool = False

    # Token auth (preferred)
    user: str = "root@pam"
    token_name: str | None = None
    token_value: str | None = None

    # Password auth (fallback)
    password: str | None = None

    # Risk tier for elevated operations:
    #   read      — only read-only tools
    #   lifecycle — + start/stop/reboot/snapshot-create/clone
    #   all       — + delete/rollback/exec
    risk_level: RiskLevel = "read"

    def get_proxmoxer_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "verify_ssl": self.verify_ssl,
            "user": self.user,
        }
        if self.token_name and self.token_value:
            kwargs["token_name"] = self.token_name
            kwargs["token_value"] = self.token_value
        elif self.password:
            kwargs["password"] = self.password
            kwargs["backend"] = "https"
        else:
            raise ValueError(
                "Either PROXMOX_TOKEN_NAME + PROXMOX_TOKEN_VALUE "
                "or PROXMOX_PASSWORD must be set"
            )
        return kwargs
