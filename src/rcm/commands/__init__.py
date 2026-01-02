"""CLI commands for RCM."""

from typing import Optional

import typer
from rich.console import Console

console = Console()


def config_option() -> Optional[str]:
    """Common config path option."""
    return typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml",
    )
