# OpenSpider — Architecture Documentation

> Auto-generated analysis of the `src/openspider/` codebase.  
> **Date**: 2026-06-25 | **Package**: `openspider` | **Active source**: `src/openspider/`

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Request Flow (End-to-End)](#2-request-flow-end-to-end)
3. [Agent System — Core Orchestration](#3-agent-system--core-orchestration)
4. [Tool System & Security Guard](#4-tool-system--security-guard)
5. [Skill System](#5-skill-system)
6. [Context & Memory Management](#6-context--memory-management)
7. [Provider Pattern & LLM Integration](#7-provider-pattern--llm-integration)
8. [Channel System](#8-channel-system)
9. [Workspace & Runner Lifecycle](#9-workspace--runner-lifecycle)
10. [Config System](#10-config-system)
11. [Plan Mode](#11-plan-mode)
12. [Mission Mode](#12-mission-mode)
13. [ACP Protocol](#13-acp-protocol)
14. [CLI Architecture](#14-cli-architecture)
15. [Security Layer](#15-security-layer)
16. [Frontend-Backend Connection](#16-frontend-backend-connection)
17. [Design Patterns Reference](#17-design-patterns-reference)
18. [Package Map](#18-package-map)

---

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                              │
│  CLI: python -m openspider app    │  HTTP: POST /api/console/chat │
│  ACP: stdio JSON-RPC              │  Channels: IM bots, MQTT     │
└──────────────┬───────────────────────┬───────────────────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                     APP LAYER (app/)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ FastAPI App   │  │ AuthMiddleware│  │ DynamicMultiAgentRunner│  │
│  │ (_app.py)     │  │ (Bearer token)│  │ (routes by X-Agent-Id) │  │
│  └──────┬───────┘  └──────────────┘  └───────────┬───────────┘  │
│         │                                         │              │
│  ┌──────▼───────────────────────────────────────▼────────────┐  │
│  │              MultiAgentManager                            │  │
│  │  Lazy-loads Workspace per agent_id on first request       │  │
│  └──────┬──────────────────────────────────────┬────────────┘  │
│         │                                      │                │
│  ┌──────▼──────────┐              ┌───────────▼──────────────┐ │
│  │   Workspace A   │              │   Workspace B            │ │
│  │  (agent_id=qa)  │              │  (agent_id=default)      │ │
│  │  ┌────────────┐ │              │  ┌────────────────────┐  │ │
│  │  │Runner      │ │              │  │Runner              │  │ │
│  │  │Memory      │ │              │  │Memory              │  │ │
│  │  │Context Mgr │ │              │  │Context Mgr         │  │ │
│  │  │MCP Clients │ │              │  │MCP Clients         │  │ │
│  │  │Channel Mgr │ │              │  │Channel Mgr         │  │ │
│  │  │Cron Mgr    │ │              │  │Cron Mgr            │  │ │
│  │  └────────────┘ │              │  └────────────────────┘  │ │
│  └─────────────────┘              └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AGENT LAYER (agents/)                         │
│  SpiderAgent                                                    │
│  ├── ToolGuardMixin ──► Security approval gate                  │
│  ├── ReActAgent ──► Reasoning ⟷ Acting loop (agentscope)       │
│  ├── Toolkit ──► 20 built-in tools + skills + MCP tools         │
│  ├── ContextManager ──► Memory compaction, pruning              │
│  ├── Memory ──► Conversation persistence (ReMe stack)           │
│  └── Hooks ──► Lifecycle callbacks (bootstrap, compaction)      │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                 INFRASTRUCTURE LAYER                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │Providers │  │ Security │  │ Config   │  │ Token Usage      │ │
│  │OpenAI    │  │Tool Guard│  │Pydantic  │  │Rate Limiter      │ │
│  │Anthropic │  │Skill Scan│  │models    │  │Retry Wrapper     │ │
│  │Gemini    │  │Secret St.│  │          │  │                  │ │
│  │Ollama    │  │          │  │          │  │                  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Request Flow (End-to-End)

### HTTP Chat Request

```
1. Client POST /api/console/chat { input, session_id, user_id, stream: true }
       │  Headers: Authorization: Bearer <token>, X-Agent-Id: <agent_id>
       ▼
2. AuthMiddleware ──► validates Bearer token
       ▼
3. AgentContextMiddleware ──► extracts agentId → sets contextvar
       ▼
4. DynamicMultiAgentRunner.stream_query(request)
       ▼
5. MultiAgentManager.get_agent(agent_id)
       │  ┌─ Lazy: creates Workspace if not cached
       │  └─ Lock released during slow startup for parallelism
       ▼
6. Workspace.runner.stream_query(request)
       ▼
7. AgentRunner ──► command dispatch
       │  ├─ /daemon approve/deny ──► ApprovalService
       │  ├─ /stop ──► cancel task
       │  ├─ /compact, /new, /clear ──► CommandHandler
       │  ├─ /plan ──► activate plan gate
       │  └─ (default) ──► create SpiderAgent
       ▼
8. SpiderAgent ──► ReAct Loop
       │  ┌─ _reasoning() ──► LLM call (via ToolGuardMixin)
       │  │   └─ ToolGuardMixin intercepts: guard check → approve/deny
       │  ├─ _acting() ──► tool execution
       │  └─ reply() ──► yield SSE events
       ▼
9. SSE stream ← response.body (yielded chunks)
       │  Each chunk: { type: "message", content: [...], metadata: {...} }
       ▼
10. Client renders AgentScopeRuntimeResponseCard
```

### WebSocket / SSE Details

- **Chat streaming**: Single `POST /api/console/chat` with `stream: true`. Server responds with `text/event-stream`.
- **Plan streaming**: Persistent `GET /api/plan/stream` with SSE. Auto-reconnects after 3s.
- **Approval polling**: `GET /api/console/push-messages` every 2.5s (polling, not push).
- **Cancellation**: `POST /api/console/chat/stop?chat_id=...` — cancels the asyncio task.

---

## 3. Agent System — Core Orchestration

### Class Hierarchy

```
agentscope.agent.ReActAgent                    (framework base)
    ▲
    │
ToolGuardMixin (agents/tool_guard_mixin.py)    (security interceptor)
    ▲
    │  MRO: SpiderAgent → ToolGuardMixin → ReActAgent
    │
SpiderAgent (agents/react_agent.py)           (main agent class)
    ├── Toolkit (20 built-in tools)
    ├── Skills (from workspace/skills/)
    ├── MCP tools (from MCPClientManager)
    ├── ContextManager (compaction, pruning)
    ├── Memory (ReMe-based persistence)
    ├── CommandHandler (/compact, /new, etc.)
    └── Hooks (lifecycle callbacks)
```

### Agent Construction

```python
# agents/react_agent.py — SpiderAgent.__init__()
def __init__(self, agent_config, workspace_dir, ...):
    # 1. Create toolkit with enabled tools from config
    self._create_toolkit(config)
    
    # 2. Register skills from workspace
    self._register_skills()
    
    # 3. Build system prompt from AGENTS.md / SOUL.md / PROFILE.md
    system_prompt = PromptBuilder.build(workspace_dir, language)
    
    # 4. Create model + formatter via factory
    model, formatter = create_model_and_formatter(agent_id)
    
    # 5. Initialize parent ReActAgent
    super().__init__(model, toolkit, memory, formatter, max_iters)
    
    # 6. Register memory tools if memory_manager present
    # 7. Swap memory to AgentContext if context_manager present
    # 8. Setup CommandHandler and lifecycle hooks
```

### Lazy Loading Pattern

```python
# agents/__init__.py — module-level lazy loading
def __getattr__(name: str):
    if name == "SpiderAgent":
        from .react_agent import SpiderAgent
        return SpiderAgent
    # Only imports heavy dependencies when actually accessed
```

This prevents importing `agentscope`, all tools, and the full react_agent module when CLI commands like `openspider init` or `openspider skills` only need the skill system.

---

## 4. Tool System & Security Guard

### Tool Registration

```python
# 20 built-in tools, each configurable via AgentProfileConfig.tools.builtin_tools
TOOLS = {
    "execute_shell_command": (shell.execute_shell_command, {"async_execution"}),
    "read_file": (file_io.read_file, set()),
    "write_file": (file_io.write_file, set()),
    "edit_file": (file_io.edit_file, set()),
    "grep_search": (file_search.grep_search, set()),
    "glob_search": (file_search.glob_search, set()),
    "browser_use": (browser_control.browser_use, set()),
    "desktop_screenshot": (desktop_screenshot.desktop_screenshot, set()),
    "view_image": (view_media.view_image, set()),
    "view_video": (view_media.view_video, set()),
    "send_file_to_user": (send_file.send_file_to_user, set()),
    "get_current_time": (get_current_time.get_current_time, set()),
    "set_user_timezone": (get_current_time.set_user_timezone, set()),
    "get_token_usage": (get_token_usage.get_token_usage, set()),
    "delegate_external_agent": (delegate.delegate_external_agent, {"async_execution"}),
    "list_agents": (agent_mgmt.list_agents, set()),
    "chat_with_agent": (agent_mgmt.chat_with_agent, set()),
    "submit_to_agent": (agent_mgmt.submit_to_agent, set()),
    "check_agent_task": (agent_mgmt.check_agent_task, set()),
}
```

### Namesake Strategy

When a skill or MCP tool name conflicts with a built-in tool name:

| Strategy | Behavior |
|----------|----------|
| `"skip"` | Don't register the conflicting tool (default) |
| `"override"` | Replace built-in with custom |
| `"raise"` | Throw error |
| `"rename"` | Auto-rename with prefix |

### Tool Guard Flow

```
Tool call from LLM
    │
    ▼
ToolGuardMixin._acting(tool_call)           [MRO override]
    │
    ▼
_decide_guard_action(tool_call)             [pure read, no lock]
    │
    ├── ToolExecutionLevel.OFF ──► bypass (return None)
    │
    ├── ToolExecutionLevel.AUTO ──► only check guarded tools
    │       └── GuardEngine.guard(tool_name, tool_input)
    │           ├── FilePathToolGuardian ──► sensitive paths?
    │           ├── RuleBasedToolGuardian ──► YAML rule match?
    │           └── ShellEvasionGuardian ──► obfuscation?
    │
    ├── ToolExecutionLevel.SMART ──► check all
    │       ├── INFO/LOW findings ──► auto-allow
    │       └── MEDIUM+ ──► needs approval
    │
    └── ToolExecutionLevel.STRICT ──► ALL tools need approval
    │
    ▼
_execute_guard_action(action)               [outside lock]
    │
    ├── None ──► proceed normally
    ├── "auto_denied" ──► block, return error message
    └── "needs_approval" ──► ApprovalService.create_pending()
            │
            ▼
        asyncio.Future ──► runner SUSPENDED
            │
            │  User clicks Approve/Deny in UI
            ▼
        ApprovalService.resolve_request(id, APPROVED/DENIED)
            │
            ▼
        Future.set_result() ──► runner RESUMES
```

### Concurrent Tool Execution

Tool calls with `parallel_tool_calls=True`:
- Guard evaluation and execution happen **outside** the `_tool_guard_lock`
- The lock only serializes mutations to shared approval state
- Each tool gets its own `_GuardAction` resolution

---

## 5. Skill System

### Architecture

```
┌─────────────────────────────────────┐
│          SKILL RESOLUTION           │
│                                     │
│  resolve_effective_skills(          │
│      agent_id, channel)             │
│         │                           │
│         ├──► Workspace skills       │
│         │    (<workspace>/skills/)  │
│         │                           │
│         ├──► Skill pool             │
│         │    (~/.openspider/        │
│         │     skill_pool/)          │
│         │                           │
│         └──► Env var overrides      │
│              OPENSPIDER_SKILL_      │
│              <NAME>_ENABLED=1       │
└─────────────────────────────────────┘
```

### Skill Structure

```
skills/<skill_name>-en/
├── SKILL.md          # Skill instructions (Markdown)
├── references/       # Reference documents
└── scripts/          # Python scripts (optional)
```

### Registration

```python
# Each skill directory is registered as an AgentScope "agent skill"
toolkit.register_agent_skill(str(skill_dir))
```

### Built-in Skills (18 bilingual pairs)

`browser_cdp`, `browser_visible`, `chat_with_agent`, `cron`, `docx`, `file_reader`, `make_plan`, `multi_agent_collaboration`, `pdf`, `pptx`, `xlsx`, `news`, `QA_source_index`, `dingtalk_channel`, `guidance`, `mu-plugins`, `channels`, `heartbeat`

---

## 6. Context & Memory Management

### Memory Stack

```
AgentContext (extends agentscope.memory.InMemoryMemory)
    │
    ├── BaseMemoryManager ──► ReMe-based persistence
    │   └── LightMemoryManager (concrete)
    │       ├── Remember/forget operations
    │       ├── Semantic search
    │       └── File watching (MEMORY.md changes)
    │
    └── BaseContextManager ──► Context window management
        └── LightContextManager (concrete)
            ├── Tool-result pruning (> DEFAULT_MAX_BYTES truncated)
            ├── Context compaction (LLM summarization of old messages)
            └── Lifecycle hooks (pre_reply, pre_reasoning, post_acting)
```

### Context Compaction Flow

```
1. pre_reasoning hook fires
       │
2. EstimatedTokenCounter.estimate(messages) > threshold?
       │  YES
       ▼
3. Compact older messages into rolling summary
       │  Uses separate "compactor" LLM (smaller model)
       │  Bilingual prompts (en/zh)
       ▼
4. Replace old messages with summary message
```

### Registry Pattern

```python
# Context managers are registered via decorator
@context_registry.register("light")
class LightContextManager(BaseContextManager):
    ...
```

---

## 7. Provider Pattern & LLM Integration

### Provider ABC

```python
class Provider(ABC):
    base_url: str
    api_key: str
    
    @abstractmethod
    async def list_models() -> list[ModelInfo]: ...
    
    @abstractmethod
    async def validate_api_key() -> bool: ...
    
    @abstractmethod
    def create_chat_model() -> ChatModelBase: ...
```

### Provider Implementations

| Provider | Chat Model Class | Notes |
|----------|-----------------|-------|
| `OpenAIProvider` | `OpenAIChatModel` | Also handles DashScope, TokenPlan; LangFuse tracing |
| `AnthropicProvider` | `AnthropicChatModel` | Claude models |
| `GeminiProvider` | `GeminiChatModel` | Google AI |
| `OllamaProvider` | `OllamaChatModel` | Local Ollama |
| `LMStudioProvider` | `LMStudioChatModel` | Local LM Studio |
| `OpenRouterProvider` | `OpenRouterChatModel` | Multi-provider aggregator |

### Model Creation Chain

```
create_model_and_formatter(agent_id)
    │
    ▼
AgentProfileConfig.active_model ──► (provider_id, model_id)
    │
    ▼
ProviderManager.get_chat_model(provider_id, model_id)
    │
    ▼
Provider.create_chat_model() ──► ChatModelBase
    │
    ▼
RetryChatModel(ChatModelBase)          [exponential backoff + rate limiting]
    │
    ▼
TokenRecordingModelWrapper(ChatModel)  [usage tracking]
    │
    ▼
Return (model, formatter) tuple
```

### Rate Limiting

```
LLMRateLimiter (singleton)
    ├── asyncio.Semaphore ──► max concurrent LLM calls
    ├── QPM sliding window ──► 60s window, proactive wait
    └── Global pause on 429 ──► per-caller jitter
```

---

## 8. Channel System

### Channel Pattern

```python
class BaseChannel(ABC):
    channel: ChannelType                    # class attr, e.g. "discord"
    
    @classmethod
    def from_config(cls, config) -> Self:   # factory
        ...
    
    async def start() -> None:              # lifecycle
        ...
    
    async def stop() -> None:               # lifecycle
        ...
    
    @abstractmethod
    async def consume_one(payload) -> None: # process message
        ...
```

### 17 Built-in Channels

`console`, `discord`, `dingtalk`, `feishu`, `qq`, `telegram`, `mattermost`, `mqtt`, `matrix`, `voice`, `sip`, `wecom`, `xiaoyi`, `wechat`, `onebot`, `imessage` + custom channels from `CUSTOM_CHANNELS_DIR`.

### Channel Manager

```
ChannelManager
    ├── UnifiedQueueManager ──► per-channel asyncio.Queue
    ├── Consumer loops ──► asyncio.Tasks
    ├── from_config() ──► reads config.json → channels
    └── _process_batch() ──► merge multi-message → consume_one()
```

### Channel Registration

```
ChannelRegistry (lazy singleton)
    ├── Built-in channels (discovered from app/channels/)
    └── Custom channels (from CUSTOM_CHANNELS_DIR)
```

---

## 9. Workspace & Runner Lifecycle

### Workspace = Isolated Agent Runtime

```python
class Workspace:
    agent_id: str
    workspace_dir: Path
    
    # Services (initialized in priority order)
    runner: AgentRunner              # Priority 10 (create), 25 (start)
    memory_manager: BaseMemoryManager # Priority 20 (concurrent)
    context_manager: BaseContextManager # Priority 20 (concurrent)
    mcp_manager: MCPClientManager    # Priority 20 (concurrent)
    chat_manager: ChatManager        # Priority 20 (concurrent)
    channel_manager: ChannelManager  # Priority 30
    cron_manager: CronManager        # Priority 40
```

### ServiceManager — Priority-Ordered Init

```
ServiceManager.start_all():
    Priority 10: init runner
    Priority 20: init memory, context, mcp, chat (CONCURRENT)
    Priority 25: start runner
    Priority 30: init channel manager
    Priority 40: init cron manager
    Priority 50-51: start config watchers
```

### MultiAgentManager — Lazy Loading

```python
class MultiAgentManager:
    _agents: dict[str, Workspace]
    _lock: asyncio.Lock
    
    async def get_agent(agent_id: str) -> Workspace:
        if agent_id not in self._agents:
            # Create workspace (lock released during slow startup)
            workspace = Workspace(agent_id, workspace_dir)
            await workspace.start()
            self._agents[agent_id] = workspace
        return self._agents[agent_id]
```

### AgentRunner — Request Processing

```python
class AgentRunner(Runner):
    async def stream_query(request: AgentRequest):
        # 1. Command dispatch
        if is_daemon_command:    → daemon_commands
        if is_control_command:   → control_commands
        if is_conversation_cmd:  → CommandHandler
        if is_mission_command:   → mission_dispatch
        if is_plan_command:      → activate plan gate
        
        # 2. Create SpiderAgent
        agent = SpiderAgent(config, workspace_dir, ...)
        
        # 3. ReAct loop → SSE streaming
        async for msg, is_last in agent(messages):
            yield format_sse(msg)
```

---

## 10. Config System

### Pydantic Model Hierarchy

```
Config (root, from config.json)
    ├── channels: ChannelConfig[]
    ├── security: SecurityConfig
    │   ├── tool_guard: ToolGuardConfig
    │   └── file_guard: FileGuardConfig
    ├── acp: ACPConfig
    ├── active_llm: ModelSlotConfig
    ├── user_timezone: str
    └── language: str

AgentProfileConfig (per-agent, from <workspace>/agent.json)
    ├── id, name, description, language
    ├── running: AgentsRunningConfig
    │   ├── max_iters: int
    │   ├── max_input_length: int
    │   ├── memory_compact_threshold: int
    │   ├── heartbeat: HeartbeatConfig
    │   └── parallel_tool_calls: bool
    ├── tools: ToolsConfig
    │   └── builtin_tools: dict[str, ToolConfig]
    │       └── enabled: bool, async_execution: bool
    ├── active_model: ModelSlotConfig
    │   ├── provider_id: str
    │   └── model: str
    ├── approval_level: ToolExecutionLevel
    ├── mcp: MCPConfig
    └── channels: per-agent channel configs
```

### Config Loading

```python
# Thread-safe, cached, mtime-invalidated
config = load_config()                    # from config.json
agent_config = load_agent_config(agent_id) # from <workspace>/agent.json
```

### Env Var System

```python
# constant.py — _get_env() with fallback chain
_get_env("OPENSPIDER_WORKING_DIR")
    # 1. OPENSPIDER_WORKING_DIR (canonical)
    # 2. QWENPAW_WORKING_DIR (legacy fallback)
    # 3. COPAW_WORKING_DIR (legacy fallback)
```

`EnvVarLoader` provides type-safe access: `get_bool()`, `get_float()`, `get_int()`, `get_str()`.

---

## 11. Plan Mode

### Purpose

Structured task decomposition with gated tool access. Agent must plan before acting.

### State Machine

```
todo ──► in_progress ──► done
  │                        │
  └──────► abandoned ◄─────┘
```

### Tool Gate

```
Agent enters plan mode (/plan <desc>)
    │
    ▼
Plan tool gate ACTIVE
    │  Only create_plan tool available
    ▼
Agent creates plan (SubTask list)
    │
    ▼
User approves plan
    │
    ▼
Plan tool gate RELEASED
    │  All tools available
    ▼
Agent executes subtasks, updating state
```

### Plan SSE Streaming

```python
# Frontend subscribes to plan updates
GET /api/plan/stream
    → SSE: { type: "plan_update", plan: {...}, session_id: "..." }
```

---

## 12. Mission Mode

### Two-Phase Code-Controlled Loop

```
Phase 1 — PRD
    ├── Agent explores codebase
    ├── Writes prd.json with user stories
    └── Full tool access

Phase 2 — Execution
    ├── Implementation tools DEACTIVATED (via Toolkit groups)
    ├── Engine reads prd.json
    ├── Checks passes on each story
    ├── Injects continuation messages
    └── Loops until all pass or max iterations
```

### Toolkit Group Mechanism

```python
# Implementation tools moved to "mission_impl" group
toolkit.create_tool_group("mission_impl", ...)
for tool in ["edit_file", "browser_use", "desktop_screenshot"]:
    toolkit.tools[tool].group = "mission_impl"

# Deactivated for Phase 2
toolkit.update_tool_groups(["mission_impl"], active=False)
```

---

## 13. ACP Protocol

### ACP = Agent Communication Protocol (Zed Industries)

```
External ACP Client (Zed, OpenCode, etc.)
    │  stdio JSON-RPC
    ▼
OpenSpiderACPAgent (agents/acp/server.py)
    │  Boots full Workspace lifecycle
    │
    ├── initialize() ──► capabilities exchange
    ├── new_session() ──► create session
    ├── prompt() ──► forward to Workspace.runner
    │   └── SSE-like streaming via session_update()
    ├── cancel() ──► cancel running task
    └── set_session_model() ──► switch model per session
```

### ACP Hosted Clients (External Agents as Tools)

```python
# External ACP agents exposed as tools
ACPConfig:
    agents:
      - id: "opencode"
        command: ["opencode"]
      - id: "claude_code"
        command: ["claude"]
```

---

## 14. CLI Architecture

### Entry Point

```python
# pyproject.toml
[project.scripts]
openspider = "openspider.cli.main:cli"

# src/openspider/__main__.py
from .cli.main import cli
cli()
```

### Lazy Subcommand Loading

```python
# cli/main.py — LazyGroup for fast startup
@click.group(cls=LazyGroup, lazy_subcommands={
    "app":      ("openspider.cli.app_cmd", "app_cmd", ".app_cmd"),
    "init":     ("openspider.cli.init_cmd", "init_cmd", ".init_cmd"),
    "doctor":   ("openspider.cli.doctor_cmd", "doctor_cmd", ".doctor_cmd"),
    "agents":   ("openspider.cli.agents_cmd", "agents_group", ".agents_cmd"),
    "channels": ("openspider.cli.channels_cmd", "channels_group", ".channels_cmd"),
    "models":   ("openspider.cli.providers_cmd", "models_group", ".providers_cmd"),
    # ... 15+ more commands
})
```

### Command List

| Command | Purpose |
|---------|---------|
| `app` | Start FastAPI server |
| `init` | Initialize workspace |
| `doctor` | System diagnostics |
| `daemon` | Approval management (`approve`/`deny`/`status`) |
| `channels` | Channel management |
| `chats` | Chat history |
| `agents` | Multi-agent management |
| `models` | Provider/model management |
| `skills` | Skill management |
| `cron` | Cron job management |
| `env` | Env var management |
| `update` | Self-update |
| `shutdown` | Graceful shutdown |
| `desktop` | Desktop app launcher |
| `acp` | ACP server |
| `plugin` | Plugin management |
| `task` | Background task management |

---

## 15. Security Layer

### Tool Guard

```
ToolGuardEngine (lazy singleton)
    ├── FilePathToolGuardian
    │   └── Detects access to sensitive paths
    ├── RuleBasedToolGuardian
    │   └── YAML rules in security/tool_guard/rules/
    └── ShellEvasionGuardian
        └── Detects obfuscation, encoding tricks
```

### Severity Levels

`CRITICAL` > `HIGH` > `MEDIUM` > `LOW` > `INFO` > `SAFE`

### Threat Categories

`command_injection`, `data_exfiltration`, `path_traversal`, `sensitive_file_access`, `network_abuse`, `credential_exposure`, `resource_abuse`, `prompt_injection`, `code_execution`, `privilege_escalation`

### Execution Levels

| Level | Behavior |
|-------|----------|
| `OFF` | No guard checks |
| `AUTO` | Only guarded tools checked (backward compat) |
| `SMART` | INFO/LOW auto-allowed, MEDIUM+ needs approval |
| `STRICT` | ALL tools require approval |

### Secret Store

```python
# Fernet encryption (AES-128-CBC + HMAC-SHA256)
# Master key from OS keychain (keyring) or fallback file
encrypt_dict_fields(config_dict, fields=["api_key", ...])
decrypt_dict_fields(config_dict, fields=["api_key", ...])
```

### Skill Scanner

Static analysis of skill directories before install:
- `scanner.py` — entry point
- `analyzers/` — analysis modules
- `rules/` — detection rules
- `scan_policy.py` — policy configuration

---

## 16. Frontend-Backend Connection

### Technology Stack

```
Frontend: React 18 + TypeScript + Vite
    ├── @agentscope-ai/chat ──► Chat UI library (SSE streaming)
    ├── Zustand ──► State management (AgentStore)
    ├── Ant Design ──► UI components
    └── React Router ──► Client-side routing

Backend: FastAPI + Python 3.10+
    └── Serves console static files from console/ build output
```

### API Connection

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Browser)                                     │
│                                                         │
│  api/request.ts                                         │
│    ├── base URL: VITE_API_BASE_URL + /api               │
│    ├── auth: Bearer token (localStorage)                │
│    └── agent: X-Agent-Id header (sessionStorage)        │
│                                                         │
│  api/modules/                                           │
│    ├── chat.ts ──► POST /console/chat (SSE stream)     │
│    ├── agents.ts ──► GET/POST /agents                   │
│    ├── commands.ts ──► POST /approval/approve|deny      │
│    ├── console.ts ──► GET /console/push-messages        │
│    ├── plan.ts ──► GET /plan/stream (SSE)               │
│    └── provider.ts ──► GET /providers, /models/active   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                      │
│                                                         │
│  AuthMiddleware ──► validates Bearer token              │
│  AgentContextMiddleware ──► extracts X-Agent-Id         │
│                                                         │
│  /api/console/chat ──► SSE stream of agent responses    │
│  /api/console/push-messages ──► approvals + push msgs   │
│  /api/approval/approve ──► resolve pending approval     │
│  /api/approval/deny ──► deny pending approval           │
│  /api/plan/stream ──► plan state SSE updates            │
│  /api/agents ──► CRUD for multi-agent management        │
└─────────────────────────────────────────────────────────┘
```

### Agent Switching Flow

```
1. User selects agent in AgentSelector dropdown
       │
2. AgentStore.setSelectedAgent(newAgentId)
       ├── sessionStorage("openspider-agent-storage") = newAgentId
       └── localStorage("openspider-last-used-agent") = newAgentId
       │
3. ChatPage detects selectedAgent change
       ├── Save last chat ID for outgoing agent
       ├── Restore last chat ID for incoming agent
       └── Re-mount AgentScopeRuntimeWebUI with new key
       │
4. All subsequent API calls include:
       X-Agent-Id: <newAgentId>
```

### Approval Flow (Frontend)

```
1. ConsolePollService polls GET /api/console/push-messages (every 2.5s)
       │
2. Response: { pending_approvals: [...] }
       │
3. ApprovalContext.setApprovals(pending)
       │
4. ApprovalCard[] rendered (filtered by root_session_id)
       │  Shows: tool name, severity, findings, timeout countdown
       │
5. User clicks Approve/Deny
       │
6. POST /api/approval/approve or /deny
       │  { request_id, session_id, reason }
       │
7. Backend: ApprovalService.resolve_request() → Future.set_result()
       │
8. Card removed from UI with exit animation
```

---

## 17. Design Patterns Reference

| Pattern | Where Used |
|---------|-----------|
| **Strategy** | `NamesakeStrategy` (override/skip/raise/rename), `ToolExecutionLevel` (STRICT/SMART/AUTO/OFF) |
| **Factory** | `create_model_and_formatter()`, `Provider.create_chat_model()`, `ServiceDescriptor` |
| **Observer** | Hooks system (pre_reasoning, post_acting, etc.), config watchers, plan broadcast |
| **Mixin (MRO)** | `ToolGuardMixin`, `ConversationCommandHandlerMixin`, `DaemonCommandHandlerMixin` |
| **Singleton** | `ApprovalService`, `ToolGuardEngine`, `LLMRateLimiter`, `ProviderManager`, `ChannelRegistry` |
| **Registry** | Channel registry, context manager registry, skill pool registry |
| **State Machine** | Plan state (todo→in_progress→done|abandoned), Pydantic-validated |
| **Decorator/Wrapper** | `RetryChatModel`, `TokenRecordingModelWrapper` |
| **Lazy Initialization** | Module `__getattr__`, `LazyGroup` CLI, workspace lazy loading, tool guard lazy init |
| **Template Method** | `BaseChannel.consume_one()`, `BaseContextManager` hooks |
| **Chain of Responsibility** | Middleware stack (Auth → AgentContext → CORS), Guard chain (FilePath → Rule → ShellEvasion) |

### Async Patterns

| Pattern | Usage |
|---------|-------|
| `asyncio.Lock` | Tool guard, approval service, MCP client manager, multi-agent manager, channel manager, config cache, rate limiter |
| `asyncio.Semaphore` | `LLMRateLimiter` — caps concurrent LLM calls |
| `asyncio.Future` | `PendingApproval.future` — suspends runner until user approves |
| `asyncio.Queue` | Streaming message pipeline, channel message queues |
| `asyncio.Event` | ACP permission requests, workspace pending starts |
| `asyncio.Task` | Background task tracking, channel consumer loops, cron execution |
| Cancellable generators | SSE streaming with client disconnect detection |

---

## 18. Package Map

```
src/openspider/
├── __init__.py              # Package init, log level setup, env bootstrap
├── __main__.py              # python -m openspider entry
├── __version__.py           # Version string
├── constant.py              # Central constants, _get_env(), EnvVarLoader
├── exceptions.py            # Domain exceptions (ProviderError, etc.)
│
├── agents/                  # Agent system (core)
│   ├── react_agent.py       # SpiderAgent class (main agent)
│   ├── tool_guard_mixin.py  # Security interceptor (Mixin)
│   ├── model_factory.py     # Model + formatter factory
│   ├── command_handler.py   # /compact, /new, /clear commands
│   ├── prompt/              # System prompt builder
│   ├── tools/               # 20 built-in tools
│   ├── skills/              # 18 built-in skill definitions (bilingual)
│   ├── skill_system/        # Skill resolution + management
│   ├── context/             # Context managers (compaction, pruning)
│   ├── memory/              # Memory managers (ReMe-based)
│   ├── hooks/               # Lifecycle hooks (BootstrapHook)
│   ├── acp/                 # ACP protocol (server + hosted clients)
│   ├── mission/             # Mission mode (two-phase execution)
│   ├── md_files/            # Agent profile templates (QA Agent)
│   └── utils/               # Token counter, registry, normalizers
│
├── app/                     # Application layer
│   ├── _app.py              # FastAPI app creation, lifespan, middleware
│   ├── runner/              # AgentRunner + DynamicMultiAgentRunner
│   ├── workspace/           # Workspace lifecycle + ServiceManager
│   ├── channels/            # 17 channel implementations + BaseChannel
│   ├── approvals/           # ApprovalService (pending → future → resolve)
│   ├── routers/             # FastAPI routers
│   ├── mcp/                 # MCP client manager
│   ├── migration/           # Workspace migration utilities
│   └── utils/               # App utilities
│
├── providers/               # LLM provider abstraction
│   ├── provider.py          # Provider ABC, ModelInfo, ProviderInfo
│   ├── provider_manager.py  # Singleton registry of providers + models
│   ├── openai_provider.py   # OpenAI + DashScope + TokenPlan
│   ├── anthropic_provider.py
│   ├── gemini_provider.py
│   ├── ollama_provider.py
│   ├── lmstudio_provider.py
│   ├── openrouter_provider.py
│   ├── rate_limiter.py      # LLMRateLimiter (semaphore + QPM + 429 pause)
│   ├── retry_chat_model.py  # RetryChatModel wrapper
│   └── model_capability_cache.py
│
├── config/                  # Configuration
│   ├── config.py            # Pydantic models (Config, AgentProfileConfig)
│   └── utils.py             # Load/save, validation, workspace discovery
│
├── cli/                     # CLI (Click-based)
│   ├── main.py              # LazyGroup entry point + 20 subcommands
│   ├── app_cmd.py           # openspider app
│   ├── init_cmd.py          # openspider init
│   ├── doctor_cmd.py        # openspider doctor
│   ├── agents_cmd.py        # openspider agents
│   └── ... (15 more command files)
│
├── security/                # Security layer
│   ├── tool_guard/          # Tool call guard engine + YAML rules
│   ├── skill_scanner/       # Static analysis of skills
│   └── secret_store.py      # Fernet-encrypted secret storage
│
├── plan/                    # Plan mode
│   ├── schemas.py           # Plan/SubTask Pydantic models + state machine
│   ├── hints.py             # Plan-to-hint generator + tool gate
│   └── broadcast.py         # Plan state broadcast to UI
│
├── backup/                  # Atomic backup/restore
├── token_usage/             # Token tracking + persistence
├── tokenizer/               # Token counting
├── local_models/            # Local model management (llama.cpp, Ollama)
├── plugins/                 # Plugin system
├── tunnel/                  # ngrok/frp tunneling
├── envs/                    # Persistent env var store
├── agent_stats/             # Agent performance metrics
└── utils/                   # Logging, audit, file utils, telemetry
```

---

> **Note**: `src/qwenpaw/` is the legacy frozen baseline — structurally identical but intentionally not modified. All active development targets `src/openspider/`.
