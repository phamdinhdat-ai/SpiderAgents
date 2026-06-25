# 02 — Agent System

> Core agent orchestration: QwenPawAgent class, ReAct loop, tool system, security guard, model factory.

---

## Agent Lifecycle (Full Flow)

```mermaid
flowchart TD
    A["🚀 App Start"] --> B["MultiAgentManager.get_agent(agent_id)"]
    B --> C{"Workspace<br/>cached?"}
    C -->|No| D["Create Workspace(agent_id)"]
    D --> E["ServiceManager.start_all()"]
    E --> F["Runner created (P10)"]
    E --> G["Memory/Context/MCP (P20)"]
    F --> H["Runner started (P25)"]
    G --> H
    H --> I["Channel Manager (P30)"]
    I --> J["✅ Workspace Ready"]
    C -->|Yes| J
    J --> K["📨 Incoming Request"]
    K --> L["AgentRunner.stream_query()"]
    L --> M{"Command<br/>dispatch?"}
    M -->|daemon| N["/daemon approve/deny"]
    M -->|control| O["/stop"]
    M -->|conversation| P["/compact, /new, /clear"]
    M -->|plan| Q["/plan → Plan Gate"]
    M -->|mission| R["Mission Phase Dispatch"]
    M -->|default| S["Create QwenPawAgent"]
    S --> T["🧠 ReAct Loop"]
    T --> U["🎯 Reply → SSE Stream"]
    N --> V["ApprovalService"]
    P --> T
    Q --> T
    R --> T
    V --> T

    style A fill:#4CAF50,color:#fff
    style J fill:#2196F3,color:#fff
    style T fill:#FF9800,color:#fff
    style U fill:#9C27B0,color:#fff
```

---

## Class Hierarchy (MRO)

```mermaid
classDiagram
    class ReActAgent {
        +reasoning()
        +acting()
        +reply()
        +memory
        +toolkit
        +max_iters
    }
    class ToolGuardMixin {
        -_tool_guard_engine
        -_tool_guard_lock
        -_tool_guard_pending_info
        +_acting(tool_call)
        +_reasoning(msgs)
        +_decide_guard_action()
        +_execute_guard_action()
        +_init_tool_guard()
    }
    class QwenPawAgent {
        -agent_config
        -workspace_dir
        -command_handler
        -context_manager
        +__init__(config, dir)
        +_create_toolkit()
        +_register_skills()
        +_register_mcp_tools()
        +_build_system_prompt()
    }
    class Toolkit {
        +tools: dict
        +groups: dict
        +register_tool()
        +register_agent_skill()
        +create_tool_group()
    }
    class ContextManager {
        +pre_reply()
        +pre_reasoning()
        +post_acting()
        +compact_context()
    }
    class Memory {
        +add()
        +get_memory()
        +clear()
    }
    class CommandHandler {
        +handle_compact()
        +handle_new()
        +handle_clear()
    }
    class Hooks {
        +BootstrapHook
        +ContextHooks
    }

    ReActAgent <|-- ToolGuardMixin : extends
    ToolGuardMixin <|-- QwenPawAgent : extends (MRO)
    QwenPawAgent *-- Toolkit : owns
    QwenPawAgent *-- ContextManager : owns
    QwenPawAgent *-- Memory : owns
    QwenPawAgent *-- CommandHandler : owns
    QwenPawAgent *-- Hooks : registers
```

### MRO Design

`ToolGuardMixin` overrides `_acting()` and `_reasoning()` via Python's MRO. Any override in `QwenPawAgent` itself **must** call `super()._acting()` / `super()._reasoning()` to keep the guard interception active.

---

## ReAct Loop (Detailed)

