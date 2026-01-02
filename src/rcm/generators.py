"""Template rendering for rathole config files."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import Config
from .parser import Service


def _get_template_env() -> Environment:
    """Get Jinja2 environment with templates directory."""
    templates_dir = Path(__file__).parent / "templates"
    return Environment(
        loader=FileSystemLoader(templates_dir),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def generate_server_toml(config: Config, services: list[Service]) -> str:
    """Generate server.toml content from config and services.

    Args:
        config: Configuration object
        services: List of services parsed from Caddyfile

    Returns:
        Rendered server.toml content
    """
    env = _get_template_env()
    template = env.get_template("server.toml.j2")

    return template.render(
        rathole=config.rathole,
        services=services,
    )


def generate_client_toml(config: Config, services: list[Service]) -> str:
    """Generate client.toml content from config and services.

    Args:
        config: Configuration object
        services: List of services parsed from Caddyfile

    Returns:
        Rendered client.toml content
    """
    env = _get_template_env()
    template = env.get_template("client.toml.j2")

    return template.render(
        server=config.server,
        rathole=config.rathole,
        services=services,
    )
