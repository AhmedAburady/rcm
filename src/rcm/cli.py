"""CLI commands for RCM."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config
from .generators import generate_client_toml, generate_server_toml
from .parser import parse_caddyfile
from .ssh import get_client_connection, get_server_connection

app = typer.Typer(
    name="rcm",
    help="Rathole Caddy Manager - Manage Rathole tunnels from Caddyfile",
    no_args_is_help=True,
)
console = Console()


@app.command()
def list(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml",
    ),
) -> None:
    """List all services parsed from Caddyfile."""
    try:
        with console.status("[bold]Loading config..."):
            config = load_config(config_path)

        with console.status("[bold]Parsing Caddyfile..."):
            services = parse_caddyfile(config.paths.caddyfile)

        if not services:
            console.print("[yellow]No services found in Caddyfile.[/yellow]")
            console.print(
                "[dim]Make sure to add comments in format: # service_name: local_addr[/dim]"
            )
            return

        table = Table(title=f"Services ({len(services)} found)")
        table.add_column("Service", style="cyan")
        table.add_column("Local Address", style="green")
        table.add_column("VPS Port", style="yellow")
        table.add_column("Domains", style="blue")

        for svc in services:
            domains_str = ", ".join(svc.domains)
            table.add_row(svc.name, svc.local_addr, str(svc.vps_port), domains_str)

        console.print(table)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def sync(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deployed without actually deploying",
    ),
) -> None:
    """Parse Caddyfile, generate configs, and deploy to both machines."""
    try:
        with console.status("[bold]Loading config..."):
            config = load_config(config_path)

        with console.status("[bold]Parsing Caddyfile..."):
            services = parse_caddyfile(config.paths.caddyfile)

        if not services:
            console.print("[yellow]No services found in Caddyfile.[/yellow]")
            console.print(
                "[dim]Make sure to add comments in format: # service_name: local_addr[/dim]"
            )
            raise typer.Exit(1)

        console.print(f"Parsed [cyan]{len(services)}[/cyan] services from Caddyfile")

        # Generate configs
        server_toml = generate_server_toml(config, services)
        client_toml = generate_client_toml(config, services)

        # Read Caddyfile content
        caddyfile_content = Path(config.paths.caddyfile).expanduser().read_text()

        if dry_run:
            # Show what would be deployed
            # Escape brackets for Rich markup
            from rich.markup import escape

            console.print()
            console.print(
                Panel(escape(server_toml), title="Generated server.toml", border_style="green")
            )
            console.print()
            console.print(
                Panel(escape(client_toml), title="Generated client.toml", border_style="blue")
            )
            console.print()
            console.print("[yellow]Would deploy:[/yellow]")
            console.print(f"  VPS ({config.server.host}): Caddyfile, server.toml")
            console.print(f"  Client ({config.client.host}): client.toml")
            console.print()
            console.print("[dim]No changes deployed (dry-run mode)[/dim]")
            return

        # Deploy to VPS
        console.print()
        console.print(f"[bold]Deploying to VPS ({config.server.host})...[/bold]")

        server_conn = get_server_connection(config.server, config.paths.ssh_dir)
        try:
            # Upload Caddyfile
            server_conn.upload_content(caddyfile_content, config.server.caddyfile)
            console.print("  [green]✓[/green] Uploaded Caddyfile")

            # Upload server.toml
            server_conn.upload_content(server_toml, config.server.rathole_config)
            console.print("  [green]✓[/green] Uploaded server.toml")

            # Restart rathole-server
            if server_conn.restart_service("rathole-server"):
                console.print("  [green]✓[/green] Restarted rathole-server")
            else:
                console.print("  [yellow]![/yellow] Failed to restart rathole-server")

            # Restart caddy
            if server_conn.restart_caddy(config.server.caddy_compose_dir):
                console.print("  [green]✓[/green] Restarted caddy")
            else:
                console.print("  [yellow]![/yellow] Failed to restart caddy")

        finally:
            server_conn.close()

        # Deploy to Client
        console.print()
        console.print(f"[bold]Deploying to client ({config.client.host})...[/bold]")

        client_conn = get_client_connection(config.client, config.paths.ssh_dir)
        try:
            # Upload client.toml
            client_conn.upload_content(client_toml, config.client.rathole_config)
            console.print("  [green]✓[/green] Uploaded client.toml")

            # Restart rathole-client
            if client_conn.restart_service("rathole-client"):
                console.print("  [green]✓[/green] Restarted rathole-client")
            else:
                console.print("  [yellow]![/yellow] Failed to restart rathole-client")

        finally:
            client_conn.close()

        console.print()
        console.print(f"[bold green]All {len(services)} services synced![/bold green]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml",
    ),
) -> None:
    """Check tunnel status on server and client."""
    try:
        with console.status("[bold]Loading config..."):
            config = load_config(config_path)

        table = Table(title="Tunnel Status")
        table.add_column("Machine", style="cyan")
        table.add_column("Service", style="white")
        table.add_column("Status", style="white")

        # Check server
        with console.status(f"[bold]Checking VPS ({config.server.host})..."):
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
        with console.status(f"[bold]Checking client ({config.client.host})..."):
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

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def restart(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml",
    ),
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

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
