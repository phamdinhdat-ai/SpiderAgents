# 15 — Agent Flows & Collaboration Patterns

> Comprehensive Mermaid diagrams covering all agent interaction patterns.

---

## Multi-Agent Collaboration Flow

```mermaid
flowchart TD
    USER(["👤 User"]) -->|"Send message"| MAIN["🏠 Main Agent<br/>(SpiderAgent)"]
    
    MAIN --> ANALYZE{"Analyze<br/>intent"}
    ANALYZE -->|"Simple task"| DIRECT["Execute directly<br/>with tools"]
    ANALYZE -->|"Complex / multi-domain"| DELEGATE["Delegate to sub-agents"]
    ANALYZE -->|"Mission mode"| MISSION["Mission Controller<br/>(Phase 1 → Phase 2)"]
    
    DELEGATE --> DISPATCH["Dispatch Workers"]
    DISPATCH --> W1["🤖 Worker Agent 1<br/>chat_with_agent()"]
    DISPATCH --> W2["🤖 Worker Agent 2<br/>chat_with_agent()"]
    DISPATCH --> W3["🤖 Worker Agent 3<br/>chat_with_agent()"]
    
    W1 --> RESULT1["📋 Result 1"]
    W2 --> RESULT2["📋 Result 2"]
    W3 --> RESULT3["📋 Result 3"]
    
    RESULT1 --> AGGREGATE["🔄 Aggregate Results"]
    RESULT2 --> AGGREGATE
    RESULT3 --> AGGREGATE
    
    AGGREGATE --> VERIFY{"Need<br/>verification?"}
    VERIFY -->|Yes| VERIFIER["🔍 Verifier Agent<br/>check_agent_task()"]
    VERIFY -->|No| REPLY
    
    VERIFIER -->|PASS| REPLY
    VERIFIER -->|FAIL| RETRY["Retry worker with<br/>error context"]
    RETRY --> DISPATCH
    
    MISSION --> M_PHASE1["📝 Phase 1: PRD Creation<br/>(Full tool access)"]
    M_PHASE1 --> M_WORKERS["Dispatch Workers<br/>for each story"]
    M_WORKERS --> M_VERIFY["Verifier per story<br/>PASS/FAIL verdict"]
    M_VERIFY --> M_CHECK{"All stories<br/>pass?"}
    M_CHECK -->|No| M_RETRY["Retry failed stories<br/>with context"]
    M_RETRY --> M_WORKERS
    M_CHECK -->|Yes| M_DONE["✅ Mission Complete"]
    
    DIRECT --> REPLY["💬 Reply to User"]
    AGGREGATE --> REPLY
    M_DONE --> REPLY

    style USER fill:#4CAF50,color:#fff
    style MAIN fill:#FF9800,color:#fff
    style DELEGATE fill:#2196F3,color:#fff
    style MISSION fill:#9C27B0,color:#fff
    style REPLY fill:#00BCD4,color:#fff
```

---

## Tool Auto-Registration Flow

