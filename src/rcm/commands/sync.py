"""Sync command."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from ..config import load_config
from ..generators import generate_client_toml, generate_server_toml
from ..parser import parse_caddyfile, parse_caddyfile_content
from ..ssh import get_client_connection, get_server_connection
from . import config_option, console


def sync_cmd(
    config_path: Optional[str] = config_option(),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be deployed without actually deploying",
    ),
) -> None:
    """Parse Caddyfile, generate configs, and deploy to both machines."""
    try:
        config = load_config(config_path)

        # Check if local Caddyfile exists
        local_caddyfile = Path(config.paths.caddyfile).expanduser()
        if not local_caddyfile.exists():
            console.print("[yellow]No local Caddyfile found.[/yellow]")

            if dry_run:
                console.print()
                console.print("[yellow]Would download:[/yellow]")
                console.print(f"  From: {config.server.host}:{config.server.caddyfile}")
                console.print(f"  To: {local_caddyfile}")
                console.print()
                console.print("[dim]Run 'rcm sync' (without --dry-run) to download.[/dim]")
                return

            console.print("Pulling Caddyfile from remote VPS...")

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

            console.print(f"[green]✓[/green] Caddyfile synced from remote to {local_caddyfile}")

            # Show summary of services
            services = parse_caddyfile(str(local_caddyfile))
            if services:
                console.print(f"  Found [cyan]{len(services)}[/cyan] services")

            console.print()
            console.print("[dim]Edit the local Caddyfile and run 'rcm sync' again to deploy changes.[/dim]")
            return

        services = parse_caddyfile(config.paths.caddyfile)

        if not services:
            console.print("[yellow]No services found in Caddyfile.[/yellow]")
            console.print(
                "[dim]Make sure to add comments in format: # service_name: local_addr[/dim]"
            )
            raise typer.Exit(1)

        console.print(f"Parsed [cyan]{len(services)}[/cyan] services from Caddyfile")

        # Check for removed services
        local_names = {svc.name for svc in services}
        server_conn = get_server_connection(config.server, config.paths.ssh_dir)
        try:
            remote_content = server_conn.download_content(config.server.caddyfile)
            remote_services = parse_caddyfile_content(remote_content)
            remote_names = {svc.name for svc in remote_services}

            removed = remote_names - local_names
            if removed:
                console.print()
                console.print(f"[yellow]Warning:[/yellow] The following {len(removed)} service(s) will be removed:")
                for name in sorted(removed):
                    console.print(f"  [red]- {name}[/red]")
                console.print()

                if not dry_run:
                    confirm = typer.confirm("Continue with sync?")
                    if not confirm:
                        console.print("[yellow]Aborted.[/yellow]")
                        raise typer.Exit(0)
        except FileNotFoundError:
            pass  # Remote doesn't exist yet, no services to remove
        finally:
            server_conn.close()

        # Generate configs
        server_toml = generate_server_toml(config, services)
        client_toml = generate_client_toml(config, services)

        # Read Caddyfile content
        caddyfile_content = Path(config.paths.caddyfile).expanduser().read_text()

        if dry_run:
            # Show what would be deployed
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

    except typer.Exit:
        raise
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
