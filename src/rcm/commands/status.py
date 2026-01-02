"""Status command."""

from typing import Optional

import typer
from rich.table import Table

from ..config import load_config
from ..ssh import get_client_connection, get_server_connection
from . import config_option, console


def status_cmd(
    config_path: Optional[str] = config_option(),
) -> None:
    """Check tunnel status on server and client."""
    try:
        config = load_config(config_path)

        table = Table(title="Tunnel Status")
        table.add_column("Machine", style="cyan")
        table.add_column("Service", style="white")
        table.add_column("Status", style="white")

        # Check server
        console.print(f"Checking VPS ({config.server.host})...")
        server_conn = get_server_connection(config.server, config.paths.ssh_dir)
        try:
            # rathole-server
            is_active, status_text = server_conn.get_service_status("rathole-server")
            status_style = "[green]● active[/green]" if is_active else f"[red]● {status_text}[/red]"
            table.add_row("VPS", "rathole-server", status_style)

            # caddy
            is_running, status_text = server_conn.get_docker_status(config.server.caddy_compose_dir)
            status_style = "[green]● running[/green]" if is_running else f"[red]● {status_text}[/red]"
            table.add_row("VPS", "caddy", status_style)
        finally:
            server_conn.close()

        # Check client
        console.print(f"Checking client ({config.client.host})...")
        client_conn = get_client_connection(config.client, config.paths.ssh_dir)
        try:
            # rathole-client
            is_active, status_text = client_conn.get_service_status("rathole-client")
            status_style = "[green]● active[/green]" if is_active else f"[red]● {status_text}[/red]"
            table.add_row("Client", "rathole-client", status_style)
        finally:
            client_conn.close()

        console.print()
        console.print(table)

    except typer.Exit:
        raise
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