```mermaid
flowchart TD
    START(["📨 User Message"]) --> PREP["Build messages + system prompt"]
    PREP --> HOOK_PRE["🪝 pre_reasoning hooks"]
    HOOK_PRE --> COMPACT{"Context<br/>compaction<br/>needed?"}
    COMPACT -->|Yes| DO_COMPACT["Compact old messages<br/>into rolling summary"]
    COMPACT -->|No| REASON
    DO_COMPACT --> REASON["🧠 _reasoning()"]
    
    REASON --> GUARD_INT["🛡️ ToolGuardMixin._reasoning()"]
    GUARD_INT --> LLM["🤖 LLM Call<br/>(RetryChatModel)"]
    LLM --> PARSE["Parse LLM response"]
    PARSE --> HAS_TOOL{"Has tool<br/>calls?"}
    
    HAS_TOOL -->|No| REPLY["💬 reply() → yield to user"]
    HAS_TOOL -->|Yes| LOOP_TOOLS["For each tool_call"]
    
    LOOP_TOOLS --> GUARD_ACT["🛡️ ToolGuardMixin._acting()"]
    GUARD_ACT --> GUARD_DECIDE{"Guard<br/>Decision"}
    GUARD_DECIDE -->|"PASS"| EXEC["⚙️ Execute Tool"]
    GUARD_DECIDE -->|"DENY"| DENY_MSG["❌ Return error message"]
    GUARD_DECIDE -->|"APPROVAL"| SUSPEND["⏸️ Suspend → await Future"]
    SUSPEND --> USER_ACTION{"User<br/>Action?"}
    USER_ACTION -->|Approve| EXEC
    USER_ACTION -->|Deny| DENY_MSG
    USER_ACTION -->|Timeout| DENY_MSG
    
    EXEC --> HOOK_POST["🪝 post_acting hooks<br/>(prune large outputs)"]
    HOOK_POST --> ADD_MEMORY["📝 Add to memory"]
    DENY_MSG --> ADD_MEMORY
    ADD_MEMORY --> CHECK_ITERS{"max_iters<br/>reached?"}
    CHECK_ITERS -->|No| HOOK_PRE
    CHECK_ITERS -->|Yes| REPLY

    style START fill:#4CAF50,color:#fff
    style REASON fill:#FF9800,color:#fff
    style EXEC fill:#2196F3,color:#fff
    style REPLY fill:#9C27B0,color:#fff
    style SUSPEND fill:#f44336,color:#fff
```

---

## Tool Guard Flow (Security Interception)

```mermaid
sequenceDiagram
    participant LLM as 🤖 LLM
    participant MIXIN as 🛡️ ToolGuardMixin
    participant ENGINE as 🔍 GuardEngine
    participant GUARDIAN as 📋 Guardians
    participant AS as ⏸️ ApprovalService
    participant USER as 👤 User
    participant TOOL as ⚙️ Tool

    LLM->>MIXIN: tool_call { name, input }
    MIXIN->>MIXIN: _acting(tool_call) [MRO override]
    MIXIN->>MIXIN: _decide_guard_action()
    
    alt Execution Level = OFF
        MIXIN->>TOOL: Execute directly (no check)
    else AUTO / SMART / STRICT
        MIXIN->>ENGINE: guard(tool_name, tool_input)
        ENGINE->>GUARDIAN: FilePathToolGuardian.guard()
        GUARDIAN-->>ENGINE: findings[]
        ENGINE->>GUARDIAN: RuleBasedToolGuardian.guard()
        GUARDIAN-->>ENGINE: findings[]
        ENGINE->>GUARDIAN: ShellEvasionGuardian.guard()
        GUARDIAN-->>ENGINE: findings[]
        ENGINE-->>MIXIN: ToolGuardResult { findings, max_severity }
        
        alt No findings / SAFE
            MIXIN->>TOOL: Execute
        else CRITICAL → auto-deny
            MIXIN-->>LLM: Error: tool blocked
        else SMART: INFO/LOW → auto-allow
            MIXIN->>TOOL: Execute
        else MEDIUM+ → needs approval
            MIXIN->>AS: create_pending(session_id, tool_name, result)
            AS->>AS: Create asyncio.Future
            AS-->>USER: ApprovalCard rendered in UI
            MIXIN->>MIXIN: await future (SUSPENDED)
            USER->>AS: POST /approval/approve or /deny
            AS->>AS: future.set_result(decision)
            MIXIN->>MIXIN: Resume
            alt Approved
                MIXIN->>TOOL: Execute
            else Denied / Timeout
                MIXIN-->>LLM: Error: tool rejected
            end
        end
    end
    TOOL-->>MIXIN: tool_result
    MIXIN-->>LLM: tool_result
```

---

## Agent Construction

```python
# agents/react_agent.py — QwenPawAgent.__init__()
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

---

## Lazy Loading Pattern

```python
# agents/__init__.py — module-level lazy loading via __getattr__
def __getattr__(name: str):
    if name == "QwenPawAgent":
        from .react_agent import QwenPawAgent
        return QwenPawAgent
    if name == "create_model_and_formatter":
        from .model_factory import create_model_and_formatter
        return create_model_and_formatter
```

**Purpose**: Prevents importing `agentscope`, all tools, and the full `react_agent` module when CLI commands like `openspider init` or `openspider skills` only need the skill system.

---

## Model Factory

`create_model_and_formatter(agent_id)`:

```
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