```mermaid
flowchart TD
    START(["🧩 Agent __init__()"]) --> READ_CFG["Read AgentProfileConfig<br/>tools.builtin_tools"]
    READ_CFG --> CREATE_TK["Create Toolkit()"]
    
    CREATE_TK --> REG_BUILTIN["Register Built-in Tools"]
    REG_BUILTIN --> ITER_TOOLS["For each tool in config"]
    ITER_TOOLS --> CHECK_ENABLED{"enabled<br/>in config?"}
    CHECK_ENABLED -->|Yes| ADD_TOOL["toolkit.register_tool(name, func)"]
    CHECK_ENABLED -->|No| SKIP["Skip"]
    ADD_TOOL --> CHECK_ASYNC{"async_execution<br/>enabled?"}
    CHECK_ASYNC -->|Yes| ADD_ASYNC["Register companion tools:<br/>view_task, wait_task, cancel_task"]
    CHECK_ASYNC -->|No| NEXT_TOOL
    ADD_ASYNC --> NEXT_TOOL{"More<br/>tools?"}
    SKIP --> NEXT_TOOL
    NEXT_TOOL -->|Yes| ITER_TOOLS
    NEXT_TOOL -->|No| REG_SKILLS["📦 Register Skills"]
    
    REG_SKILLS --> RESOLVE["resolve_effective_skills(agent_id, channel)"]
    RESOLVE --> ITER_SKILLS["For each active skill"]
    ITER_SKILLS --> LOAD_SKILL["Load SKILL.md + scripts"]
    LOAD_SKILL --> CHECK_NAME{"Name conflict<br/>with built-in?"}
    CHECK_NAME -->|Yes| STRATEGY{"namesake_strategy"}
    STRATEGY -->|"skip"| SKIP_SKILL["Skip skill tool"]
    STRATEGY -->|"override"| OVERRIDE["Replace built-in"]
    STRATEGY -->|"raise"| ERROR["Raise error"]
    STRATEGY -->|"rename"| RENAME["Register with prefix"]
    CHECK_NAME -->|No| REG_SKILL["toolkit.register_agent_skill()"]
    OVERRIDE --> REG_SKILL
    RENAME --> REG_SKILL
    SKIP_SKILL --> NEXT_SKILL
    ERROR --> NEXT_SKILL
    REG_SKILL --> NEXT_SKILL{"More<br/>skills?"}
    NEXT_SKILL -->|Yes| ITER_SKILLS
    NEXT_SKILL -->|No| REG_MCP["🔌 Register MCP Tools"]
    
    REG_MCP --> GET_CLIENTS["MCPClientManager.get_clients()"]
    GET_CLIENTS --> ITER_MCP["For each MCP client"]
    ITER_MCP --> LIST_TOOLS["client.list_tools()"]
    LIST_TOOLS --> REG_MCP_TOOL["toolkit.register_mcp_tool()"]
    REG_MCP_TOOL --> NEXT_MCP{"More<br/>clients?"}
    NEXT_MCP -->|Yes| ITER_MCP
    NEXT_MCP -->|No| REG_PLUGIN["🔌 Register Plugin Tools"]
    
    REG_PLUGIN --> LOAD_PLUGINS["PluginRegistry.get_tools()"]
    LOAD_PLUGINS --> ITER_PLUGIN["For each plugin tool"]
    ITER_PLUGIN --> CHECK_SEC{"Security<br/>gated?"}
    CHECK_SEC -->|Yes| CHECK_CONFIG{"Explicitly<br/>enabled?"}
    CHECK_CONFIG -->|No| SKIP_PLUGIN["Skip"]
    CHECK_CONFIG -->|Yes| ADD_PLUGIN["Register"]
    CHECK_SEC -->|No| ADD_PLUGIN
    ADD_PLUGIN --> NEXT_PLUGIN{"More<br/>plugins?"}
    SKIP_PLUGIN --> NEXT_PLUGIN
    NEXT_PLUGIN -->|Yes| ITER_PLUGIN
    NEXT_PLUGIN -->|No| DONE["✅ Toolkit Ready<br/>(20 built-in + skills + MCP + plugins)"]

    style START fill:#4CAF50,color:#fff
    style DONE fill:#2196F3,color:#fff
    style REG_BUILTIN fill:#FF9800,color:#fff
    style REG_SKILLS fill:#9C27B0,color:#fff
    style REG_MCP fill:#00BCD4,color:#fff
```

---

## Agent Selection & Routing Flow

```mermaid
flowchart TD
    REQ(["📨 HTTP Request"]) --> AUTH["AuthMiddleware<br/>Validate Bearer Token"]
    AUTH --> CTX["AgentContextMiddleware<br/>Extract X-Agent-Id"]
    CTX --> RUNNER["DynamicMultiAgentRunner"]
    
    RUNNER --> PARSE{"Parse agent_id<br/>from header/path"}
    PARSE -->|"X-Agent-Id: qa"| QA["MultiAgentManager<br/>.get_agent('qa')"]
    PARSE -->|"X-Agent-Id: default"| DEF["MultiAgentManager<br/>.get_agent('default')"]
    PARSE -->|"Path: /api/agents/bot/..."| BOT["MultiAgentManager<br/>.get_agent('bot')"]
    
    QA --> LOCK{"Workspace 'qa'<br/>in cache?"}
    DEF --> LOCK2{"Workspace 'default'<br/>in cache?"}
    BOT --> LOCK3{"Workspace 'bot'<br/>in cache?"}
    
    LOCK -->|No| CREATE_QA["Create Workspace('qa')<br/>→ ServiceManager.start_all()"]
    LOCK -->|Yes| USE_QA["Return cached Workspace"]
    CREATE_QA --> USE_QA
    
    LOCK2 -->|No| CREATE_DEF["Create Workspace('default')<br/>→ ServiceManager.start_all()"]
    LOCK2 -->|Yes| USE_DEF["Return cached Workspace"]
    CREATE_DEF --> USE_DEF
    
    LOCK3 -->|No| CREATE_BOT["Create Workspace('bot')<br/>→ ServiceManager.start_all()"]
    LOCK3 -->|Yes| USE_BOT["Return cached Workspace"]
    CREATE_BOT --> USE_BOT
    
    USE_QA --> RUN["workspace.runner.stream_query()"]
    USE_DEF --> RUN
    USE_BOT --> RUN
    
    RUN --> AGENT["SpiderAgent created<br/>with agent-specific config"]
    AGENT --> TOOLS["Tools loaded:<br/>agent-specific enabled set"]
    TOOLS --> SKILLS["Skills loaded:<br/>channel-aware resolution"]
    SKILLS --> REPLY["💬 Reply via SSE stream"]

    style REQ fill:#4CAF50,color:#fff
    style RUNNER fill:#FF9800,color:#fff
    style AGENT fill:#2196F3,color:#fff
    style REPLY fill:#9C27B0,color:#fff
```

