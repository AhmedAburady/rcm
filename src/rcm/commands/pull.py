"""Pull command."""

from pathlib import Path
from typing import Optional

import typer

from ..config import load_config
from ..parser import parse_caddyfile
from ..ssh import get_server_connection
from . import config_option, console


def pull_cmd(
    config_path: Optional[str] = config_option(),
) -> None:
    """Pull Caddyfile from remote VPS to local."""
    try:
        config = load_config(config_path)

        local_caddyfile = Path(config.paths.caddyfile).expanduser()

        # Check if local file exists and prompt for confirmation
        if local_caddyfile.exists():
            confirm = typer.confirm(
                f"Local Caddyfile exists at {local_caddyfile}. Overwrite?"
            )
            if not confirm:
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(0)

        # Download from remote
        console.print(f"Downloading from VPS ({config.server.host})...")
        server_conn = get_server_connection(config.server, config.paths.ssh_dir)
        try:
            content = server_conn.download_content(config.server.caddyfile)
        finally:
            server_conn.close()

        # Ensure parent directory exists
        local_caddyfile.parent.mkdir(parents=True, exist_ok=True)

        # Write to local
        local_caddyfile.write_text(content)

        console.print(f"[green]✓[/green] Downloaded Caddyfile to {local_caddyfile}")

        # Show summary of services
        services = parse_caddyfile(str(local_caddyfile))
        if services:
            console.print(f"  Found [cyan]{len(services)}[/cyan] services")

    except typer.Exit:
        raise  # Re-raise typer exits cleanly
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
