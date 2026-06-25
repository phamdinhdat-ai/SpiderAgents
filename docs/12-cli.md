# 12 — CLI Architecture

> Click-based CLI with lazy subcommand loading, 20+ commands.

---

## Entry Points

```toml
# pyproject.toml
[project.scripts]
openspider = "openspider.cli.main:cli"
copaw = "openspider.cli.main:cli"  # legacy alias
```

```python
# src/openspider/__main__.py
from .cli.main import cli
cli()
```

---

## LazyGroup Pattern

```python
# cli/main.py — Subcommands loaded on demand for fast startup
@click.group(cls=LazyGroup, lazy_subcommands={
    "app":      ("openspider.cli.app_cmd", "app_cmd", ".app_cmd"),
    "init":     ("openspider.cli.init_cmd", "init_cmd", ".init_cmd"),
    "doctor":   ("openspider.cli.doctor_cmd", "doctor_cmd", ".doctor_cmd"),
    "daemon":   ("openspider.cli.daemon_cmd", "daemon_group", ".daemon_cmd"),
    "channels": ("openspider.cli.channels_cmd", "channels_group", ".channels_cmd"),
    "chats":    ("openspider.cli.chats_cmd", "chats_group", ".chats_cmd"),
    "clean":    ("openspider.cli.clean_cmd", "clean_cmd", ".clean_cmd"),
    "cron":     ("openspider.cli.cron_cmd", "cron_group", ".cron_cmd"),
    "env":      ("openspider.cli.env_cmd", "env_group", ".env_cmd"),
    "models":   ("openspider.cli.providers_cmd", "models_group", ".providers_cmd"),
    "skills":   ("openspider.cli.skills_cmd", "skills_group", ".skills_cmd"),
    "agents":   ("openspider.cli.agents_cmd", "agents_group", ".agents_cmd"),
    "uninstall":("openspider.cli.uninstall_cmd", "uninstall_cmd", ".uninstall_cmd"),
    "desktop":  ("openspider.cli.desktop_cmd", "desktop_cmd", ".desktop_cmd"),
    "update":   ("openspider.cli.update_cmd", "update_cmd", ".update_cmd"),
    "shutdown": ("openspider.cli.shutdown_cmd", "shutdown_cmd", ".shutdown_cmd"),
    "auth":     ("openspider.cli.auth_cmd", "auth_group", ".auth_cmd"),
    "acp":      ("openspider.cli.acp_cmd", "acp_cmd", ".acp_cmd"),
    "plugin":   ("openspider.cli.plugin_commands", "plugin", ".plugin_commands"),
    "task":     ("openspider.cli.task_cmd", "task_cmd", ".task_cmd"),
})
```

Each tuple: `(module_path, attr_name, import_path)` — only imports when subcommand is invoked.

---

## Command List

| Command | Purpose |
|---------|---------|
| `openspider app` | Start FastAPI server |
| `openspider init` | Initialize workspace |
| `openspider doctor` | System diagnostics |
| `openspider daemon approve` | Approve pending tool guard request |
| `openspider daemon deny` | Deny pending tool guard request |
| `openspider daemon status` | Show pending approvals |
| `openspider channels` | Channel management (list, add, remove, config) |
| `openspider chats` | Chat history management |
| `openspider clean` | Cleanup old data |
| `openspider cron` | Cron job management |
| `openspider env` | Environment variable management |
| `openspider models` | Provider/model management (list, add, remove, config) |
| `openspider skills` | Skill management (list, enable, disable, install) |
| `openspider agents` | Multi-agent management (list, create, delete, chat) |
| `openspider uninstall` | Remove OpenSpider |
| `openspider desktop` | Desktop app launcher |
| `openspider update` | Self-update from PyPI |
| `openspider shutdown` | Graceful shutdown of running service |
| `openspider auth` | Authentication management |
| `openspider acp` | ACP server (stdio JSON-RPC) |
| `openspider plugin` | Plugin management |
| `openspider task` | Background task management |

---

## Global Options

```bash
openspider --host 127.0.0.1 --port 8088 <command>
```

Default host/port read from `last_api.json` (cached from previous run).

---

## Update Command Flow

```
openspider update
    │
    ▼
1. Detect installation (pip, conda, etc.)
2. Fetch latest version from PyPI
3. Compare versions
4. Check for running service
5. Confirm with user
6. Launch update worker in subprocess
7. Worker: pip install openspider==<version>
8. Restart service if needed
```

---

## Process Detection

`process_utils.py` provides process-matching utilities for shutdown and update:

```python
def _matches_openspider_cli_command(command, *subcommands) -> bool:
    # Checks for: -m openspider <cmd>, openspider.exe <cmd>, etc.

def _is_openspider_service_command(command) -> bool:
    # Checks if process is running "openspider app"

def _is_openspider_wrapper_process(name, command) -> bool:
    # Checks for task wrapper processes
```
