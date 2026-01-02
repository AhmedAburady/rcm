"""Caddyfile parser to extract service definitions."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Service:
    """Represents a service extracted from Caddyfile."""

    name: str  # From comment: # name: local_addr
    local_addr: str  # From comment: # name: local_addr
    domains: list[str]  # All domains pointing to this service
    vps_port: int  # From reverse_proxy directive

    @property
    def domain(self) -> str:
        """Primary domain (first one)."""
        return self.domains[0] if self.domains else ""


def parse_caddyfile(caddyfile_path: str) -> list[Service]:
    """Parse Caddyfile and extract service definitions.

    Expected format:
    ```
    # service_name: 192.168.1.x:port
    domain.com {
        reverse_proxy 127.0.0.1:5000 {
            ...
        }
    }
    ```

    Args:
        caddyfile_path: Path to the Caddyfile

    Returns:
        List of Service objects
    """
    path = Path(caddyfile_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"Caddyfile not found: {path}")

    content = path.read_text()
    return parse_caddyfile_content(content)


def parse_caddyfile_content(content: str) -> list[Service]:
    """Parse Caddyfile content and extract service definitions.

    Args:
        content: Caddyfile content as string

    Returns:
        List of Service objects (deduplicated by name)
    """
    # Track services by name to deduplicate
    services_by_name: dict[str, Service] = {}
    lines = content.split("\n")

    # Pattern for service comment: # service_name: local_addr
    comment_pattern = re.compile(r"^#\s*(\w+):\s*(.+?)\s*$")

    # Pattern for domain block start: domain.com {
    domain_pattern = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9.-]+)\s*\{")

    # Pattern for reverse_proxy: reverse_proxy [https://]127.0.0.1:PORT or localhost:PORT
    proxy_pattern = re.compile(r"reverse_proxy\s+(?:https?://)?(?:127\.0\.0\.1|localhost):(\d+)")

    pending_service: Optional[tuple[str, str]] = None  # (name, local_addr)

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for service comment
        comment_match = comment_pattern.match(line)
        if comment_match:
            pending_service = (comment_match.group(1), comment_match.group(2))
            i += 1
            continue

        # Check for domain block start
        domain_match = domain_pattern.match(line)
        if domain_match and pending_service:
            domain = domain_match.group(1)
            name, local_addr = pending_service

            # Find reverse_proxy port in this block
            vps_port = None
            brace_count = 1
            j = i + 1

            while j < len(lines) and brace_count > 0:
                block_line = lines[j]
                brace_count += block_line.count("{") - block_line.count("}")

                proxy_match = proxy_pattern.search(block_line)
                if proxy_match and vps_port is None:
                    vps_port = int(proxy_match.group(1))

                j += 1

            if vps_port is not None:
                if name in services_by_name:
                    # Add domain to existing service
                    services_by_name[name].domains.append(domain)
                else:
                    # Create new service
                    services_by_name[name] = Service(
                        name=name,
                        local_addr=local_addr,
                        domains=[domain],
                        vps_port=vps_port,
                    )

            pending_service = None
            i = j
            continue

        # If we hit a domain without a pending service comment, skip it
        if domain_match:
            pending_service = None

        i += 1

    return list(services_by_name.values())
