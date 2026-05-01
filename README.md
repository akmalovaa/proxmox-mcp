# proxmox-mcp

MCP server for managing Proxmox VE through Claude Code, Claude Desktop, and any MCP-compatible client.

39 tools: nodes, QEMU VMs, LXC containers, storage, cluster, tasks, snapshots, command execution.

## Requirements

- Python 3.14+ with [UV](https://docs.astral.sh/uv/), or Docker
- Proxmox VE 7+ with API access

## Installation

```bash
git clone https://github.com/akmalov/proxmox-mcp.git
cd proxmox-mcp
uv sync
```

### Docker

```bash
docker build -t proxmox-mcp .
docker run -i --rm --env-file .env proxmox-mcp
```

Or pass variables directly:

```bash
# Token auth
docker run -i --rm \
  -e PROXMOX_HOST=192.168.1.100 \
  -e PROXMOX_USER=root@pam \
  -e PROXMOX_TOKEN_NAME=mcp \
  -e PROXMOX_TOKEN_VALUE=your-token-value \
  proxmox-mcp

# Password auth
docker run -i --rm \
  -e PROXMOX_HOST=192.168.1.100 \
  -e PROXMOX_USER=root@pam \
  -e PROXMOX_PASSWORD=your-password \
  proxmox-mcp
```

## Proxmox API Token

Create an API token in Proxmox UI:

```
Datacenter → Permissions → API Tokens → Add
  User:                  root@pam
  Token ID:              mcp
  Privilege Separation:  unchecked
```

Save the token value — it is shown only once.

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
PROXMOX_HOST=192.168.1.100
PROXMOX_USER=root@pam
PROXMOX_TOKEN_NAME=mcp
PROXMOX_TOKEN_VALUE=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Optional
PROXMOX_PORT=8006
PROXMOX_VERIFY_SSL=false
PROXMOX_ALLOW_ELEVATED=false
```

Set `PROXMOX_ALLOW_ELEVATED=true` to enable start/stop/reboot/snapshot/clone/exec operations.

Password auth is also supported — set `PROXMOX_PASSWORD` instead of token variables.

## Usage with Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "proxmox": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/proxmox-mcp", "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "mcp",
        "PROXMOX_TOKEN_VALUE": "your-token-value"
      }
    }
  }
}
```

With Docker:

```json
{
  "mcpServers": {
    "proxmox": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm",
        "-e", "PROXMOX_HOST", "-e", "PROXMOX_USER",
        "-e", "PROXMOX_TOKEN_NAME", "-e", "PROXMOX_TOKEN_VALUE",
        "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "mcp",
        "PROXMOX_TOKEN_VALUE": "your-token-value"
      }
    }
  }
}
```

With Docker (password auth):

```json
{
  "mcpServers": {
    "proxmox": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm",
        "-e", "PROXMOX_HOST", "-e", "PROXMOX_USER", "-e", "PROXMOX_PASSWORD",
        "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_PASSWORD": "your-password"
      }
    }
  }
}
```

## Usage with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/proxmox-mcp", "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "mcp",
        "PROXMOX_TOKEN_VALUE": "your-token-value"
      }
    }
  }
}
```

With Docker:

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
        "-e", "PROXMOX_HOST", "-e", "PROXMOX_USER",
        "-e", "PROXMOX_TOKEN_NAME", "-e", "PROXMOX_TOKEN_VALUE",
        "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_TOKEN_NAME": "mcp",
        "PROXMOX_TOKEN_VALUE": "your-token-value"
      }
    }
  }
}
```

