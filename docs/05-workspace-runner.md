# 05 — Workspace & Runner

> Workspace lifecycle, ServiceManager, MultiAgentManager, AgentRunner, request dispatch.

---

## Workspace = Isolated Agent Runtime

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

---

## ServiceManager — Priority-Ordered Init

```
ServiceManager.start_all():
    Priority 10: init runner
    Priority 20: init memory, context, mcp, chat (CONCURRENT)
    Priority 25: start runner
    Priority 30: init channel manager
    Priority 40: init cron manager
    Priority 50-51: start config watchers
```

### ServiceDescriptor

```python
class ServiceDescriptor:
    service_class: type
    init_args: tuple
    post_init: Callable | None
    start_method: str    # e.g. "start"
    stop_method: str     # e.g. "stop"
    priority: int        # Lower = earlier
    concurrent_init: bool # Run in parallel with same-priority services
    reusable: bool       # Can be reused across workspaces
```

---

## MultiAgentManager — Lazy Loading

```python
class MultiAgentManager:
    _agents: dict[str, Workspace]
    _lock: asyncio.Lock
    
    async def get_agent(agent_id: str) -> Workspace:
        if agent_id not in self._agents:
            # Lock for dict mutation only
            # Released during slow Workspace.start() for parallelism
            workspace = Workspace(agent_id, workspace_dir)
            await workspace.start()
            self._agents[agent_id] = workspace
        return self._agents[agent_id]
```

**Key design**: The lock is released during slow startup so other agents can start concurrently.

---

## AgentRunner — Request Processing

```python
class AgentRunner(Runner):
    async def stream_query(request: AgentRequest):
        # 1. Command dispatch
        if is_daemon_command:    → daemon_commands.py
        if is_control_command:   → control_commands/
        if is_conversation_cmd:  → CommandHandler
        if is_mission_command:   → mission_dispatch.py
        if is_plan_command:      → activate plan gate
        
        # 2. Create SpiderAgent
        agent = SpiderAgent(config, workspace_dir, ...)
        
        # 3. ReAct loop → SSE streaming
        async for msg, is_last in agent(messages):
            yield format_sse(msg)
```

### Command Dispatch Priority

| Priority | Command Type | Handler |
|----------|-------------|---------|
| 1 | Daemon commands | `/daemon approve`, `/daemon deny`, `/daemon restart` |
| 2 | Control commands | `/stop` |
| 3 | Conversation commands | `/compact`, `/new`, `/clear`, `/dump_history`, `/load_history` |
| 4 | Mission commands | Mission mode control |
| 5 | Plan commands | `/plan <description>` |
| 6 | Normal messages | Create SpiderAgent, run ReAct loop |

### Streaming

```python
async def _stream_printing_messages_interruptible(agent, ...):
    # Cancellable streaming with asyncio.Queue
    # Client disconnect → cancel agent task
    # Error handling: convert_model_exception(), error dump to JSON
```

---

## FastAPI Layer

### Middleware Stack

```
Request
    │
    ▼
CORSMiddleware          [configurable origins via OPENSPIDER_CORS_ORIGINS]
    │
    ▼
AuthMiddleware          [Bearer token validation]
    │
    ▼
CorrelationIDMiddleware [X-Request-Id propagation]
    │
    ▼
AgentContextMiddleware  [extracts X-Agent-Id from header/path]
    │
    ▼
Route handler
```

### Routes

All routers mounted under `/api/` PLUS agent-scoped variants under `/api/agents/{agentId}/`.

### Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config = load_config()
    migrate_legacy_workspace()
    ensure_default_agent()
    manager = MultiAgentManager()
    await manager.start_all()
    load_channels()
    register_custom_channel_routes()
    setup_cron()
    auto_register_admin_user()
    
    yield  # Server running
    
    # Shutdown
    await manager.stop_all()
    cleanup()
```

### Static Files

Console web UI (Vite-built React app) served from `console/` directory — configured via `OPENSPIDER_CONSOLE_STATIC_DIR` env var or built-in package data.
