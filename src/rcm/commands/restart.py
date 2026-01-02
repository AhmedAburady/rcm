"""Restart command."""

from typing import Optional

import typer

from ..config import load_config
from ..ssh import get_client_connection, get_server_connection
from . import config_option, console


def restart_cmd(
    config_path: Optional[str] = config_option(),
    server: bool = typer.Option(
        False,
        "--server",
        "-s",
        help="Restart only VPS services",
    ),
    client: bool = typer.Option(
        False,
        "--client",
        "-l",
        help="Restart only home client services",
    ),
) -> None:
    """Restart rathole and caddy services."""
    try:
        config = load_config(config_path)

        # If neither specified, restart both
        restart_server = server or (not server and not client)
        restart_client = client or (not server and not client)

        if restart_server:
            console.print(f"[bold]Restarting VPS ({config.server.host})...[/bold]")
            server_conn = get_server_connection(config.server, config.paths.ssh_dir)
            try:
                if server_conn.restart_service("rathole-server"):
                    console.print("  [green]✓[/green] Restarted rathole-server")
                else:
                    console.print("  [yellow]![/yellow] Failed to restart rathole-server")

                if server_conn.restart_caddy(config.server.caddy_compose_dir):
                    console.print("  [green]✓[/green] Restarted caddy")
                else:
                    console.print("  [yellow]![/yellow] Failed to restart caddy")
            finally:
                server_conn.close()

        if restart_client:
            console.print(f"[bold]Restarting client ({config.client.host})...[/bold]")
            client_conn = get_client_connection(config.client, config.paths.ssh_dir)
            try:
                if client_conn.restart_service("rathole-client"):
                    console.print("  [green]✓[/green] Restarted rathole-client")
                else:
                    console.print("  [yellow]![/yellow] Failed to restart rathole-client")
            finally:
                client_conn.close()

        console.print()
        console.print("[bold green]Done![/bold green]")

    except typer.Exit:
        raise
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
