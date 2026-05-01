from typing import Any

from pydantic_settings import BaseSettings


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

    # Elevated operations
    allow_elevated: bool = False

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
