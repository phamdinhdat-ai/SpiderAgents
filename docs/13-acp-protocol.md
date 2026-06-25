# 13 — ACP Protocol

> Agent Communication Protocol — OpenSpider as an ACP server + hosted external agents.

---

## What is ACP?

ACP = **Agent Communication Protocol** — a Zed Industries standard for agent interoperability over stdio JSON-RPC.

OpenSpider can act as both:
1. **ACP Server** — expose OpenSpider agents to external ACP clients (Zed, OpenCode, etc.)
2. **ACP Host** — integrate external ACP agents as tools within OpenSpider

---

## ACP Server

```
External ACP Client (Zed, OpenCode, etc.)
    │  stdio JSON-RPC
    ▼
OpenSpiderACPAgent (agents/acp/server.py)
    │  Boots full Workspace lifecycle
    │
    ├── initialize()
    │   └── Capabilities exchange: load_session, session close/list/resume
    │
    ├── new_session()
    │   └── Create session with cwd, MCP servers, mode
    │
    ├── load_session()
    │   └── Resume existing session
    │
    ├── prompt()
    │   └── Forward text to Workspace.runner
    │       └── SSE-like streaming via session_update()
    │
    ├── cancel()
    │   └── Cancel running task via asyncio.Event
    │
    ├── set_session_model()
    │   └── Switch model per session (writes agent.json)
    │
    ├── set_config_option()
    │   └── Toggle modes: "default" or "bypassPermissions"
    │
    └── close_session() / list_sessions() / resume_session()
```

### Agent Info

```python
# Exposed to ACP clients
agent_info = Implementation(
    name="openspider",
    title="OpenSpider",
    version=__version__,
)
```

### Session Modes

| Mode | Tool Guard | Description |
|------|-----------|-------------|
| `default` | Enabled | Normal mode with security checks |
| `bypassPermissions` | Disabled | All security checks skipped |

### Workspace Lifecycle

The ACP agent boots a **full Workspace** — same lifecycle as the web console:
- MCP tools, memory, chat persistence, sub-agent delegation
- All capabilities available

---

## ACP Hosted Clients

External ACP agents exposed as tools within OpenSpider:

```python
# agents/acp/core.py + hosted/
ACPHostedClient
    ├── opencode_client      # OpenCode agent
    ├── qwen_code_client     # QwenCode agent
    ├── claude_code_client   # Claude Code agent
    └── codex_client         # Codex agent
```

### Configuration

```python
# In agent.json
ACPConfig:
    agents:
      - id: "opencode"
        command: ["opencode"]
      - id: "claude_code"
        command: ["claude"]
```

---

## ACP Service

```python
# agents/acp/service.py
class ACPService:
    # Runs alongside the main app
    # Manages ACP server lifecycle
    
    async def start() -> None: ...
    async def stop() -> None: ...
```

### Startup

```bash
# Standalone ACP server
openspider acp

# Or as part of the full app (config-based)
```

---

## Permission Adapter

```python
# agents/acp/permission_adapter.py
class ACPPermissionAdapter:
    # Translates ACP permission requests to OpenSpider approval flow
    # SuspendedPermission → PendingApproval
    
    async def request_permission(request) -> ApprovalDecision: ...
```

---

## Protocol Details

### Initialize

```json
// Request
{ "method": "initialize", "params": { "protocol_version": 1 } }

// Response
{
    "protocol_version": 1,
    "agent_capabilities": {
        "load_session": true,
        "session_capabilities": {
            "close": {},
            "list": {},
            "resume": {}
        }
    },
    "agent_info": {
        "name": "openspider",
        "title": "OpenSpider",
        "version": "1.0.0"
    }
}
```

### Prompt → Stream

```json
// Request
{
    "method": "prompt",
    "params": {
        "session_id": "abc123",
        "prompt": [{ "type": "text", "text": "Hello" }]
    }
}

// Streamed updates
{
    "sessionUpdate": "agent_message_chunk",
    "content": { "type": "text", "text": "Hello! How can I help?" }
}
```

### Usage Tracking

Each LLM call emits usage metadata:
```json
{
    "sessionUpdate": "agent_message_chunk",
    "content": { "type": "text", "text": "" },
    "field_meta": {
        "usage": {
            "inputTokens": 150,
            "outputTokens": 50,
            "totalTokens": 200
        }
    }
}
```
