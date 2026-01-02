"""List command."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from ..config import load_config
from ..parser import parse_caddyfile, parse_caddyfile_content
from ..ssh import get_server_connection
from . import config_option, console


def list_cmd(
    config_path: Optional[str] = config_option(),
    plain: bool = typer.Option(
        False,
        "--plain",
        "-p",
        help="Output in plain text format",
    ),
) -> None:
    """List all services from local and remote Caddyfile."""
    try:
        with console.status("[bold]Loading config..."):
            config = load_config(config_path)

        local_caddyfile = Path(config.paths.caddyfile).expanduser()
        local_services: dict[str, object] = {}
        remote_services: dict[str, object] = {}

        # Parse local Caddyfile if exists
        if local_caddyfile.exists():
            with console.status("[bold]Parsing local Caddyfile..."):
                for svc in parse_caddyfile(str(local_caddyfile)):
                    local_services[svc.name] = svc

        # Parse remote Caddyfile
        with console.status(f"[bold]Fetching remote Caddyfile ({config.server.host})..."):
            server_conn = get_server_connection(config.server, config.paths.ssh_dir)
            try:
                remote_content = server_conn.download_content(config.server.caddyfile)
                for svc in parse_caddyfile_content(remote_content):
                    remote_services[svc.name] = svc
            except FileNotFoundError:
                pass  # Remote Caddyfile doesn't exist
            finally:
                server_conn.close()

        # Merge all service names
        all_names = set(local_services.keys()) | set(remote_services.keys())

        if not all_names:
            console.print("[yellow]No services found.[/yellow]")
            console.print(
                "[dim]Make sure to add comments in format: # service_name: local_addr[/dim]"
            )
            return

        if plain:
            # Plain text output
            print(f"Services: {len(all_names)}")
            print()
            for name in sorted(all_names):
                local_svc = local_services.get(name)
                remote_svc = remote_services.get(name)
                svc = local_svc or remote_svc

                local_mark = "✓" if local_svc else "✗"
                remote_mark = "✓" if remote_svc else "✗"
                domains_str = ", ".join(svc.domains)

                print(f"{svc.name}")
                print(f"  Address: {svc.local_addr}")
                print(f"  VPS Port: {svc.vps_port}")
                print(f"  Domains: {domains_str}")
                print(f"  Local: {local_mark}  Remote: {remote_mark}")
                print()
        else:
            # Rich table output
            table = Table(title=f"Services ({len(all_names)} found)")
            table.add_column("Service", style="cyan")
            table.add_column("Local Address", style="green")
            table.add_column("VPS Port", style="yellow")
            table.add_column("Domains", style="blue")
            table.add_column("Local", style="white")
            table.add_column("Remote", style="white")

            for name in sorted(all_names):
                local_svc = local_services.get(name)
                remote_svc = remote_services.get(name)

                # Use whichever service exists for display
                svc = local_svc or remote_svc

                domains_str = ", ".join(svc.domains)
                local_status = "[green]✓[/green]" if local_svc else "[red]✗[/red]"
                remote_status = "[green]✓[/green]" if remote_svc else "[red]✗[/red]"

                table.add_row(
                    svc.name,
                    svc.local_addr,
                    str(svc.vps_port),
                    domains_str,
                    local_status,
                    remote_status,
                )

            console.print(table)

    except typer.Exit:
        raise
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
