# CLI

`openspider` is the command-line tool for openspider. This page is organized from
"get-up-and-running" to "advanced management" — read from top to bottom if
you're new, or jump to the section you need.

> Not sure what "channels", "heartbeat", or "cron" mean? See
> [Introduction](./intro) first.

---

## Getting started

These are the commands you'll use on day one.

### openspider init

First-time setup. Walks you through configuration interactively.

```bash
openspider init              # Interactive setup (recommended for first time)
openspider init --defaults   # Non-interactive, use all defaults (good for scripts)
openspider init --force      # Overwrite existing config files
```

**What the interactive flow covers (in order):**

1. **Default Workspace Initialization** — automatically create default workspace and configuration files.
2. **LLM provider** — select provider, enter API key, choose model
   (**required**).
3. **Environment variables** — optionally add key-value pairs for tools.
4. **HEARTBEAT.md** — edit the heartbeat checklist in your default editor.

### openspider app

Start the openspider server. Everything else — channels, cron jobs, the Console
UI — depends on this.

```bash
openspider app                             # Start on 127.0.0.1:8088
openspider app --reload                    # Auto-reload on code change (dev)
openspider app --log-level debug           # Verbose logging
```

| Option        | Default     | Description                                                   |
| ------------- | ----------- | ------------------------------------------------------------- |
| `--host`      | `127.0.0.1` | Bind host                                                     |
| `--port`      | `8088`      | Bind port                                                     |
| `--reload`    | off         | Auto-reload on file changes (dev only)                        |
| `--log-level` | `info`      | `critical` / `error` / `warning` / `info` / `debug` / `trace` |
| `--workers`   | —           | **[DEPRECATED]** Ignored. openspider always uses 1 worker        |

> **Note:** The `--workers` option is deprecated for stability reasons. openspider is designed to run with a single worker process. Multi-worker mode can cause issues with in-memory state management and WebSocket connections. This option will be removed in a future version.

### Console

Once `openspider app` is running, open `http://127.0.0.1:8088/` in your browser to
access the **Console** — a web UI for chat, channels, cron, skills, models,
and more. See [Console](./console) for a full walkthrough.

If the frontend was not built, the root URL returns a JSON message like `{"message": "openspider Web Console is not available."}` but the API still works.

**To build the frontend:** in the project's `console/` directory run
`npm ci && npm run build`, then copy the output to the package directory:
`mkdir -p src/openspider/console && cp -R console/dist/. src/openspider/console/`.
Docker images and pip packages already include the Console.

### openspider daemon

Inspect status, version, and recent logs without starting a conversation. Same
behavior as sending `/daemon status` etc. in chat (CLI can show local info when
the app is not running).

| Command                        | Description                                                                               |
| ------------------------------ | ----------------------------------------------------------------------------------------- |
| `openspider daemon status`        | Status (config, working dir, memory manager)                                              |
| `openspider daemon restart`       | Print instructions (in-chat /daemon restart does in-process reload)                       |
| `openspider daemon reload-config` | Re-read and validate config (channel/MCP changes need /daemon restart or process restart) |
| `openspider daemon version`       | Version and paths                                                                         |
| `openspider daemon logs [-n N]`   | Last N lines of log (default 100; from `openspider.log` in working dir)                      |

**Multi-Agent Support:** All commands support the `--agent-id` parameter (defaults to `default`).

```bash
openspider daemon status                     # Default agent status
openspider daemon status --agent-id abc123   # Specific agent status
openspider daemon version
openspider daemon logs -n 50
```

### openspider doctor

Read-only diagnostics for your install: root `config.json` validation,
workspaces, `agent.json`, channels, MCP, static console bundle, API
reachability, active LLM / per-agent model checks, and more. **`doctor` by
itself does not repair files** — use the separate **`doctor fix`** subcommand
when you intend to change disk (that path creates backups by default).

```bash
openspider doctor                      # Default checks
openspider doctor --deep               # Extra: enabled-channel probes + local llama notes
openspider doctor --port 8088          # Force API target (see note below)
openspider doctor fix --dry-run        # Preview planned fixes (no writes)
openspider doctor fix -y --only …      # Apply allowlisted fixes (see --help)
```

