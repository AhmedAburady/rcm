"""Configuration loading and Pydantic models."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


DEFAULT_CONFIG_PATH = "~/.config/rcm/config.yaml"


class PathsConfig(BaseModel):
    """Paths configuration."""

    caddyfile: str = Field(description="Path to local Caddyfile")
    ssh_dir: str = Field(default="~/.ssh", description="SSH keys directory")


class ServerConfig(BaseModel):
    """VPS server SSH configuration."""

    host: str = Field(description="VPS IP address")
    user: str = Field(default="root", description="SSH user")
    ssh_key: str = Field(default="/ssh/id_rsa", description="Path to SSH private key")
    rathole_config: str = Field(
        default="/etc/rathole/server.toml",
        description="Remote path for rathole server config",
    )
    caddyfile: str = Field(
        default="~/rathole-caddy/caddy/Caddyfile",
        description="Remote path for Caddyfile",
    )
    caddy_compose_dir: str = Field(
        default="~/rathole-caddy/caddy",
        description="Remote path for caddy docker-compose directory",
    )


class ClientConfig(BaseModel):
    """Home client SSH configuration."""

    host: str = Field(description="Home machine IP address")
    user: str = Field(description="SSH user")
    ssh_key: str = Field(default="/ssh/id_rsa", description="Path to SSH private key")
    rathole_config: str = Field(
        default="/etc/rathole/client.toml",
        description="Remote path for rathole client config",
    )


class RatholeConfig(BaseModel):
    """Rathole tunnel configuration."""

    bind_port: int = Field(default=2333, description="Rathole bind port")
    token: str = Field(description="Shared token for authentication")
    server_private_key: str = Field(description="Server private key (stays on server)")
    server_public_key: str = Field(description="Server public key (goes to client)")


class Config(BaseModel):
    """Root configuration model."""

    paths: PathsConfig
    server: ServerConfig
    client: ClientConfig
    rathole: RatholeConfig


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml. If None, uses CONFIG_PATH env var
                     or defaults to ~/.config/rcm/config.yaml

    Returns:
        Validated Config object
    """
    import os

    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)

    path = Path(config_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(
            f"Config not found: {path}\n"
            f"Create it with: mkdir -p ~/.config/rcm && cp config.yaml.example ~/.config/rcm/config.yaml"
        )

    with open(path) as f:
        data = yaml.safe_load(f)

    return Config(**data)