With Docker (password auth):

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
        "-e", "PROXMOX_HOST", "-e", "PROXMOX_USER", "-e", "PROXMOX_PASSWORD",
        "proxmox-mcp"],
      "env": {
        "PROXMOX_HOST": "192.168.1.100",
        "PROXMOX_USER": "root@pam",
        "PROXMOX_PASSWORD": "your-password"
      }
    }
  }
}
```

## Tools

### Nodes (7)

| Tool | Description |
|------|-------------|
| `list_nodes` | List all cluster nodes with status, CPU, memory, uptime |
| `get_node_status` | Detailed node metrics (CPU, memory, disk, load, kernel) |
| `get_node_networks` | Network interfaces on a node |
| `get_node_disks` | Physical disks on a node |
| `get_node_tasks` | Recent tasks on a node |
| `get_task_status` | Status of a specific task by UPID |
| `get_task_log` | Log output from a task |

### QEMU VMs (15)

| Tool | Elevated | Description |
|------|----------|-------------|
| `list_vms` | | List all VMs, optionally filter by node |
| `get_vm_status` | | Current VM status (running/stopped, CPU, memory) |
| `get_vm_config` | | VM configuration (hardware, disks, network) |
| `list_vm_snapshots` | | List all snapshots of a VM |
| `start_vm` | yes | Start a VM |
| `stop_vm` | yes | Force-stop a VM |
| `shutdown_vm` | yes | Graceful ACPI shutdown with timeout |
| `reboot_vm` | yes | Reboot via ACPI |
| `suspend_vm` | yes | Suspend a VM |
| `resume_vm` | yes | Resume a suspended VM |
| `clone_vm` | yes | Full or linked clone |
| `create_vm_snapshot` | yes | Create a snapshot |
| `delete_vm_snapshot` | yes | Delete a snapshot |
| `rollback_vm_snapshot` | yes | Rollback to a snapshot |
| `exec_vm_command` | yes | Execute command via QEMU Guest Agent |

### LXC Containers (11)

| Tool | Elevated | Description |
|------|----------|-------------|
| `list_containers` | | List all LXC containers, optionally filter by node |
| `get_container_status` | | Current container status |
| `get_container_config` | | Container configuration |
| `list_container_snapshots` | | List all snapshots |
| `start_container` | yes | Start a container |
| `stop_container` | yes | Force-stop a container |
| `shutdown_container` | yes | Graceful shutdown with timeout |
| `reboot_container` | yes | Reboot a container |
| `create_container_snapshot` | yes | Create a snapshot |
| `delete_container_snapshot` | yes | Delete a snapshot |
| `rollback_container_snapshot` | yes | Rollback to a snapshot |

### Storage (2)

| Tool | Description |
|------|-------------|
| `list_storage` | Storage pools with usage, optionally filter by node |
| `get_storage_content` | Contents of a storage pool (ISOs, backups, images, templates) |

### Cluster (4)

| Tool | Description |
|------|-------------|
| `get_cluster_status` | Cluster health, quorum, node membership |
| `get_cluster_resources` | All resources (VMs, containers, storage, nodes) |
| `get_cluster_backups` | Configured backup jobs |
| `get_next_vmid` | Next available VM/container ID |

## Architecture

```
├── Dockerfile         # Docker image (python:3.14-slim + UV)
├── .dockerignore
src/proxmox_mcp/
├── server.py          # FastMCP instance + entry point
├── config.py          # Pydantic Settings (env vars with PROXMOX_ prefix)
├── client.py          # Proxmoxer connection via lifespan pattern
└── tools/
    ├── nodes.py       # Node info, tasks, disks, networks
    ├── vms.py         # QEMU VM read + lifecycle + snapshots + exec
    ├── containers.py  # LXC read + lifecycle + snapshots
    ├── storage.py     # Storage pools and content
    └── cluster.py     # Cluster status, resources, backups
```

**Key design decisions:**

- **Read-only by default** — destructive tools are gated behind `PROXMOX_ALLOW_ELEVATED=true`
- **API token auth** — recommended; password auth as fallback
- **Lifespan pattern** — single Proxmoxer connection created at startup, shared across all tools
- **Clean JSON output** — no formatting or decorations; LLM processes raw data

## TODO

- [ ] **LXC `exec_container_command` via SSH + `pct exec`** — Proxmox REST API has no LXC exec endpoint, so the tool was removed. Bring it back by SSHing to the target node under a restricted user (sudoers limited to `pct exec`) and running `pct exec <vmid> -- <cmd>`. Requires: `asyncssh` dep, new `Settings` fields (`ssh_user`, `ssh_key_path` or `ssh_password`, optional per-node overrides), gating under `PROXMOX_ALLOW_ELEVATED`. Use cases: patching, log inspection, app deploy/restart, agent-driven diagnostics across the LXC fleet.

## License

MIT
