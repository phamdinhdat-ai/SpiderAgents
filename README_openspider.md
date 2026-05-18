<div align="center">

# OpenSpider

[![PyPI](https://img.shields.io/pypi/v/qwenpaw?color=3775A9&label=PyPI&logo=pypi)](https://pypi.org/project/qwenpaw/)
[![Python Version](https://img.shields.io/badge/python-3.10%20~%20%3C3.14-blue.svg?logo=python&label=Python)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-red.svg?logo=apache&label=License)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-black.svg?logo=python&label=CodeStyle)](https://github.com/psf/black)
[![Discord](https://img.shields.io/badge/Discord-Join_Us-blueviolet.svg?logo=discord)](https://discord.gg/eYMpfnkG8h)

**Self-hosted personal AI agent assistant — deploy locally or in the cloud, connect across any channel, extend with skills.**

[[中文](README_zh.md)] · [[Quick Start](#quick-start)] · [[Architecture](#architecture)] · [[Contributing](#contributing)]

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [System Overview](#system-overview)
  - [Request Lifecycle](#request-lifecycle)
  - [Component Map](#component-map)
- [Quick Start](#quick-start)
  - [pip install](#option-1-pip-install)
  - [Script install](#option-2-script-install)
  - [Docker](#option-3-docker)
  - [ModelScope Studio](#option-4-modelscope-studio)
  - [Desktop Application](#option-5-desktop-application-beta)
- [LLM Providers](#llm-providers)
- [Channels](#channels)
- [Built-in Tools](#built-in-tools)
- [Skills System](#skills-system)
- [Security](#security)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Multi-Agent](#multi-agent)
- [MCP (Model Context Protocol)](#mcp-model-context-protocol)
- [API Reference](#api-reference)
- [CLI Reference](#cli-reference)
- [Local Models](#local-models)
- [Deployment](#deployment)
- [Developer Guide](#developer-guide)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**OpenSpider** is a self-hosted personal AI agent assistant (evolved from QwenPaw). It runs locally or on your own server, connects to any LLM provider, integrates with 17+ messaging channels, and extends its capabilities through a skill system.

> **Core capabilities:**
>
> - **Under your control** — Memory, config, and data fully on your server. No third-party hosting, no data upload.
> - **Every channel** — DingTalk, Feishu, WeChat, Discord, Telegram, Slack, MQTT, iMessage, SIP/voice, and more.
> - **Any model** — OpenAI, Anthropic, Google Gemini, Ollama, LM Studio, OpenRouter, Volcano Engine, Aliyun, and OpenAI-compatible endpoints.
> - **Skills extension** — Built-in scheduling, PDF/Office processing, news digest, email; custom skills auto-loaded, no lock-in.
> - **Multi-agent collaboration** — Multiple independent agents with their own role; inter-agent communication for complex tasks.
> - **Multi-layer security** — Tool guard approval gate, file access control, skill security scanning.

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          OpenSpider                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Console    │  │  17+ Channel │  │  REST API / SSE Stream   │  │
│  │  (Web UI)    │  │  Integrations│  │  (FastAPI)               │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         └─────────────────┴───────────────────────┘                │
│                           │ HTTP/WebSocket                          │
│                    ┌──────▼──────┐                                  │
│                    │   FastAPI   │ AuthMiddleware                   │
│                    │    app      │ AgentContextMiddleware           │
│                    └──────┬──────┘ CORSMiddleware                  │
│                           │                                         │
│              ┌────────────▼─────────────────┐                      │
│              │   DynamicMultiAgentRunner     │                      │
│              │   (routes via X-Agent-Id)     │                      │
│              └────────────┬─────────────────┘                      │
│                           │                                         │
│         ┌─────────────────▼──────────────────────┐                 │
│         │          MultiAgentManager              │                 │
│         │   (lazy-loads Workspace per agent)      │                 │
│         └─────────────────┬──────────────────────┘                 │
│                           │                                         │
│              ┌────────────▼────────────┐                           │
│              │        Workspace        │  per-agent isolation       │
│              │  ┌──────────────────┐   │                           │
│              │  │     Runner       │   │  session / turn mgmt      │
│              │  └────────┬─────────┘   │                           │
│              │           │             │                           │
│              │  ┌────────▼──────────┐  │                           │
│              │  │  QwenPawAgent     │  │  ReActAgent subclass      │
│              │  │  ToolGuardMixin   │  │  approval gate            │
│              │  └────────┬──────────┘  │                           │
│              └───────────┼─────────────┘                           │
│                          │                                          │
│        ┌─────────────────┼──────────────────────┐                  │
│        │                 │                       │                  │
│   ┌────▼─────┐   ┌───────▼──────┐   ┌──────────▼──────┐           │
│   │  Tools   │   │   Skills     │   │  LLM Provider   │           │
│   │ (built-in│   │  (Markdown + │   │  (OpenAI/Claude │           │
│   │  + MCP)  │   │   scripts)   │   │  /Gemini/Ollama)│           │
│   └──────────┘   └──────────────┘   └─────────────────┘           │
│                                                                     │
│   ┌──────────────────────────────────────────────────────────────┐ │
│   │  Support systems: Memory · ApprovalService · APScheduler ·   │ │
│   │  TokenUsage · Backup · ProviderManager · LocalModelManager   │ │
│   └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
Channel / HTTP request
        │
        ▼
AuthMiddleware → AgentContextMiddleware (reads X-Agent-Id header)
        │
        ▼
DynamicMultiAgentRunner.stream_query()
        │
        ▼
MultiAgentManager.get_workspace(agent_id)  ← lazy create on first request
        │
        ▼
Runner.run(message, session)
        │
        ▼
QwenPawAgent._acting(tool_call)
        │
        ├── ToolGuardMixin checks ExecLevel
        │       ├── FREE → execute immediately
        │       ├── APPROVAL_REQUIRED → ApprovalService.create_pending()
        │       │       └── suspend runner, await user resolve, resume
        │       └── BLOCKED → raise exception
        │
        ├── Tool execution (shell / file / browser / agent / MCP ...)
        │
        ▼
LLM Provider (with rate limiter + retry + token usage tracking)
        │
        ▼
SSE stream → Console / Channel
```

### Component Map

| Layer | Package path | Key classes |
|---|---|---|
| Application | `app/_app.py` | `DynamicMultiAgentRunner`, `AgentApp` |
| Agent | `agents/react_agent.py` | `QwenPawAgent`, `ToolGuardMixin` |
| Runner | `app/runner/` | `Runner`, `MultiAgentManager`, `Workspace`, `TaskTracker` |
| Providers | `providers/` | `ProviderManager`, `OpenAIProvider`, `AnthropicProvider`, … |
| Channels | `app/channels/` | `BaseChannel` subclasses (17 types) |
| Skills | `agents/skill_system/` | `SkillSystem`, skill directories |
| Security | `security/tool_guard/` | `ToolGuardMixin`, `ApprovalService`, YAML rule engine |
| Memory | `agents/memory/` | `InMemoryMemory`, compaction |
| MCP | `app/mcp/` | `HttpStatefulClient`, `StdIOStatefulClient` |
| Plans | `plan/` | `PlanStateResponse`, `SubTaskResponse` |
| Config | `config/config.py` | `load_config()` |
| Crons | `app/crons/` | APScheduler-based scheduled tasks |
| Token usage | `token_usage/` | `UsageBuffer`, `UsageStorage`, `ModelWrapper` |
| Backup | `backup/` | `BackupOrchestration` |
| Plugins | `plugins/` | `PluginRegistry`, `PluginLoader` |

---

## Quick Start

### Option 1: pip install

```bash
pip install qwenpaw
qwenpaw init --defaults
qwenpaw app
```

Open **http://127.0.0.1:8088/** → **Settings → Models** to configure your API key and model.

---

### Option 2: Script install

No Python setup required. The script installs `uv`, creates a virtual environment, and installs all dependencies.

**macOS / Linux:**
```bash
curl -fsSL https://qwenpaw.agentscope.io/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://qwenpaw.agentscope.io/install.ps1 | iex
```

**Windows (CMD):**
```cmd
curl -fsSL https://qwenpaw.agentscope.io/install.bat -o install.bat && install.bat
```

Then:
```bash
qwenpaw init --defaults
qwenpaw app
```

---

### Option 3: Docker

```bash
docker run -p 127.0.0.1:8088:8088 \
  -v qwenpaw-data:/app/working \
  -v qwenpaw-secrets:/app/working.secret \
  -v qwenpaw-backups:/app/working.backups \
  agentscope/qwenpaw:latest
```

Pass API keys as environment variables:
```bash
docker run -p 127.0.0.1:8088:8088 \
  -e DASHSCOPE_API_KEY=sk-xxx \
  -v qwenpaw-data:/app/working \
  -v qwenpaw-secrets:/app/working.secret \
  agentscope/qwenpaw:latest
```

> **Connecting to Ollama on host:** Add `--add-host=host.docker.internal:host-gateway` and use `http://host.docker.internal:11434` as the base URL in Settings.

Also available via [docker-compose.openspider.yml](docker-compose.openspider.yml):
```bash
docker compose -f docker-compose.openspider.yml up
```

---

### Option 4: ModelScope Studio

[ModelScope Studio](https://modelscope.cn/studios/fork?target=AgentScope/QwenPaw) — one-click cloud setup, no local install. Set your Studio to **non-public**.

---

### Option 5: Desktop Application (Beta)

Download from [GitHub Releases](https://github.com/agentscope-ai/QwenPaw/releases):
- **Windows**: `QwenPaw-Setup-<version>.exe`
- **macOS**: `QwenPaw-<version>-macOS.zip`

Zero configuration — double-click to run.

---

## LLM Providers

OpenSpider supports these LLM providers out of the box (configured via **Settings → Models** or environment variables):

| Provider | Module | Type | Multimodal | Notes |
|---|---|---|---|---|
| **OpenAI** | `openai_provider.py` | Cloud | ✅ | GPT-4o, GPT-4.1, o1, o3, etc. |
| **Anthropic** | `anthropic_provider.py` | Cloud | ✅ | Claude 3.x / 4.x series |
| **Google Gemini** | `gemini_provider.py` | Cloud | ✅ | `google-genai` SDK |
| **OpenRouter** | `openrouter_provider.py` | Cloud | ✅ | 100+ models via one API key |
| **Volcano Engine** | via OpenAI compat | Cloud | ✅ | Doubao models |
| **Aliyun (DashScope)** | via OpenAI compat | Cloud | ✅ | Qwen series; set `DASHSCOPE_API_KEY` |
| **Ollama** | `ollama_provider.py` | Local | ✅ | Run `ollama serve` first |
| **LM Studio** | `lmstudio_provider.py` | Local | ✅ | Run LM Studio server first |
| **OpenAI-compatible** | `openai_provider.py` | Any | depends | Any endpoint compatible with OpenAI API |

Supporting infrastructure: `rate_limiter.py` (QPM/concurrent limits), `retry_chat_model.py` (exponential backoff), `multimodal_prober.py` (capability detection), `model_capability_cache.py`.

**Key env vars:**
| Variable | Purpose |
|---|---|
| `DASHSCOPE_API_KEY` | Aliyun / DashScope |
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic |
| `GEMINI_API_KEY` | Google Gemini |

---

## Channels

OpenSpider connects to 17 messaging channels. Configure them via **Settings → Channels** in the console or the CLI.

| Channel | Module | Protocol / Platform |
|---|---|---|
| **Console** | `channels/console/` | Built-in web UI + REST |
| **DingTalk** | `channels/dingtalk/` | DingTalk stream (event-driven) |
| **Feishu / Lark** | `channels/feishu/` | Feishu bot (webhook + stream) |
| **WeChat** | `channels/wechat/` | WeChat public account / MP |
| **WeCom** | `channels/wecom/` | Enterprise WeChat / WeCom |
| **QQ** | `channels/qq/` | QQ bot |
| **Telegram** | `channels/telegram/` | Telegram Bot API |
| **Discord** | `channels/discord_/` | Discord bot |
| **Matrix** | `channels/matrix/` | Matrix protocol (Element, etc.) |
| **Mattermost** | `channels/mattermost/` | Mattermost webhook/bot |
| **MQTT** | `channels/mqtt/` | MQTT broker message bus |
| **OneBot** | `channels/onebot/` | OneBot v11 protocol (QQ) |
| **iMessage** | `channels/imessage/` | macOS iMessage (AppleScript) |
| **SIP / Phone** | `channels/sip/` | VoIP via Twilio / SIP |
| **Voice** | `channels/voice/` | Voice input (Whisper transcription) |
| **Xiaoyi** | `channels/xiaoyi/` | Xiaoyi |
| **QR Auth** | `channels/qrcode_auth_handler.py` | QR-code-based channel auth |

Each channel inherits `BaseChannel` and implements `start()`, `stop()`, and message handling. See [`app/channels/`](src/openspider/app/channels/) for implementation details.

---

## Built-in Tools

The agent has access to these tool categories at all times (registered at construction):

| Category | Tools | Description |
|---|---|---|
| **Shell** | `execute_shell_command` | Run shell commands (subject to tool guard) |
| **File I/O** | `read_file`, `write_file`, `edit_file` | Read, create, and patch files |
| **File Search** | `glob_search`, `grep_search` | Find files and search content |
| **Browser** | `browser_use`, browser snapshot | Full browser automation via Playwright |
| **Desktop** | `desktop_screenshot` | Capture desktop screen |
| **Media** | `view_image`, `view_video` | View/analyze images and video files |
| **File Send** | `send_file_to_user` | Push files to the user's session |
| **Agent Mgmt** | `list_agents`, `chat_with_agent`, `delegate_external_agent`, `check_agent_task`, `submit_to_agent` | Multi-agent coordination |
| **Time** | `get_current_time`, `set_user_timezone` | Time and timezone utilities |
| **Token Usage** | `get_token_usage` | Query LLM token consumption |

Additional tools are available via MCP servers (see [MCP](#mcp-model-context-protocol)).

---

## Skills System

Skills extend the agent's knowledge and behavior beyond built-in tools. Each skill is a directory containing a `SKILL.md` file (the instruction document loaded into the agent's context) plus optional Python scripts.

### Directory Structure

```
skills/
├── my-skill-en/          # English variant
│   ├── SKILL.md          # Skill instructions (Markdown)
│   └── helper.py         # Optional supporting scripts
└── my-skill-zh/          # Chinese variant
    └── SKILL.md
```

### Built-in Skills

| Skill | Purpose |
|---|---|
| `guidance` | Agent onboarding and help instructions |
| `cron` | Create and manage APScheduler-based scheduled tasks |
| `news` | News digest and hot-topic aggregation |
| `browser_cdp` | Browser automation via Chrome DevTools Protocol |
| `browser_visible` | Visible browser mode for interactive automation |
| `pdf` | PDF document reading and extraction |
| `docx` | Microsoft Word document processing |
| `pptx` | PowerPoint presentation processing |
| `xlsx` | Excel spreadsheet processing |
| `file_reader` | Generic file reading for various formats |
| `channel_message` | Send messages to specific channels from agent |
| `chat_with_agent` | Inter-agent communication protocol |
| `multi_agent_collaboration` | Coordinate complex tasks across multiple agents |
| `make_plan` | Break tasks into tracked sub-task plans |
| `dingtalk_channel` | DingTalk-specific interaction patterns |
| `himalaya` | Email management via Himalaya CLI |
| `QA_source_index` | Built-in Q&A knowledge base lookup |

### Creating Custom Skills

1. Create a directory under your working directory's `skills/` folder (e.g., `~/.qwenpaw/skills/my-skill-en/`)
2. Add a `SKILL.md` with natural language instructions for the agent
3. Restart or use `/reload` — skills are auto-discovered

Skills are scanned for security risks before loading (see [Security](#security)).

---

## Security

OpenSpider implements a multi-layer security model based on the **ToolGuardMixin** architecture.

### Approval Gate

Every tool call passes through `ToolGuardMixin._acting()` before execution:

```
Tool call requested
       │
       ▼
ToolGuardMixin evaluates against YAML rules
       │
       ├── ExecLevel.FREE → execute immediately
       │
       ├── ExecLevel.APPROVAL_REQUIRED
       │       └── ApprovalService.create_pending(request_id)
       │               │
       │               ├── Suspend runner
       │               ├── Notify user via SSE (with heartbeat every 15s)
       │               └── On user resolve → resume runner
       │
       └── ExecLevel.BLOCKED → reject, raise exception
```

### Security Rules

Rules live in [`security/tool_guard/`](src/openspider/security/tool_guard/) as YAML files. Current categories:

| Rule file | Detects |
|---|---|
| `dangerous_shell_commands.yaml` | `rm -rf /`, fork bombs, reverse shells, privilege escalation, etc. |

Rule structure (YAML):
```yaml
- name: "rm_rf_root"
  pattern: "rm\\s+-[a-z]*r[a-z]*f[a-z]*\\s+/"
  level: BLOCKED
  message: "Recursive force-delete from root is not allowed"
```

### Skill Security Scanning

Before any skill is installed, `security/skill_scanner/` automatically scans the `SKILL.md` for:
- Prompt injection attempts
- Command injection patterns
- Hardcoded secrets / credentials
- Data exfiltration instructions
- Social engineering patterns

### Additional Protections

| Feature | Description |
|---|---|
| File access guard | Restricts agent access to sensitive paths (`~/.ssh`, key files, system dirs) |
| Web authentication | Optional login for the console — set `QWENPAW_AUTH_ENABLED=true` |
| Local deployment | All data stored locally; only conversation content is sent to your chosen LLM API |

---

## Configuration & Environment Variables

OpenSpider is configured via environment variables (current prefix: `QWENPAW_*`, migration to `OPENSPIDER_*` is in progress with backward-compat fallback).

### Core

| Variable | Default | Description |
|---|---|---|
| `QWENPAW_WORKING_DIR` | `~/.qwenpaw` | Working directory for data, memory, config |
| `QWENPAW_SECRET_DIR` | `~/.qwenpaw.secret` | Directory for secrets and API keys |
| `QWENPAW_RUNNING_IN_CONTAINER` | `false` | Set `true` inside Docker/K8s |
| `QWENPAW_OPENAPI_DOCS` | `false` | Enable `/docs` (OpenAPI UI) |
| `QWENPAW_CORS_ORIGINS` | `""` | Comma-separated allowed CORS origins |
| `QWENPAW_AUTH_ENABLED` | `false` | Enable web authentication |

### LLM Concurrency

| Variable | Default | Description |
|---|---|---|
| `QWENPAW_LLM_MAX_CONCURRENT` | `10` | Max parallel LLM requests |
| `QWENPAW_LLM_MAX_QPM` | `600` | Max queries per minute |
| `QWENPAW_LLM_MAX_RETRIES` | `3` | Retry attempts on failure |
| `QWENPAW_LLM_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `QWENPAW_LLM_BACKOFF_CAP` | `10.0` | Exponential backoff cap (seconds) |
| `QWENPAW_LLM_ACQUIRE_TIMEOUT` | `300` | Semaphore acquire timeout (seconds) |

### Security / Approval

| Variable | Default | Description |
|---|---|---|
| `QWENPAW_TOOL_GUARD_APPROVAL_TIMEOUT_SECONDS` | `300` | Approval request timeout |
| `QWENPAW_TOOL_GUARD_APPROVAL_HEARTBEAT_INTERVAL` | `15` | SSE heartbeat interval (seconds) |

### Memory

| Variable | Default | Description |
|---|---|---|
| `QWENPAW_MEMORY_COMPACT_RATIO` | `0.7` | Trigger compaction when memory hits this ratio of limit |
| `QWENPAW_MEMORY_COMPACT_KEEP_RECENT` | `3` | Messages to keep uncompressed during compaction |

### Working Directory Structure (auto-created)

```
~/.qwenpaw/
├── config.yaml          # Agent configuration
├── memory/              # Long-term memory storage
├── skills/              # User-installed custom skills
├── workspace/           # Per-agent workspace data
└── logs/                # Application logs

~/.qwenpaw.secret/
├── providers.yaml       # LLM provider API keys
└── auth.yaml            # Web auth credentials (if enabled)
```

---

## Multi-Agent

OpenSpider supports multiple independent agent instances, each with isolated memory, config, and workspace.

### How it Works

- Each agent is identified by a UUID (`agent_id`)
- The `MultiAgentManager` lazily creates a `Workspace` for each agent on first request
- Requests are routed by the `X-Agent-Id` HTTP header
- Agents can communicate via the `chat_with_agent` / `delegate_external_agent` tools

### Creating Agents

Via the console (**Settings → Agents → New Agent**) or CLI:
```bash
qwenpaw agents create --name "Research Agent" --model gpt-4o
qwenpaw agents list
```

### Inter-Agent Communication

Enable the `multi_agent_collaboration` or `chat_with_agent` skill on an agent. Then from a conversation:

```
User: Delegate this research task to the Research Agent
Agent: [calls chat_with_agent(agent_id="...", message="...")]
```

Available agent tools:

| Tool | Description |
|---|---|
| `list_agents` | List all available agents |
| `chat_with_agent` | Send a message to another agent and get response |
| `delegate_external_agent` | Fire-and-forget task delegation |
| `check_agent_task` | Poll status of a delegated task |
| `submit_to_agent` | Submit input/feedback to a running agent task |

---

## MCP (Model Context Protocol)

OpenSpider supports the Model Context Protocol for connecting external tool servers.

### Transport Types

| Type | Class | Use case |
|---|---|---|
| HTTP Stateful | `HttpStatefulClient` | Remote MCP servers over HTTP |
| StdIO | `StdIOStatefulClient` | Local MCP servers via subprocess |

### Configuration

Configure MCP servers via **Settings → MCP** in the console, or in `config.yaml`:

```yaml
mcp_servers:
  - name: "filesystem"
    type: "stdio"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  - name: "my-api"
    type: "http"
    url: "http://localhost:3000/mcp"
```

MCP tools are automatically discovered from connected servers and made available to the agent alongside built-in tools.

---

## API Reference

The FastAPI application exposes 25+ router groups at **http://localhost:8088/api/v1/**. Enable the OpenAPI docs with `QWENPAW_OPENAPI_DOCS=true`.

| Router | Path prefix | Description |
|---|---|---|
| `agents` | `/agents` | Create, list, update, delete agents |
| `agent_scoped` | `/agents/{id}/...` | Per-agent operations |
| `agent_stats` | `/agents/{id}/stats` | Agent usage statistics |
| `agent_status` | `/agents/{id}/status` | Agent running status |
| `approval` | `/approvals` | Tool guard approval requests |
| `auth` | `/auth` | Authentication (login, logout, token) |
| `backup` | `/backup` | Backup and restore operations |
| `config` | `/config` | Agent configuration CRUD |
| `console` | `/console` | Console WebSocket / SSE |
| `envs` | `/envs` | Environment variable store |
| `files` | `/files` | File upload/download |
| `local_models` | `/local-models` | Download and manage local models |
| `mcp` | `/mcp` | MCP server config and status |
| `messages` | `/messages` | Chat history |
| `plan` | `/plan` | Sub-task plan state |
| `plugins` | `/plugins` | Plugin management |
| `providers` | `/providers` | LLM provider config |
| `schemas_config` | `/schemas` | Config schema introspection |
| `settings` | `/settings` | Global settings |
| `skills` | `/skills` | Skill install/uninstall/list |
| `skills_stream` | `/skills/stream` | Skill install SSE progress |
| `token_usage` | `/token-usage` | Token consumption history |
| `tools` | `/tools` | Available tools list |
| `voice` | `/voice` | Voice input processing |
| `workspace` | `/workspace` | Workspace management |

---

## CLI Reference

All CLI commands are available via `qwenpaw` (also `openspider` and `copaw` aliases):

```bash
qwenpaw <command> [options]
```

| Command | Description |
|---|---|
| `init` | Initialize working directory and configuration (interactive or `--defaults`) |
| `app` | Start the OpenSpider server |
| `app --port 8888` | Start on a custom port |
| `stop` | Stop a running server |
| `agents list` | List all configured agents |
| `agents create` | Create a new agent |
| `providers list` | List configured LLM providers |
| `providers add` | Add a new LLM provider |
| `channels list` | List configured channels |
| `channels add` | Configure a new channel |
| `skills list` | List installed skills |
| `skills install <path>` | Install a skill from directory or URL |
| `skills uninstall <name>` | Remove a skill |
| `skills test <name>` | Run skill security scan |
| `env list` | List environment variables |
| `env set KEY=value` | Set an environment variable |
| `cron list` | List scheduled cron jobs |
| `cron add` | Create a scheduled task |
| `task list` | List running / pending tasks |
| `mission list` | List missions |
| `backup create` | Create a backup archive |
| `backup restore` | Restore from backup |
| `doctor` | Run diagnostics and connectivity checks |
| `doctor --fix` | Auto-fix common issues |
| `chats list` | List chat sessions |
| `update` | Update to the latest version |
| `uninstall` | Uninstall (use `--purge` to remove all data) |
| `daemon start` | Run as a background daemon |
| `daemon stop` | Stop the background daemon |

---

## Local Models

Run LLMs entirely on your machine — no API keys required.

| Backend | Platform | Setup |
|---|---|---|
| **llama.cpp** | macOS / Linux / Windows | Click "Download Llama.cpp" in the web UI — no separate install |
| **Ollama** | macOS / Linux / Windows | Install [Ollama](https://ollama.com), run `ollama serve`, then configure in Settings |
| **LM Studio** | macOS / Linux / Windows | Install [LM Studio](https://lmstudio.ai), start the local server, configure in Settings |

The local model manager ([`local_models/`](src/openspider/local_models/)) handles model downloads, GGUF tag parsing, and lifecycle management via `llamacpp.py` and `manager.py`.

---

## Deployment

### Docker Compose (recommended for production)

```bash
# OpenSpider variant
docker compose -f docker-compose.openspider.yml up -d
```

Config in [`deploy/`](deploy/):
- `Dockerfile.openspider` — production image
- `entrypoint.openspider.sh` — startup script
- `config/supervisord.openspider.conf.template` — supervisord config

### Environment file

Create a `.env` file in the project root:
```env
DASHSCOPE_API_KEY=sk-xxx
QWENPAW_AUTH_ENABLED=true
QWENPAW_CORS_ORIGINS=https://yourdomain.com
QWENPAW_LLM_MAX_CONCURRENT=20
```

### Reverse Proxy (nginx)

```nginx
location / {
    proxy_pass http://127.0.0.1:8088;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 300s;  # required for SSE streaming
}
```

### Alibaba Cloud ECS

One-click deployment: [QwenPaw on Alibaba Cloud ECS](https://computenest.console.aliyun.com/service/instance/create/cn-hangzhou?type=user&ServiceId=service-1ed84201799f40879884)

---

## Developer Guide

### Install from Source

```bash
git clone https://github.com/agentscope-ai/QwenPaw.git
cd QwenPaw

# Build console frontend
cd console && npm ci && npm run build
cd ..

# Copy frontend build
mkdir -p src/qwenpaw/console
cp -R console/dist/. src/qwenpaw/console/

# Install Python package (editable)
pip install -e ".[dev,full]"
```

### Running Tests

```bash
make test               # full test suite
make test-unit          # unit tests only (fast)
make quick              # unit tests, fail-fast (-x -q)
make test-contract      # channel/provider contract tests
make test-integration   # integration tests (requires running app)
make coverage-full      # HTML + terminal coverage report
```

`pytest` config in `pyproject.toml`: `asyncio_mode = "auto"` — all async tests run without decoration. Coverage threshold: 30% (`src/openspider`).

Test markers: `unit`, `contract`, `integration`, `slow`.

### Project Structure (source)

```
src/openspider/          # Active development target
src/qwenpaw/             # Legacy (kept in sync; do not modify unless asked)
tests/
├── unit/                # Fast unit tests
├── contract/            # Channel and provider contract tests
├── integration/         # End-to-end integration tests
└── fixtures/            # Shared test fixtures
console/                 # React frontend (TypeScript + Vite)
website/                 # Documentation site
deploy/                  # Docker and supervisord configs
scripts/                 # Build, install, and CI scripts
plugins/                 # Official plugin packages
```

### Adding a New Channel

1. Create `src/openspider/app/channels/<name>/channel.py`
2. Subclass `BaseChannel`, implement `start()`, `stop()`, and message routing
3. Register in the channel discovery list
4. Add contract tests in `tests/contract/channels/`

### Adding a New LLM Provider

1. Create `src/openspider/providers/<name>_provider.py`
2. Implement the `Provider` ABC (`provider.py`)
3. Register in `ProviderManager`
4. Add a `ProviderInfo` Pydantic model with capability flags

### Plugin System

Plugins are Python packages loaded at runtime via `plugins/loader.py`. A plugin can add tools, channels, or skills.

```python
# plugins/my_plugin/__init__.py
from openspider.plugins.api import register_tool

@register_tool
def my_custom_tool(input: str) -> str:
    """My custom tool description."""
    return f"processed: {input}"
```

Place the plugin directory under the working directory's `plugins/` folder or install it as a pip package with the `qwenpaw.plugins` entry point.

---

## Contributing

OpenSpider evolves through open collaboration. Areas actively seeking contributors:

- **New channels** — Matrix bridges, Slack, WhatsApp, LINE, etc.
- **New LLM providers** — Cohere, Mistral, Together AI, etc.
- **New skills** — Domain-specific automation, integrations
- **MCP servers** — Tool server implementations
- **Frontend improvements** — Console UI enhancements

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow, code style (Black), and PR checklist.

Join [GitHub Discussions](https://github.com/agentscope-ai/QwenPaw/discussions) to discuss ideas.

---

## Roadmap

| Area | Item | Status |
|---|---|---|
| **Branding** | Rename `PROJECT_NAME` and env prefix from `QWENPAW_*` to `OPENSPIDER_*` (with fallback) | In Progress |
| **Multi-agent** | Agent Swarm / Team coordination | Planned |
| **Interaction** | Faster SSE streaming, richer slash-command feedback | In Progress |
| **Processing** | Parallel subtask execution in `plan/`, higher `LLM_MAX_CONCURRENT` default | In Progress |
| **Small + Large Model Collaboration** | Intelligent switching between on-device and cloud models | In Progress |
| **Memory System** | Context-aware proactive delivery | In Progress |
| **Context Management** | Intelligent context compression, user-selectable compression | Planned |
| **Security** | Fine-grained rule-based controls; LLM-based security controls | In Progress |
| **Versioning & Migration** | One-click packaging; multi-version / cross-device migration | In Progress |
| **Self-operations** | Self-update; failure rollback | Planned |

---

## Built by

[AgentScope team](https://github.com/agentscope-ai) · [AgentScope](https://github.com/agentscope-ai/agentscope) · [AgentScope Runtime](https://github.com/agentscope-ai/agentscope-runtime) · [ReMe](https://github.com/agentscope-ai/ReMe)

---

## License

OpenSpider is released under the [Apache License 2.0](LICENSE).

---

## Contributors

<a href="https://github.com/agentscope-ai/QwenPaw/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=agentscope-ai/QwenPaw" alt="Contributors" />
</a>
