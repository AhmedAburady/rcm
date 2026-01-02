"""SSH operations using Fabric."""

from pathlib import Path
from typing import Optional

from fabric import Connection
from rich.console import Console

from .config import ClientConfig, ServerConfig

console = Console()


class SSHConnection:
    """Wrapper for SSH operations using Fabric."""

    def __init__(self, host: str, user: str, key_path: str):
        """Initialize SSH connection.

        Args:
            host: Remote host IP/hostname
            user: SSH username
            key_path: Path to SSH private key
        """
        self.host = host
        self.user = user
        self.key_path = Path(key_path).expanduser()
        self._conn: Optional[Connection] = None

    def connect(self) -> Connection:
        """Establish SSH connection."""
        if self._conn is None:
            self._conn = Connection(
                host=self.host,
                user=self.user,
                connect_kwargs={"key_filename": str(self.key_path)},
            )
        return self._conn

    def upload_content(self, content: str, remote_path: str) -> None:
        """Upload string content to remote file.

        Args:
            content: File content as string
            remote_path: Remote file path
        """
        import io

        conn = self.connect()
        # Expand ~ in remote path
        if remote_path.startswith("~"):
            result = conn.run("echo $HOME", hide=True)
            home = result.stdout.strip()
            remote_path = remote_path.replace("~", home, 1)

        # Use a temp file approach
        conn.put(io.StringIO(content), remote=remote_path)

    def run_command(self, cmd: str, hide: bool = True) -> str:
        """Run a command on the remote host.

        Args:
            cmd: Command to run
            hide: Whether to hide output

        Returns:
            Command stdout
        """
        conn = self.connect()
        result = conn.run(cmd, hide=hide, warn=True)
        return result.stdout

    def restart_service(self, service_name: str) -> bool:
        """Restart a systemd service.

        Args:
            service_name: Name of the systemd service

        Returns:
            True if successful
        """
        conn = self.connect()
        result = conn.run(f"sudo systemctl restart {service_name}", hide=True, warn=True)
        return result.ok

    def restart_caddy(self, compose_dir: str) -> bool:
        """Restart Caddy via docker compose.

        Args:
            compose_dir: Directory containing docker-compose.yml

        Returns:
            True if successful
        """
        conn = self.connect()
        # Expand ~ in path
        if compose_dir.startswith("~"):
            result = conn.run("echo $HOME", hide=True)
            home = result.stdout.strip()
            compose_dir = compose_dir.replace("~", home, 1)

        result = conn.run(
            f"cd {compose_dir} && docker compose restart",
            hide=True,
            warn=True,
        )
        return result.ok

    def get_service_status(self, service_name: str) -> tuple[bool, str]:
        """Get systemd service status.

        Args:
            service_name: Name of the systemd service

        Returns:
            Tuple of (is_active, status_text)
        """
        conn = self.connect()
        result = conn.run(
            f"systemctl is-active {service_name} 2>/dev/null || echo 'inactive'",
            hide=True,
            warn=True,
        )
        status = result.stdout.strip()
        is_active = status == "active"
        return is_active, status

    def get_docker_status(self, compose_dir: str, service_name: str = "caddy") -> tuple[bool, str]:
        """Get docker compose service status.

        Args:
            compose_dir: Directory containing docker-compose.yml
            service_name: Name of the docker service

        Returns:
            Tuple of (is_running, status_text)
        """
        conn = self.connect()
        # Expand ~ in path
        if compose_dir.startswith("~"):
            result = conn.run("echo $HOME", hide=True)
            home = result.stdout.strip()
            compose_dir = compose_dir.replace("~", home, 1)

        result = conn.run(
            f"cd {compose_dir} && docker compose ps --format '{{{{.State}}}}' {service_name} 2>/dev/null || echo 'not found'",
            hide=True,
            warn=True,
        )
        status = result.stdout.strip()
        is_running = status == "running"
        return is_running, status

    def close(self) -> None:
        """Close the SSH connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def get_server_connection(config: ServerConfig, ssh_dir: str) -> SSHConnection:
    """Create SSH connection to VPS server.

    Args:
        config: Server configuration
        ssh_dir: Directory containing SSH keys

    Returns:
        SSHConnection instance
    """
    key_path = f"{ssh_dir}/{config.ssh_key}"
    return SSHConnection(
        host=config.host,
        user=config.user,
        key_path=key_path,
    )


def get_client_connection(config: ClientConfig, ssh_dir: str) -> SSHConnection:
    """Create SSH connection to home client.

    Args:
        config: Client configuration
        ssh_dir: Directory containing SSH keys

    Returns:
        SSHConnection instance
    """
    key_path = f"{ssh_dir}/{config.ssh_key}"
    return SSHConnection(
        host=config.host,
        user=config.user,
        key_path=key_path,
    )