---

## Context Compaction Loop

```mermaid
flowchart TD
    LOOP_START(["🔄 pre_reasoning hook"]) --> ESTIMATE["EstimatedTokenCounter<br/>.estimate(messages)"]
    ESTIMATE --> CHECK{"Token count<br/>> threshold?"}
    CHECK -->|No| CONTINUE["Continue to reasoning"]
    CHECK -->|Yes| SELECT["Select messages to compact<br/>(keep N most recent)"]
    
    SELECT --> BUILD_PROMPT["Build compaction prompt<br/>(bilingual en/zh)"]
    BUILD_PROMPT --> CALL_COMPACTOR["Call compactor LLM<br/>(smaller model)"]
    CALL_COMPACTOR --> SUMMARY["Get rolling summary"]
    SUMMARY --> REPLACE["Replace old messages<br/>with summary message"]
    REPLACE --> CONTINUE
    
    CONTINUE --> REASON["🧠 LLM reasoning call"]
    REASON --> ACTING{"Has tool<br/>calls?"}
    ACTING -->|Yes| EXEC_TOOL["⚙️ Execute tool"]
    ACTING -->|No| REPLY["💬 Reply to user"]
    
    EXEC_TOOL --> POST_ACT["🪝 post_acting hook<br/>(prune large outputs)"]
    POST_ACT --> CHECK_SIZE{"Output ><br/>DEFAULT_MAX_BYTES?"}
    CHECK_SIZE -->|Yes| TRUNCATE["Truncate + add<br/>TRUNCATION_NOTICE_MARKER"]
    CHECK_SIZE -->|No| ADD_MEM
    TRUNCATE --> ADD_MEM["📝 Add to memory"]
    
    ADD_MEM --> CHECK_ITERS{"More<br/>iterations?"}
    CHECK_ITERS -->|Yes| LOOP_START
    CHECK_ITERS -->|No| REPLY

    style LOOP_START fill:#FF9800,color:#fff
    style CALL_COMPACTOR fill:#9C27B0,color:#fff
    style REASON fill:#2196F3,color:#fff
    style REPLY fill:#4CAF50,color:#fff
```

---

## Provider Selection & Model Routing

```mermaid
flowchart TD
    START(["🔧 create_model_and_formatter(agent_id)"]) --> READ["Read AgentProfileConfig<br/>.active_model"]
    READ --> PARSE["Parse: { provider_id, model_id }"]
    
    PARSE --> GET_PROV["ProviderManager<br/>.get_provider(provider_id)"]
    GET_PROV --> VALID{"Provider<br/>exists?"}
    VALID -->|No| ERR1["❌ ProviderError"]
    VALID -->|Yes| CHECK_MODEL{"Model in<br/>provider.models?"}
    CHECK_MODEL -->|No| CHECK_EXTRA{"Model in<br/>provider.extra_models?"}
    CHECK_EXTRA -->|No| ERR2["❌ Model not found"]
    CHECK_MODEL -->|Yes| CREATE
    CHECK_EXTRA -->|Yes| CREATE
    
    CREATE["provider.create_chat_model(model_id)"] --> BASE["ChatModelBase instance"]
    BASE --> WRAP_RETRY["Wrap: RetryChatModel<br/>(exponential backoff)"]
    WRAP_RETRY --> WRAP_TOKEN["Wrap: TokenRecordingModelWrapper<br/>(usage tracking)"]
    WRAP_TOKEN --> GET_FORMAT["Get formatter for provider"]
    GET_FORMAT --> CHECK_MM{"Model supports<br/>multimodal?"}
    CHECK_MM -->|Yes| SET_MM["Enable multimodal handling"]
    CHECK_MM -->|No| STRIP["Set _openspider_force_strip_media"]
    SET_MM --> RETURN
    STRIP --> RETURN["Return (model, formatter)"]
    
    RETURN --> USE["Used by SpiderAgent<br/>in ReAct loop"]

    style START fill:#4CAF50,color:#fff
    style CREATE fill:#FF9800,color:#fff
    style WRAP_RETRY fill:#2196F3,color:#fff
    style RETURN fill:#9C27B0,color:#fff
```

