# RCM (Rathole Caddy Manager) - Implementation Plan

## Overview
A Python CLI that uses **Caddyfile as the source of truth**. Parses a local Caddyfile, generates `server.toml` and `client.toml`, then deploys everything via SSH.

## Key Concept: Caddyfile = Source of Truth

```caddyfile
# ntf: 192.168.1.185:8010
ntf.at3ch.com {
    tls /certs/at3ch-cert.pem /certs/at3ch-priv.key
    reverse_proxy 127.0.0.1:5001 {
        ...
    }
}
```

The tool parses this to extract:
- **Service name**: `ntf` (from comment)
- **Local address**: `192.168.1.185:8010` (from comment)
- **Domain**: `ntf.at3ch.com`
- **VPS port**: `5001` (from reverse_proxy)

## Architecture

```
Docker Container (or local)
┌──────────────────────────────┐
│  rcm CLI                     │
│  ┌────────────────────────┐  │
│  │ config.yaml            │  │ (mounted)
│  │ Caddyfile              │  │ (mounted - local copy)
│  │ ~/.ssh/                │  │ (mounted)
│  └────────────────────────┘  │
└──────────┬───────────────────┘
           │
     SSH to both
           │
    ┌──────┴──────┐
    ▼             ▼
┌────────┐    ┌────────────┐
│  VPS   │    │ Home Client│
│        │    │            │
│ Caddy- │    │ client.toml│
│ file   │    │ (generated)│
│ server │    │            │
│ .toml  │    └────────────┘
│(gener-)│
│ ated)  │
└────────┘
```

## Workflow

```
1. Edit local Caddyfile (add/remove domain blocks with # service: local_addr comments)
2. Run: rcm sync
3. Tool parses Caddyfile, generates .toml files, deploys all 3 configs, restarts services
4. Done!
```

## CLI Commands

```bash
rcm sync                     # Parse Caddyfile → generate .toml → deploy all → restart
rcm sync --dry-run           # Show what would be generated without deploying
rcm list                     # Parse Caddyfile and show services table
rcm status                   # Health check: services up? HTTP responding?
rcm restart                  # Restart rathole + caddy on both machines
rcm restart --server         # Restart only VPS services
rcm restart --client         # Restart only home client
```

## File Structure

```
rcm/
├── pyproject.toml
├── README.md
├── PLAN.md
├── main.py                     # CLI entrypoint
├── src/
│   └── rcm/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI commands
│       ├── config.py           # Load config.yaml + Pydantic models
│       ├── parser.py           # Parse Caddyfile → extract services
│       ├── generators.py       # Generate server.toml & client.toml
│       ├── ssh.py              # Fabric SSH to both machines
│       ├── health.py           # Health checks & status
│       └── templates/
│           ├── server.toml.j2
│           └── client.toml.j2
├── config/
│   └── config.yaml             # User fills this in
├── Dockerfile
└── docker-compose.yml
```

## config.yaml Format

```yaml
# Paths (local to where rcm runs / mounted in Docker)
paths:
  caddyfile: "/config/Caddyfile"        # Local Caddyfile path

# VPS (Server) SSH Configuration
server:
  host: "159.69.217.87"
  user: "root"
  ssh_key: "/ssh/id_rsa"
  rathole_config: "/etc/rathole/server.toml"
  caddyfile: "~/rathole-caddy/caddy/Caddyfile"
  caddy_compose_dir: "~/rathole-caddy/caddy"

# Home (Client) SSH Configuration
client:
  host: "192.168.1.X"
  user: "pi"
  ssh_key: "/ssh/id_rsa"
  rathole_config: "/etc/rathole/client.toml"

# Rathole keys (from: rathole --genkey)
rathole:
  bind_port: 2333
  token: "YOUR_TOKEN"                    # From: openssl rand -base64 32
  server_private_key: "PRIVATE_KEY"      # Stays on server
  server_public_key: "PUBLIC_KEY"        # Goes to client
```

## Caddyfile Format (with service comments)

```caddyfile
# chopit: 192.168.1.178:4224
chopit.io {
    tls /certs/chopit-cert.pem /certs/chopit-priv.key
    reverse_proxy 127.0.0.1:5000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}

# ha: 192.168.1.8:8123
ha.aburadyhomelab.com {
    tls /certs/homelab-cert.pem /certs/homelab-priv.key
    reverse_proxy 127.0.0.1:5003 {
        ...
    }
}
```

**Comment pattern:** `# <service_name>: <local_ip>:<port>`

---

## Implementation Steps

### Phase 1: Core Script (Current Focus)

#### Step 1: Config Loading (`config.py`)
- Load `config.yaml` using PyYAML
- Pydantic models for validation:
  - `PathsConfig`: caddyfile path
  - `ServerConfig`: host, user, ssh_key, paths
  - `ClientConfig`: host, user, ssh_key, paths
  - `RatholeConfig`: bind_port, token, keys
  - `Config`: combines all above

#### Step 2: Caddyfile Parser (`parser.py`)
- Read local Caddyfile from `config.paths.caddyfile`
- Parse comment pattern: `# service_name: local_addr`
- Extract domain from block header (e.g., `ntf.at3ch.com`)
- Extract VPS port from `reverse_proxy 127.0.0.1:PORT`
- Return list of `Service` objects:
  ```python
  @dataclass
  class Service:
      name: str           # From comment
      local_addr: str     # From comment (home network IP:port)
      domain: str         # From Caddyfile block
      vps_port: int       # From reverse_proxy directive
  ```