Also handles:
- File:// URL normalization for multimodal inputs
- Provider-specific formatter selection
- `_openspider_force_strip_media` flag for models that don't support multimodal

---

## Tool System

### 20 Built-in Tools

| Tool | File | Supports Async |
|------|------|---------------|
| `execute_shell_command` | `shell.py` | ✅ |
| `read_file` | `file_io.py` | — |
| `write_file` | `file_io.py` | — |
| `edit_file` | `file_io.py` | — |
| `append_file` | `file_io.py` | — |
| `grep_search` | `file_search.py` | — |
| `glob_search` | `file_search.py` | — |
| `browser_use` | `browser_control.py` | — |
| `desktop_screenshot` | `desktop_screenshot.py` | — |
| `view_image` | `view_media.py` | — |
| `view_video` | `view_media.py` | — |
| `send_file_to_user` | `send_file.py` | — |
| `get_current_time` | `get_current_time.py` | — |
| `set_user_timezone` | `get_current_time.py` | — |
| `get_token_usage` | `get_token_usage.py` | — |
| `delegate_external_agent` | `delegate_external_agent.py` | ✅ |
| `list_agents` | `agent_management.py` | — |
| `chat_with_agent` | `agent_management.py` | — |
| `submit_to_agent` | `agent_management.py` | — |
| `check_agent_task` | `agent_management.py` | — |

**Async execution**: Tools with `async_execution=True` get companion tools auto-registered: `view_task`, `wait_task`, `cancel_task`.

### Registration

Each tool is configurable via `AgentProfileConfig.tools.builtin_tools` — each has an `enabled: bool` flag. Plugin-discovered tools are security-gated (must be explicitly configured).

### Namesake Strategy

When a skill or MCP tool name conflicts with a built-in:

| Strategy | Behavior |
|----------|----------|
| `"skip"` | Don't register the conflicting tool (default) |
| `"override"` | Replace built-in with custom |
| `"raise"` | Throw error |
| `"rename"` | Auto-rename with prefix |

---

## Security Guard (ToolGuardMixin)

### Flow

```
Tool call from LLM
    │
    ▼
ToolGuardMixin._acting(tool_call)           [MRO override]
    │
    ▼
_decide_guard_action(tool_call)             [pure read, no lock]
    │
    ├── OFF ──► bypass
    ├── AUTO ──► only check guarded tools
    ├── SMART ──► INFO/LOW auto-allow, MEDIUM+ needs approval
    └── STRICT ──► ALL tools need approval
    │
    ▼
_execute_guard_action(action)               [outside lock]
    │
    ├── None ──► proceed normally
    ├── "auto_denied" ──► block, return error
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

### Execution Levels

| Level | Behavior |
|-------|----------|
| `OFF` | No guard checks |
| `AUTO` | Only guarded tools checked (backward compatible) |
| `SMART` | INFO/LOW auto-allowed, MEDIUM+ needs approval |
| `STRICT` | ALL tools require approval |

### Concurrent Tool Execution

With `parallel_tool_calls=True`:
- Guard evaluation and execution happen **outside** the `_tool_guard_lock`
- The lock only serializes mutations to shared approval state
- Each tool gets its own `_GuardAction` resolution

### Three Guardians

| Guardian | Checks |
|----------|--------|
| `FilePathToolGuardian` | Sensitive file paths |
| `RuleBasedToolGuardian` | YAML rules (dangerous commands) |
| `ShellEvasionGuardian` | Obfuscation, encoding tricks |

---

## Hooks

### BootstrapHook

On first user interaction:
1. Checks for `BOOTSTRAP.md` in workspace
2. Prepends identity-establishing guidance
3. Sets `.bootstrap_completed` flag

Registered as `pre_reasoning` instance hook.

### Context Manager Hooks

Registered when `context_manager` is present:

| Hook | Trigger |
|------|---------|
| `pre_reply` | Before agent emits final reply |
| `pre_reasoning` | Before reasoning step (compaction check) |
| `post_acting` | After tool execution (prune large outputs) |
| `post_reply` | After reply (cleanup) |

---

## Command Handler

Built-in slash commands processed by `CommandHandler`:

| Command | Action |
|---------|--------|
| `/compact` | Force context compaction |
| `/new` | Start fresh conversation |
| `/clear` | Clear conversation history |
| `/dump_history` | Export conversation to file |
| `/load_history` | Import conversation from file |
| `/stop` | Stop current agent execution |