---

## API Connectivity — Request-Response Lifecycle

```mermaid
sequenceDiagram
    participant UI as 🖥️ React Frontend
    participant API as 🌐 FastAPI Backend
    participant AUTH as 🔐 AuthMiddleware
    participant CTX as 🏷️ AgentContextMiddleware
    participant RUNNER as 🏃 DynamicMultiAgentRunner
    participant MAM as 📦 MultiAgentManager
    participant WS as 🏠 Workspace
    participant AGENT as 🤖 SpiderAgent
    participant LLM as 🧠 LLM Provider

    UI->>API: POST /api/console/chat<br/>{ input, session_id, stream: true }
    Note over UI,API: Headers: Authorization, X-Agent-Id
    
    API->>AUTH: Validate Bearer token
    AUTH-->>API: ✅ Valid
    API->>CTX: Extract agentId from X-Agent-Id
    CTX-->>API: agent_id = "default"
    
    API->>RUNNER: stream_query(request)
    RUNNER->>MAM: get_agent("default")
    
    alt Workspace not cached
        MAM->>WS: Create Workspace("default")
        WS->>WS: ServiceManager.start_all()
        Note over WS: Priority 10-50 initialization
        MAM-->>RUNNER: ✅ Workspace ready
    else Workspace cached
        MAM-->>RUNNER: ✅ Cached Workspace
    end
    
    RUNNER->>WS: runner.stream_query(request)
    WS->>AGENT: Create SpiderAgent(config)
    
    loop ReAct Loop
        AGENT->>LLM: reasoning() → LLM call
        LLM-->>AGENT: Response with/without tool_calls
        
        alt Has tool calls
            AGENT->>AGENT: ToolGuardMixin._acting()
            AGENT->>AGENT: Execute tool
            AGENT->>AGENT: Add result to memory
        else No tool calls
            AGENT-->>WS: reply() → final message
        end
    end
    
    WS-->>RUNNER: SSE events (streaming)
    RUNNER-->>API: SSE chunks
    API-->>UI: text/event-stream
    
    Note over UI,API: Each chunk: { type, content, metadata }
    
    UI->>UI: Render AgentScopeRuntimeResponseCard
    
    opt User cancels
        UI->>API: POST /api/console/chat/stop
        API->>RUNNER: Cancel asyncio.Task
        RUNNER-->>API: 200 OK
    end
```

---

## Approval Polling & Resolution Loop

```mermaid
sequenceDiagram
    participant UI as 🖥️ Frontend
    participant API as 🌐 /api/console/push-messages
    participant AS as ⏸️ ApprovalService
    participant AGENT as 🤖 Agent (suspended)
    participant TOOL as ⚙️ Tool

    loop Every 2.5 seconds
        UI->>API: GET /api/console/push-messages
        API-->>UI: { messages[], pending_approvals[] }
        UI->>UI: Update ApprovalContext
    end
    
    Note over AGENT,TOOL: Agent blocked on asyncio.Future
    
    UI->>UI: Show ApprovalCard<br/>(severity, tool, findings, countdown)
    
    alt User Approves
        UI->>API: POST /api/approval/approve<br/>{ request_id, session_id, reason }
        API->>AS: resolve_request(id, APPROVED)
        AS->>AS: future.set_result(APPROVED)
        AS-->>AGENT: Resume execution
        AGENT->>TOOL: Execute tool
        TOOL-->>AGENT: Result
        UI->>UI: Remove card (exit animation)
        
    else User Denies
        UI->>API: POST /api/approval/deny<br/>{ request_id, session_id, reason }
        API->>AS: resolve_request(id, DENIED)
        AS->>AS: future.set_result(DENIED)
        AS-->>AGENT: Resume execution
        AGENT->>AGENT: Return error message
        UI->>UI: Remove card (exit animation)
        
    else Timeout (300s)
        AS->>AS: future.set_result(TIMEOUT)
        AS-->>AGENT: Resume execution
        AGENT->>AGENT: Auto-deny, return error
        UI->>UI: Remove card (timeout)
    end
```

---

## Mission Mode — Two-Phase Loop

