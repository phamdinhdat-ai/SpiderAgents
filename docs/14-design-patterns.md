# 14 — Design Patterns Reference

> All design patterns used across the OpenSpider codebase, organized by category.

---

## Pattern Distribution Map

```mermaid
graph TB
    subgraph Creational["🏗️ Creational"]
        FACTORY["Factory<br/>create_model_and_formatter()<br/>Provider.create_chat_model()<br/>BaseChannel.from_config()"]
        SINGLETON["Singleton<br/>ApprovalService<br/>LLMRateLimiter<br/>ProviderManager<br/>ToolGuardEngine"]
        LAZY["Lazy Initialization<br/>Module __getattr__<br/>LazyGroup CLI<br/>Workspace lazy load"]
    end
    
    subgraph Structural["🏛️ Structural"]
        MIXIN["Mixin (MRO)<br/>ToolGuardMixin<br/>DaemonCommandHandlerMixin"]
        DECORATOR["Decorator/Wrapper<br/>RetryChatModel<br/>TokenRecordingModelWrapper"]
        ADAPTER["Adapter<br/>ACPPermissionAdapter<br/>ToolAdapter"]
        REGISTRY["Registry<br/>ChannelRegistry<br/>ContextRegistry<br/>SkillPoolRegistry"]
        FACADE["Facade<br/>Workspace wraps<br/>6 subsystems"]
    end
    
    subgraph Behavioral["🔄 Behavioral"]
        STRATEGY["Strategy<br/>ToolExecutionLevel<br/>NamesakeStrategy"]
        OBSERVER["Observer<br/>Lifecycle Hooks<br/>Config Watchers<br/>Plan Broadcast"]
        STATE["State Machine<br/>Plan subtask states<br/>Pydantic-validated"]
        TEMPLATE["Template Method<br/>BaseChannel.consume_one()<br/>BaseContextManager hooks"]
        CHAIN["Chain of Responsibility<br/>Middleware stack<br/>Guard chain<br/>Command dispatch"]
        COMMAND["Command<br/>/compact, /new, /clear<br/>Slash command handlers"]
        FUTURE["Future Suspension<br/>Approval flow<br/>asyncio.Future"]
    end

    style FACTORY fill:#FF9800,color:#fff
    style SINGLETON fill:#2196F3,color:#fff
    style LAZY fill:#4CAF50,color:#fff
    style MIXIN fill:#9C27B0,color:#fff
    style DECORATOR fill:#00BCD4,color:#fff
    style STRATEGY fill:#f44336,color:#fff
    style STATE fill:#795548,color:#fff
    style CHAIN fill:#607D8B,color:#fff
```

---

## Creational Patterns

### Factory

```python
# Model + Formatter factory
model, formatter = create_model_and_formatter(agent_id)

# Provider model creation
chat_model = provider.create_chat_model()

# Channel from config
channel = BaseChannel.from_config(config)

# Workspace service creation
service = ServiceDescriptor(service_class, init_args, ...)
```

### Singleton

```python
# Global singletons via module-level getter functions
approval_service = get_approval_service()
guard_engine = get_guard_engine()
rate_limiter = LLMRateLimiter.get_instance()
provider_manager = ProviderManager.get_instance()
channel_registry = ChannelRegistry.get_registry()
```

### Lazy Initialization

```python
# Module-level lazy loading (agents/__init__.py)
def __getattr__(name):
    if name == "QwenPawAgent":
        from .react_agent import QwenPawAgent
        return QwenPawAgent

# CLI lazy subcommand loading (cli/main.py)
@click.group(cls=LazyGroup, lazy_subcommands={...})

# Workspace lazy loading (app/)
async def get_agent(agent_id):
    if agent_id not in cache:
        workspace = await create_and_start(agent_id)

# Tool guard lazy init
def _init_tool_guard(self):
    from openspider.security.tool_guard.engine import get_guard_engine
```

---

## Structural Patterns

### Mixin (via MRO)

```python
# Security interceptor in class hierarchy
class QwenPawAgent(ToolGuardMixin, ReActAgent):
    # MRO: QwenPawAgent → ToolGuardMixin → ReActAgent
    # ToolGuardMixin._acting() intercepts before ReActAgent._acting()
```

Also: `ConversationCommandHandlerMixin`, `DaemonCommandHandlerMixin`.

### Decorator / Wrapper

```python
# Retry wrapper around chat models
model = RetryChatModel(ChatModelBase)

# Token usage wrapper
model = TokenRecordingModelWrapper(model)

# Chain: TokenRecordingModelWrapper(RetryChatModel(ChatModelBase))
```