| Option          | Applies to | Purpose                                                               |
| --------------- | ---------- | --------------------------------------------------------------------- |
| `--timeout`     | `doctor`   | HTTP timeout for API / connectivity checks (default 5s)               |
| `--llm-timeout` | `doctor`   | Timeout for model “ping” checks (default 15s)                         |
| `--deep`        | `doctor`   | Outbound probes for enabled channels; extra notes for `openspider-local` |

**Which host/port does `doctor` hit?** Global `openspider --host` / `--port`
apply to every subcommand, including `doctor`. If you omit them, the CLI
fills missing values from **`last_api` in `config.json`** (updated when
`openspider app` last ran). Only when `last_api` is absent do you get
`127.0.0.1:8088`. If checks target the wrong port, pass `--port` explicitly or
update `last_api`.

**`doctor fix`** applies conservative repairs under the working directory
only.

#### Recommended workflow (preview before apply)

```bash
openspider doctor fix --dry-run
# Narrow to the exact ids you want
openspider doctor fix --dry-run --only ensure-working-dir,ensure-workspace-dirs

# Apply after you confirm the plan
openspider doctor fix --only ensure-working-dir,ensure-workspace-dirs
```

- `--dry-run` prints planned operations and does not write files.
- Read-only validations in the plan (such as jobs.json validation) can still
  return non-zero exit codes on FAIL (useful for CI gates).

#### Fix ids at a glance

Pass comma-separated ids with `--only`.

- Common safe examples:
  - `ensure-working-dir` - create working directory if missing
  - `ensure-workspace-dirs` - create missing agent workspace directories
- For the full list of fix ids and risk semantics, run:
  - `openspider doctor fix --help`
- When `openspider doctor` detects issues, output includes matching fix hints,
  including suggested `doctor fix --dry-run --only ...` commands.

#### Applying risky ids safely

```bash
openspider doctor fix --dry-run --only seed-missing-agent-json,reset-invalid-agent-json
openspider doctor fix -y --only seed-missing-agent-json,reset-invalid-agent-json
```

- Risky ids require `-y` only when applying (without `--dry-run`).
- `--non-interactive` allows only safe + read-only + skill-sync ids and still
  rejects risky ids even with `-y`.

#### Backups and restore

By default, `doctor fix` writes backups to:

- `doctor-fix-backups/<timestamp>/files/`

Restore by copying files from the `files/` subtree back into your working
directory using the same relative paths.

> Avoid `--no-backup` unless you are sure you do not need rollback.

---

## Models & environment variables

Before using openspider you need at least one LLM provider configured. Environment
variables power many built-in tools (e.g. web search).

### openspider models

Manage LLM providers and the active model.

| Command                                  | What it does                                         |
| ---------------------------------------- | ---------------------------------------------------- |
| `openspider models list`                    | Show all providers, API key status, and active model |
| `openspider models config`                  | Full interactive setup: API keys → active model      |
| `openspider models config-key [provider]`   | Configure a single provider's API key                |
| `openspider models set-llm`                 | Switch the active model (API keys unchanged)         |
| `openspider models download <repo_id>`      | Download a local model (llama.cpp)                   |
| `openspider models local`                   | List downloaded local models                         |
| `openspider models remove-local <model_id>` | Delete a downloaded local model                      |

```bash
openspider models list                    # See what's configured
openspider models config                  # Full interactive setup
openspider models config-key modelscope   # Just set ModelScope's API key
openspider models config-key dashscope    # Just set DashScope's API key
openspider models config-key custom       # Set custom provider (Base URL + key)
openspider models set-llm                 # Change active model only
```

#### Local models

