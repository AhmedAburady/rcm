"""CLI entry point for RCM."""

from importlib.metadata import version
from typing import Optional

import typer

from .commands.list import list_cmd
from .commands.pull import pull_cmd
from .commands.restart import restart_cmd
from .commands.status import status_cmd
from .commands.sync import sync_cmd


def version_callback(value: bool) -> None:
    if value:
        print(f"rcm {version('rcm')}")
        raise typer.Exit()


app = typer.Typer(
    name="rcm",
    help="Rathole Caddy Manager - Manage Rathole tunnels from Caddyfile",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    pass

# Register commands
app.command(name="list")(list_cmd)
app.command(name="pull")(pull_cmd)
app.command(name="sync")(sync_cmd)
app.command(name="status")(status_cmd)
app.command(name="restart")(restart_cmd)


if __name__ == "__main__":
    app()