#### Step 3: Template Files
- `templates/server.toml.j2`:
  ```toml
  [server]
  bind_addr = "0.0.0.0:{{ rathole.bind_port }}"
  default_token = "{{ rathole.token }}"

  [server.transport]
  type = "noise"

  [server.transport.noise]
  local_private_key = "{{ rathole.server_private_key }}"

  {% for service in services %}
  [server.services.{{ service.name }}]
  bind_addr = "127.0.0.1:{{ service.vps_port }}"
  {% endfor %}
  ```

- `templates/client.toml.j2`:
  ```toml
  [client]
  remote_addr = "{{ server.host }}:{{ rathole.bind_port }}"
  default_token = "{{ rathole.token }}"

  [client.transport]
  type = "noise"

  [client.transport.noise]
  remote_public_key = "{{ rathole.server_public_key }}"

  {% for service in services %}
  [client.services.{{ service.name }}]
  local_addr = "{{ service.local_addr }}"
  {% endfor %}
  ```

#### Step 4: Generator Module (`generators.py`)
- `generate_server_toml(config, services) -> str`
- `generate_client_toml(config, services) -> str`
- Uses Jinja2 to render templates

#### Step 5: SSH Module (`ssh.py`)
- Uses Fabric library
- `SSHConnection` class with methods:
  - `connect(host, user, key_path)`
  - `upload_file(local_content, remote_path)`
  - `run_command(cmd)`
  - `restart_service(service_name)` - runs `sudo systemctl restart {service_name}`
  - `restart_caddy(compose_dir)` - runs `cd {dir} && docker compose restart`

#### Step 6: CLI Commands (`cli.py`)
- `sync`:
  1. Load config
  2. Read & parse Caddyfile
  3. Generate server.toml and client.toml
  4. SSH to VPS: upload Caddyfile, upload server.toml, restart rathole-server, restart caddy
  5. SSH to client: upload client.toml, restart rathole-client

- `sync --dry-run`:
  1. Load config
  2. Read & parse Caddyfile
  3. Generate configs
  4. Print what would be deployed (no SSH)

- `list`:
  1. Load config
  2. Read & parse Caddyfile
  3. Print services table

### Phase 2: Operations (Later)
- `status` command - health checks
- `restart` command - restart without redeploying

---

## sync Command Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         rcm sync                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Load config.yaml                                         │
│    - Validate with Pydantic                                 │
│    - Get SSH creds, rathole keys, paths                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Parse Caddyfile                                          │
│    - Read from config.paths.caddyfile                       │
│    - Extract services (name, local_addr, domain, vps_port)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Generate configs                                         │
│    - Render server.toml.j2 → server.toml                    │
│    - Render client.toml.j2 → client.toml                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Deploy to VPS (SSH)                                      │
│    - Upload Caddyfile → server.caddyfile path               │
│    - Upload server.toml → server.rathole_config path        │
│    - Run: sudo systemctl restart rathole-server             │
│    - Run: cd caddy_compose_dir && docker compose restart    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Deploy to Client (SSH)                                   │
│    - Upload client.toml → client.rathole_config path        │
│    - Run: sudo systemctl restart rathole-client             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                           Done!
```

---

## Dependencies (pyproject.toml)

```toml
[project]
dependencies = [
    "typer[all]>=0.9.0",      # CLI framework
    "pyyaml>=6.0",            # YAML parsing
    "pydantic>=2.0",          # Config validation
    "jinja2>=3.0",            # Template rendering
    "fabric>=3.0",            # SSH operations
    "rich>=13.0",             # Pretty output
    "httpx>=0.25",            # HTTP health checks (Phase 2)
]
```

---

## Docker Setup (Later)

```yaml
# docker-compose.yml
services:
  rcm:
    build: .
    volumes:
      - ./config:/config:rw          # config.yaml + Caddyfile
      - ~/.ssh:/ssh:ro               # SSH keys
```

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install .
ENTRYPOINT ["rcm"]
```

---

## Output Examples

```
$ rcm list
┌───────────┬─────────────────────┬──────────┬─────────────────────────────┐
│ Service   │ Local Address       │ VPS Port │ Domain                      │
├───────────┼─────────────────────┼──────────┼─────────────────────────────┤
│ chopit    │ 192.168.1.178:4224  │ 5000     │ chopit.io                   │
│ ntf       │ 192.168.1.185:8010  │ 5001     │ ntf.at3ch.com               │
│ contacts  │ 192.168.1.221:6503  │ 5002     │ cont.aburadyhomelab.com     │
│ ha        │ 192.168.1.8:8123    │ 5003     │ ha.aburadyhomelab.com       │
│ analytics │ 192.168.1.156:3001  │ 5004     │ analytics.aburadyhomelab.com│
│ aburady   │ 192.168.1.156:3000  │ 5005     │ aburady.com                 │
└───────────┴─────────────────────┴──────────┴─────────────────────────────┘

$ rcm sync --dry-run
Parsed 6 services from Caddyfile

Generated server.toml:
──────────────────────
[server]
bind_addr = "0.0.0.0:2333"
default_token = "abc123..."
...

Generated client.toml:
──────────────────────
[client]
remote_addr = "159.69.217.87:2333"
...

Would deploy:
  VPS: Caddyfile, server.toml
  Client: client.toml

No changes deployed (dry-run mode)

$ rcm sync
Parsed 6 services from Caddyfile

Deploying to VPS (159.69.217.87)...
  ✓ Uploaded Caddyfile
  ✓ Uploaded server.toml
  ✓ Restarted rathole-server
  ✓ Restarted caddy

Deploying to client (192.168.1.X)...
  ✓ Uploaded client.toml
  ✓ Restarted rathole-client

All 6 services synced!
```