### Adapter

```python
# ACP permission requests → OpenSpider approval flow
class ACPPermissionAdapter:
    async def request_permission(request) -> ApprovalDecision

# ACP tool calls → AgentScope tool schemas
# tool_adapter.py maps external tool views to internal schemas
```

### Registry

```python
# Context manager registry
@context_registry.register("light")
class LightContextManager(BaseContextManager): ...

# Channel registry
registry = ChannelRegistry.get_registry()
registry.get("discord")  # → DiscordChannel class

# Skill pool registry
pool = SkillPoolRegistry()
```

### Facade

```python
# Workspace wraps multiple subsystems
class Workspace:
    runner: AgentRunner
    memory_manager: BaseMemoryManager
    context_manager: BaseContextManager
    mcp_manager: MCPClientManager
    channel_manager: ChannelManager
    cron_manager: CronManager
    chat_manager: ChatManager
```

---

## Behavioral Patterns

### Strategy

```python
# Tool namesake conflict resolution
NamesakeStrategy = Literal["override", "skip", "raise", "rename"]

# Tool guard execution levels
class ToolExecutionLevel(Enum):
    STRICT = "strict"   # ALL tools need approval
    SMART = "smart"     # INFO/LOW auto-allow
    AUTO = "auto"       # Only guarded tools
    OFF = "off"         # Bypass entirely
```

### Observer

```python
# Lifecycle hooks
agent.register_hook("pre_reasoning", compaction_check)
agent.register_hook("post_acting", prune_large_outputs)

# Config file watchers
MCPConfigWatcher.watch(path, callback)

# Plan state broadcast
broadcast_plan_update(plan, session_id)
```

### State Machine

```python
# Plan subtask states (Pydantic-validated)
SubTaskResponse:
    state: Literal["todo", "in_progress", "done", "abandoned"]
    
    @model_validator
    def validate_state_transition(cls, values):
        # todo → in_progress ✓
        # in_progress → done ✓
        # in_progress → abandoned ✓
        # todo → done ✗ (must go through in_progress)
```

### Template Method

```python
# Channel message processing
class BaseChannel(ABC):
    @abstractmethod
    async def consume_one(self, payload) -> None:
        # Subclasses implement platform-specific logic
    
    async def _consume_one_request(self, payload) -> None:
        # Template: normalize → consume_one → send reply

# Context manager hooks
class BaseContextManager(ABC):
    async def pre_reply(self, agent, msg) -> None: ...  # Template hook
    async def pre_reasoning(self, agent, msgs) -> None: ...
```

### Chain of Responsibility

```python
# Middleware stack
CORSMiddleware → AuthMiddleware → CorrelationIDMiddleware → AgentContextMiddleware

# Guard chain
FilePathToolGuardian → RuleBasedToolGuardian → ShellEvasionGuardian

# Command dispatch
daemon_commands → control_commands → conversation_commands → mission → plan → default
```

### Command

```python
# Slash commands
class CommandHandler:
    "/compact" → compact_context()
    "/new" → new_session()
    "/clear" → clear_history()
    "/stop" → cancel_execution()
```

### Future-based Suspension

```python
# Approval flow suspends runner
future = asyncio.Future()
pending = PendingApproval(request_id, tool_name, future)

# Runner blocks
decision = await future  # Suspended until user action

# User resolves
await approval_service.resolve_request(request_id, APPROVED)
# → future.set_result(APPROVED) → runner resumes
```

---

## Async Patterns

| Pattern | Usage | File |
|---------|-------|------|
| `asyncio.Lock` | Tool guard, approval service, MCP manager, multi-agent manager, channel manager, config cache, rate limiter | Multiple |
| `asyncio.Semaphore` | `LLMRateLimiter` — caps concurrent LLM calls | `providers/rate_limiter.py` |
| `asyncio.Future` | `PendingApproval.future` — suspends runner until user approves | `app/approvals/service.py` |
| `asyncio.Queue` | Streaming message pipeline, channel message queues | `app/runner/`, `app/channels/` |
| `asyncio.Event` | ACP permission requests, workspace pending starts | `agents/acp/`, `app/workspace/` |
| `asyncio.Task` | Background task tracking, channel consumers, cron execution | Multiple |
| Cancellable generators | SSE streaming with client disconnect detection | `app/runner/runner.py` |

### Lock Hierarchy