```mermaid
flowchart TD
    START(["🚀 Mission Start"]) --> PHASE1["📝 Phase 1: PRD Creation"]
    PHASE1 --> EXPLORE["Agent explores codebase<br/>(full tool access)"]
    EXPLORE --> WRITE_PRD["Write prd.json<br/>{ userStories[] }"]
    WRITE_PRD --> VALIDATE{"prd.json<br/>valid?"}
    VALIDATE -->|No| FIX_PRD["Fix schema issues"]
    FIX_PRD --> VALIDATE
    VALIDATE -->|Yes| TRANSITION["🔒 Transition to Phase 2<br/>(DEACTIVATE implementation tools)"]
    
    TRANSITION --> PHASE2["⚙️ Phase 2: Execution Loop"]
    PHASE2 --> READ_STORIES["Read prd.json<br/>Find unpassed stories"]
    READ_STORIES --> HAS_REMAIN{"Remaining<br/>stories?"}
    HAS_REMAIN -->|No| DONE["✅ All stories pass"]
    HAS_REMAIN -->|Yes| DISPATCH["Dispatch Workers<br/>openspider agents chat --background"]
    
    DISPATCH --> WORKER["🤖 Worker Agent<br/>Implements story"]
    WORKER --> VERIFIER["🔍 Verifier Agent<br/>Checks acceptance criteria"]
    VERIFIER --> VERDICT{"PASS/FAIL<br/>verdict?"}
    VERDICT -->|PASS| MARK_PASS["Mark story passes: true"]
    VERDICT -->|FAIL| RETRY_CTX["Retry with error context"]
    MARK_PASS --> CHECK_MAX{"Max iterations<br/>reached?"}
    RETRY_CTX --> CHECK_MAX
    CHECK_MAX -->|No| HAS_REMAIN
    CHECK_MAX -->|Yes| DONE_WARN["⚠️ Max iterations<br/>(partial completion)"]
    
    DONE --> SUMMARY["Generate completion summary<br/>✅/❌ per story"]
    DONE_WARN --> SUMMARY
    SUMMARY --> RESTORE["🔓 Restore implementation tools"]
    RESTORE --> END(["🏁 Mission End"])

    style START fill:#4CAF50,color:#fff
    style PHASE1 fill:#FF9800,color:#fff
    style PHASE2 fill:#2196F3,color:#fff
    style DONE fill:#9C27B0,color:#fff
    style END fill:#00BCD4,color:#fff
```

---

## Plan Mode — State Machine

```mermaid
stateDiagram-v2
    [*] --> Idle: No plan active
    
    Idle --> Planning: /plan <description>
    Planning --> AwaitingApproval: Plan created
    
    AwaitingApproval --> Executing: User approves
    AwaitingApproval --> Idle: User rejects
    
    Executing --> Executing: Subtask in_progress
    Executing --> AwaitingApproval: Plan modified
    
    state Executing {
        [*] --> TodoSelected
        TodoSelected --> InProgress: Start subtask
        InProgress --> Done: Complete subtask
        InProgress --> Abandoned: Abandon subtask
        Done --> TodoSelected: Next subtask
        Abandoned --> TodoSelected: Next subtask
    }
    
    Executing --> Idle: All subtasks done/abandoned
```

---

## Channel Message Routing

```mermaid
flowchart LR
    subgraph External["🌍 External Platforms"]
        DC["Discord"]
        TG["Telegram"]
        DT["DingTalk"]
        FS["Feishu"]
        QQ["QQ"]
        WECOM["WeCom"]
        WECHAT["WeChat"]
        IM["iMessage"]
        MT["Mattermost"]
        MQTT["MQTT"]
        MATRIX["Matrix"]
        VOICE["Voice/SIP"]
    end
    
    subgraph Channels["📡 Channel Layer"]
        direction TB
        ADAPTERS["Platform-specific<br/>adapters"]
        CM["ChannelManager"]
        QUEUES["UnifiedQueueManager<br/>(asyncio.Queue per channel)"]
        CONSUMERS["Consumer loops<br/>(asyncio.Tasks)"]
    end
    
    subgraph Core["🏠 Core"]
        RUNNER["DynamicMultiAgentRunner"]
        MAM["MultiAgentManager"]
        WS["Workspace → Agent"]
    end
    
    DC --> ADAPTERS
    TG --> ADAPTERS
    DT --> ADAPTERS
    FS --> ADAPTERS
    QQ --> ADAPTERS
    WECOM --> ADAPTERS
    WECHAT --> ADAPTERS
    IM --> ADAPTERS
    MT --> ADAPTERS
    MQTT --> ADAPTERS
    MATRIX --> ADAPTERS
    VOICE --> ADAPTERS
    
    ADAPTERS --> CM
    CM --> QUEUES
    QUEUES --> CONSUMERS
    CONSUMERS --> RUNNER
    RUNNER --> MAM
    MAM --> WS