openspider can also run models locally via llama.cpp, Ollama, or LM Studio — no API key needed.
But you need to download the corresponding application first, such as [Ollama](https://ollama.com/download) or [LM Studio](https://lmstudio.ai/download).

```bash
# Download a model (auto-selects Q4_K_M GGUF)
openspider models download Qwen/Qwen3-4B-GGUF

# Download from ModelScope
openspider models download Qwen/Qwen2-0.5B-Instruct-GGUF --source modelscope

# List downloaded models
openspider models local

# Delete a downloaded model
openspider models remove-local <model_id>
openspider models remove-local <model_id> --yes   # skip confirmation
```

| Option     | Short | Default       | Description                                                           |
| ---------- | ----- | ------------- | --------------------------------------------------------------------- |
| `--source` | `-s`  | `huggingface` | Download source (`huggingface` or `modelscope`)                       |
| `--file`   | `-f`  | _(auto)_      | Specific filename. If omitted, auto-selects (prefers Q4_K_M for GGUF) |

#### Ollama models

openspider integrates with Ollama to run models locally. Models are dynamically loaded from your Ollama daemon — install Ollama first from [ollama.com](https://ollama.com).

Install the Ollama SDK: `pip install 'openspider[ollama]'` (or re-run the installer with `--extras ollama`)

```bash
# Download an Ollama model
ollama pull mistral:7b
ollama pull qwen3:8b

# List Ollama models
ollama list

# Remove an Ollama model
ollama rm mistral:7b

# Use in config flow (auto-detects Ollama models)
openspider models config           # Select Ollama → Choose from model list
openspider models set-llm          # Switch to a different Ollama model
```

**Key differences from local models:**

- Models come from Ollama daemon (not downloaded by openspider)
- Use `ollama` CLI to manage models (not `openspider models download/remove-local`)
- Model list updates dynamically when you add/remove via Ollama CLI or openspider

> **Note:** You are responsible for ensuring the API key is valid. openspider does
> not verify key correctness. See [Config — LLM Providers](./config#llm-providers).

### openspider env

Manage environment variables used by tools and skills at runtime.

| Command                     | What it does                  |
| --------------------------- | ----------------------------- |
| `openspider env list`          | List all configured variables |
| `openspider env set KEY VALUE` | Set or update a variable      |
| `openspider env delete KEY`    | Delete a variable             |

```bash
openspider env list
openspider env set TAVILY_API_KEY "tvly-xxxxxxxx"
openspider env set GITHUB_TOKEN "ghp_xxxxxxxx"
openspider env delete TAVILY_API_KEY
```

> **Note:** openspider only stores and loads these values; you are responsible for
> ensuring they are correct. See
> [Config — Environment Variables](./config#environment-variables).

---

## Channels

Connect openspider to messaging platforms.

### openspider channels

Manage channel configuration (iMessage, Discord, DingTalk, Feishu, QQ,
Console, etc.) and send messages to channels. **Note:** Use `config` for interactive setup (no `configure`
subcommand); use `remove` to uninstall custom channels (no `uninstall`).

**Alias:** You can use `openspider channel` (singular) as a shorthand for `openspider channels`.

| Command                          | What it does                                                                                                      |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `openspider channels list`          | Show all channels and their status (secrets masked)                                                               |
| `openspider channels send`          | Send a one-way message to a user/session via a channel (requires all 5 parameters)                                |
| `openspider channels install <key>` | Install a channel into `custom_channels/`: create stub or use `--path`/`--url`                                    |
| `openspider channels add <key>`     | Install and add to config; built-in channels only get config entry; supports `--path`/`--url`                     |
| `openspider channels remove <key>`  | Remove a custom channel from `custom_channels/` (built-ins cannot be removed); `--keep-config` keeps config entry |
| `openspider channels config`        | Interactively enable/disable channels and fill in credentials                                                     |

**Multi-Agent Support:** All commands support the `--agent-id` parameter (defaults to `default`).

```bash
openspider channels list                    # See default agent's channels
openspider channels list --agent-id abc123  # See specific agent's channels
openspider channels install my_channel      # Create custom channel stub
openspider channels install my_channel --path ./my_channel.py
openspider channels add dingtalk            # Add DingTalk to config
openspider channels remove my_channel       # Remove custom channel (and from config by default)
openspider channels remove my_channel --keep-config   # Remove module only, keep config entry
openspider channels config                  # Configure default agent
openspider channels config --agent-id abc123 # Configure specific agent
```

The interactive `config` flow lets you pick a channel, enable/disable it, and enter credentials. It loops until you choose "Save and exit".

| Channel      | Fields to fill in                                                                    |
| ------------ | ------------------------------------------------------------------------------------ |
| **iMessage** | Bot prefix, database path, poll interval                                             |
| **Discord**  | Bot prefix, Bot Token, HTTP proxy, proxy auth                                        |
| **DingTalk** | Bot prefix, Client ID, Client Secret, Message Type, Card Template ID/Key, Robot Code |
| **Feishu**   | Bot prefix, App ID, App Secret                                                       |
| **QQ**       | Bot prefix, App ID, Client Secret                                                    |
| **Console**  | Bot prefix                                                                           |

> For platform-specific credential setup, see [Channels](./channels).

#### Sending messages to channels (Proactive Notifications)

> Corresponding skill: **Channel Message**

Use `openspider channels send` to proactively push messages to users/sessions via any configured channel. This is a **one-way send** — no response expected.

When agents have the **channel_message** skill enabled, they can automatically use this command to send proactive notifications when needed.

**Typical use cases:**

- Notify user after task completion
- Scheduled reminders, alerts, status updates
- Push async processing results back to original session
- User explicitly requested "notify me when done"

```bash
# Step 1: Query available sessions
openspider chats list --agent-id my_bot --channel feishu

# Step 2: Send message using queried parameters
openspider channels send \
  --agent-id my_bot \
  --channel feishu \
  --target-user ou_xxxx \
  --target-session session_id_xxxx \
  --text "Task completed!"
```

**Required parameters (all 5):**

- `--agent-id`: Sending agent ID
- `--channel`: Target channel (console/dingtalk/feishu/discord/imessage/qq)
- `--target-user`: User ID (get from `openspider chats list`)
- `--target-session`: Session ID (get from `openspider chats list`)
- `--text`: Message content

**Important:**

- Always query sessions with `openspider chats list` first — do NOT guess `target-user` or `target-session`
- If multiple sessions exist, prefer the most recently updated one
- This is for proactive notifications only; for agent-to-agent communication, use `openspider agents chat` (see "Agents" section below)

**Key differences from `openspider agents chat`:**

- `openspider channels send`: Agent-to-user/channel, one-way, no response
- `openspider agents chat`: Agent-to-agent, bidirectional, with response

---

## Agents

Manage agents and enable inter-agent communication.

### openspider agents

> Corresponding skill: **Multi-Agent Collaboration**

When agents have the **multi_agent_collaboration** skill enabled, they can automatically use `openspider agents chat` to collaborate with other agents as needed.

**Alias:** You can use `openspider agent` (singular) as a shorthand for `openspider agents`.

| Command                 | What it does                                                                 |
| ----------------------- | ---------------------------------------------------------------------------- |
| `openspider agents list`   | List all configured agents with their IDs, names, descriptions, workspaces   |
| `openspider agents create` | Create a new agent configuration and workspace locally                       |
| `openspider agents delete` | Delete a configured agent (stops it if running, removes from agent list)     |
| `openspider agents chat`   | Communicate with another agent (bidirectional, supports multi-turn dialogue) |

```bash
# List all agents
openspider agents list
openspider agent list  # Same with singular alias

# Create a new agent
openspider agents create --name "Data Analyst"
openspider agents create --name "Helper" --template coder --skill web_search --skill pdf_reader
openspider agents create --name "GPT Bot" --provider-id openai --model-id gpt-4

# Delete an agent (default agent cannot be deleted)
openspider agents delete my_agent
openspider agents delete my_agent --remove-workspace  # Also remove workspace directory
openspider agents delete my_agent --yes                # Skip confirmation

# Chat with another agent (real-time mode, one-shot)
openspider agents chat \
  --agent-id my_bot \
  --to-agent helper_bot \
  --text "Please analyze this data"

# Multi-turn conversation (session reuse)
openspider agents chat \
  --agent-id my_bot \
  --to-agent helper_bot \
  --session-id collab_session_001 \
  --text "Follow-up question"

# Complex task (background mode)
openspider agents chat --background \
  --agent-id my_bot \
  --to-agent data_analyst \
  --text "Analyze /data/logs/2026-03-26.log and generate detailed report"
# Returns [TASK_ID: xxx] [SESSION: xxx]

# Check background task status (--to-agent is optional when querying)
openspider agents chat --background \
  --task-id <task_id>
# Status flow: submitted → pending → running → finished
# When finished, result shows: completed (✅) or failed (❌)

# Stream mode (incremental response, real-time mode only)
openspider agents chat \
  --agent-id my_bot \
  --to-agent helper_bot \
  --text "Long analysis task" \
  --mode stream
```

**Required parameters (real-time mode):**

- `--from-agent` (alias: `--agent-id`): Your agent ID (sender)
- `--to-agent`: Target agent ID (recipient)
- `--text`: Message content

**Background task parameters (new):**

- `--background`: Background task mode
- `--task-id`: Check background task status (use with `--background`)

**Optional parameters:**

- `--session-id`: Session ID for multi-turn conversations (auto-generated if omitted)
- `--mode`: Response mode — `final` (default, complete response) or `stream` (incremental)
  - **Note**: `--background` and `--mode stream` are mutually exclusive
- `--base-url`: Override API base URL
- `--timeout`: Timeout in seconds (default: 300)
- `--json-output`: Output full JSON instead of text

**Background mode explanation:**

When tasks are complex (e.g., data analysis, batch processing, report generation), use `--background` to avoid blocking the current agent. After submission, it returns a `task_id` that can be used later to query the task status and result.

**Use cases for background mode**:

- Data analysis and statistics
- Batch file processing
- Generating detailed reports
- Calling slow external APIs
- Complex tasks with uncertain execution time

**Task Status Flow**:

- `submitted`: Task accepted, waiting to start
- `pending`: Queued for execution
- `running`: Currently executing
- `finished`: Completed (result shows `completed` for success or `failed` for error)

**Note:** You can use either `--from-agent` or `--agent-id` — they are equivalent. When checking task status, only `--task-id` is required (`--to-agent` is optional).

**Key differences from `openspider channels send`:**

- `openspider agents chat`: Agent-to-agent, bidirectional, returns response
- `openspider channels send`: Agent-to-user/channel, one-way, no response

---

## Cron (scheduled tasks)

Create jobs that run on a timed schedule — "every day at 9am", "every 2 hours
ask openspider and send the reply". **Requires `openspider app` to be running.**

### openspider cron

| Command                        | What it does                                  |
| ------------------------------ | --------------------------------------------- |
| `openspider cron list`            | List all jobs                                 |
| `openspider cron get <job_id>`    | Show a job's spec                             |
| `openspider cron state <job_id>`  | Show runtime state (next run, last run, etc.) |
| `openspider cron create ...`      | Create a job                                  |
| `openspider cron delete <job_id>` | Delete a job                                  |
| `openspider cron pause <job_id>`  | Pause a job                                   |
| `openspider cron resume <job_id>` | Resume a paused job                           |
| `openspider cron run <job_id>`    | Run once immediately                          |

**Multi-Agent Support:** All commands support the `--agent-id` parameter (defaults to `default`).

### Creating jobs

**Option 1 — CLI arguments (simple jobs)**

Two task types:

- **text** — send a fixed message to a channel on schedule.
- **agent** — ask openspider a question on schedule and deliver the reply.

```bash
# Text: send "Good morning!" to DingTalk every day at 9:00 (default agent)
openspider cron create \
  --type text \
  --name "Daily 9am" \
  --cron "0 9 * * *" \
  --channel dingtalk \
  --target-user "your_user_id" \
  --target-session "session_id" \
  --text "Good morning!"

# Agent: create task for specific agent
openspider cron create \
  --agent-id abc123 \
  --type agent \
  --name "Check todos" \
  --cron "0 */2 * * *" \
  --channel dingtalk \
  --target-user "your_user_id" \
  --target-session "session_id" \
  --text "What are my todo items?"
```

Required: `--type`, `--name`, `--cron`, `--channel`, `--target-user`,
`--target-session`, `--text`.

**Option 2 — JSON file (complex or batch)**

```bash
openspider cron create -f job_spec.json
```

JSON structure matches the output of `openspider cron get <job_id>`.

### Additional options

| Option                       | Default       | Description                                                              |
| ---------------------------- | ------------- | ------------------------------------------------------------------------ |
| `--timezone`                 | user timezone | Timezone for the cron schedule (defaults to `user_timezone` from config) |
| `--enabled` / `--no-enabled` | enabled       | Create enabled or disabled                                               |
| `--mode`                     | `final`       | `stream` (incremental) or `final` (complete response)                    |
| `--base-url`                 | auto          | Override the API base URL                                                |

### Cron expression cheat sheet

Five fields: **minute hour day month weekday** (no seconds).

| Expression     | Meaning                   |
| -------------- | ------------------------- |
| `0 9 * * *`    | Every day at 9:00         |
| `0 */2 * * *`  | Every 2 hours on the hour |
| `30 8 * * 1-5` | Weekdays at 8:30          |
| `0 0 * * 0`    | Sunday at midnight        |
| `*/15 * * * *` | Every 15 minutes          |

---

## Chats (sessions)

Manage chat sessions via the API. **Requires `openspider app` to be running.**

### openspider chats

**Alias:** You can use `openspider chat` (singular) as a shorthand for `openspider chats`.

| Command                                  | What it does                                                  |
| ---------------------------------------- | ------------------------------------------------------------- |
| `openspider chats list`                     | List all sessions (supports `--user-id`, `--channel` filters) |
| `openspider chats get <id>`                 | View a session's details and message history                  |
| `openspider chats create ...`               | Create a new session                                          |
| `openspider chats update <id> --name "..."` | Rename a session                                              |
| `openspider chats delete <id>`              | Delete a session                                              |

**Multi-Agent Support:** All commands support the `--agent-id` parameter (defaults to `default`).

```bash
openspider chats list                        # Default agent's chats
openspider chats list --agent-id abc123      # Specific agent's chats
openspider chats list --user-id alice --channel dingtalk
openspider chats get 823845fe-dd13-43c2-ab8b-d05870602fd8
openspider chats create --session-id "discord:alice" --user-id alice --name "My Chat"
openspider chats create --agent-id abc123 -f chat.json
openspider chats update <chat_id> --name "Renamed"
openspider chats delete <chat_id>
```

---

## Skills

Extend openspider's capabilities with skills (PDF reading, web search, etc.).

### openspider skills

| Command                    | What it does                                              |
| -------------------------- | --------------------------------------------------------- |
| `openspider skills install`   | Install a skill from a supported URL source               |
| `openspider skills uninstall` | Remove a skill from the skill pool or one agent workspace |
| `openspider skills list`      | Show all skills and their enabled/disabled status         |
| `openspider skills config`    | Interactively enable/disable skills (checkbox UI)         |
| `openspider skills info`      | Show local details for one workspace skill                |

**Multi-Agent Support:** All commands support the `--agent-id` parameter (defaults to `default`).

```bash
openspider skills install https://skills.sh/owner/repo/skill  # Import into the local skill pool
openspider skills install https://skills.sh/owner/repo/skill --agent-id abc123  # Import directly into a specific agent workspace
openspider skills uninstall skill-creator  # Remove from the local skill pool
openspider skills uninstall skill-creator --agent-id abc123  # Remove from a specific agent workspace
openspider skills list                   # See default agent's skills
openspider skills list --agent-id abc123 # See specific agent's skills
openspider skills config                 # Configure default agent
openspider skills config --agent-id abc123 # Configure specific agent
openspider skills info [skill_name]               # See default agent's skill details
openspider skills info [skill_name] --agent-id abc123 # See specific agent's skill details
```

In the interactive UI: ↑/↓ to navigate, Space to toggle, Enter to confirm.
A preview of changes is shown before applying.

> For built-in skill details and custom skill authoring, see [Skills](./skills).

---

## Maintenance

### openspider clean

Remove everything under the working directory (default `~/.openspider`).

```bash
openspider clean             # Interactive confirmation
openspider clean --yes       # No confirmation
openspider clean --dry-run   # Only list what would be removed
```

---

## Global options

Every `openspider` subcommand inherits:

| Option          | Default     | Description                                      |
| --------------- | ----------- | ------------------------------------------------ |
| `--host`        | `127.0.0.1` | API host (auto-detected from last `openspider app`) |
| `--port`        | `8088`      | API port (auto-detected from last `openspider app`) |
| `-h` / `--help` |             | Show help message                                |

If the server runs on a non-default address, pass these globally:

```bash
openspider --host 0.0.0.0 --port 9090 cron list
```

## Working directory

All config and data live in `~/.openspider` by default:

- **Global config**: `config.json` (providers, environment variables, agent list)
- **Agent workspaces**: `workspaces/{agent_id}/` (each agent's independent config and data)

```
~/.openspider/
├── config.json              # Global config
└── workspaces/
    ├── default/             # Default agent workspace
    │   ├── agent.json       # Agent config
    │   ├── chats.json       # Conversation history
    │   ├── jobs.json        # Cron jobs
    │   ├── AGENTS.md        # Persona files
    │   └── memory/          # Memory files
    └── abc123/              # Other agent workspace
        └── ...
```

| Variable              | Description                         |
| --------------------- | ----------------------------------- |
| `openspider_WORKING_DIR` | Override the working directory path |
| `openspider_CONFIG_FILE` | Override the config file path       |

See [Config & Working Directory](./config) and [Multi-Agent](./multi-agent) for full details.

---

## Command overview

| Command             | Subcommands                                                                          | Requires server? |
| ------------------- | ------------------------------------------------------------------------------------ | :--------------: |
| `openspider init`      | —                                                                                    |        No        |
| `openspider app`       | —                                                                                    |  — (starts it)   |
| `openspider desktop`   | —                                                                                    |  — (starts it)   |
| `openspider doctor`    | `fix`                                                                                |        No        |
| `openspider daemon`    | `status` · `restart` · `reload-config` · `version` · `logs`                          |        No        |
| `openspider models`    | `list` · `config` · `config-key` · `set-llm` · `download` · `local` · `remove-local` |        No        |
| `openspider env`       | `list` · `set` · `delete`                                                            |        No        |
| `openspider channels`  | `list` · `send` · `install` · `add` · `remove` · `config`                            |     **Yes**      |
| `openspider agents`    | `list` · `create` · `delete` · `chat`                                                |    Partial ¹     |
| `openspider cron`      | `list` · `get` · `state` · `create` · `delete` · `pause` · `resume` · `run`          |     **Yes**      |
| `openspider chats`     | `list` · `get` · `create` · `update` · `delete`                                      |     **Yes**      |
| `openspider skills`    | `install` · `uninstall` · `list` · `config` · `info`                                 |        No        |
| `openspider task`      | —                                                                                    |        No        |
| `openspider auth`      | `reset-password`                                                                     |        No        |
| `openspider plugin`    | `install` · `list` · `info` · `uninstall` · `validate`                               |        No        |
| `openspider acp`       | —                                                                                    |        No        |
| `openspider clean`     | —                                                                                    |        No        |
| `openspider shutdown`  | —                                                                                    |        No        |
| `openspider update`    | —                                                                                    |        No        |
| `openspider uninstall` | —                                                                                    |        No        |

¹ `create` does not require server; `list`, `delete`, and `chat` require server.

---

## Related pages

- [Introduction](./intro) — What openspider can do
- [Console](./console) — Web-based management UI
- [Channels](./channels) — DingTalk, Feishu, iMessage, Discord, QQ setup
- [Heartbeat](./heartbeat) — Scheduled check-in / digest
- [Skills](./skills) — Built-in and custom skills
- [Config & Working Directory](./config) — Working directory and config.json
- [Multi-Agent](./multi-agent) — Multi-agent setup, management, and collaboration