```
1. _tool_guard_lock        (ToolGuardMixin — serializes approval state mutations)
2. _lock                    (MultiAgentManager — serializes workspace creation)
3. _config_lock             (Config cache — serializes config reads/writes)
4. _client_lock             (MCPClientManager — serializes client swaps)
## Async Lock Hierarchy

```mermaid
flowchart TD
    REQUEST(["📨 Incoming Request"]) --> RT["🌐 Request Thread"]
    
    RT --> CFG["_config_lock<br/>(Config reads)"]
    CFG --> MAM["_lock<br/>(MultiAgentManager<br/>workspace creation)"]
    MAM --> MCP_LOCK["_client_lock<br/>(MCPClientManager<br/>client swaps)"]
    MCP_LOCK --> CH_LOCK["_channel_lock<br/>(ChannelManager<br/>registration)"]
    CH_LOCK --> TG_LOCK["_tool_guard_lock<br/>(ToolGuardMixin<br/>approval state)"]
    
    TG_LOCK --> SEM["asyncio.Semaphore<br/>(LLMRateLimiter<br/>concurrent LLM calls)"]
    SEM --> LLM["🤖 LLM Call"]
    LLM --> RELEASE["Release semaphore"]
    
    subgraph "Locks released during I/O"
        CFG -.-> MAM
        MAM -.-> MCP_LOCK
        MCP_LOCK -.-> CH_LOCK
    end

    style REQUEST fill:#4CAF50,color:#fff
    style CFG fill:#2196F3,color:#fff
    style TG_LOCK fill:#f44336,color:#fff
    style SEM fill:#FF9800,color:#fff
    style LLM fill:#9C27B0,color:#fff
```

**Key rule**: Locks are never held across `await` calls that could block (I/O, network). Long operations release locks and re-acquire.

---

## Async Patterns — Visual Reference

```mermaid
flowchart LR
    subgraph Lock["🔒 asyncio.Lock"]
        L1["ToolGuardMixin<br/>approval state mutations"]
        L2["MultiAgentManager<br/>workspace creation"]
        L3["MCPClientManager<br/>client swaps"]
        L4["ChannelManager<br/>registration"]
        L5["Config cache<br/>reads/writes"]
    end
    
    subgraph Sem["🚦 asyncio.Semaphore"]
        S1["LLMRateLimiter<br/>concurrent LLM calls<br/>OPENSPIDER_LLM_MAX_CONCURRENT"]
    end
    
    subgraph Future["⏸️ asyncio.Future"]
        F1["PendingApproval<br/>suspends runner<br/>until user action"]
    end
    
    subgraph Queue["📬 asyncio.Queue"]
        Q1["SSE streaming pipeline<br/>message chunks"]
        Q2["Channel message queues<br/>UnifiedQueueManager"]
    end
    
    subgraph Event["🚩 asyncio.Event"]
        E1["ACP permission requests"]
        E2["Workspace pending starts"]
    end
    
    subgraph Task["📋 asyncio.Task"]
        T1["Background task tracking<br/>TaskTracker"]
        T2["Channel consumer loops"]
        T3["Cron execution"]
        T4["Cancellable generators<br/>SSE disconnect detection"]
    end

    style Lock fill:#2196F3,color:#fff
    style Sem fill:#FF9800,color:#fff
    style Future fill:#f44336,color:#fff
    style Queue fill:#4CAF50,color:#fff
    style Event fill:#9C27B0,color:#fff
    style Task fill:#00BCD4,color:#fff
```

---

### Semaphore Pattern

```python
# Rate limiter: acquire slot before LLM call
async with rate_limiter:
    response = await model(messages)

# Streaming: release slot after first chunk
async for chunk in stream:
    if first_chunk:
        rate_limiter.release()  # Allow next caller
    yield chunk
```

---

## MRO (Method Resolution Order) — Visual

```mermaid
classDiagram
    direction LR
    
    class ReActAgent {
        +reasoning()
        +acting()
        +reply()
    }
    
    class ToolGuardMixin {
        +_acting() **OVERRIDE**
        +_reasoning() **OVERRIDE**
        +_decide_guard_action()
        +_execute_guard_action()
    }
    
    class QwenPawAgent {
        +__init__()
        +_create_toolkit()
        +_register_skills()
    }
    
    ReActAgent <|-- ToolGuardMixin : "extends"
    ToolGuardMixin <|-- QwenPawAgent : "extends"
    
    note for ToolGuardMixin "MRO: QwenPawAgent → ToolGuardMixin → ReActAgent"
```

**Call chain**: `QwenPawAgent._acting()` → `super()._acting()` → `ToolGuardMixin._acting()` → `super()._acting()` → `ReActAgent._acting()`
