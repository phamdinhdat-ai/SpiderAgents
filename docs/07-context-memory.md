# 07 — Context & Memory

> Memory stack, context compaction, ReMe integration, tool-result pruning.

---

## Memory Stack

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

---

## Context Compaction Flow

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

### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENSPIDER_MEMORY_COMPACT_KEEP_RECENT` | 3 | Keep N most recent messages |
| `OPENSPIDER_MEMORY_COMPACT_RATIO` | 0.7 | Compaction threshold ratio |

---

## BaseContextManager (ABC)

```python
class BaseContextManager(ABC):
    async def start() -> None: ...
    async def close() -> None: ...
    
    # Lifecycle hooks
    async def pre_reply(agent, msg) -> None: ...
    async def pre_reasoning(agent, msgs) -> None: ...
    async def post_acting(agent, result) -> None: ...
    async def post_reply(agent, reply) -> None: ...
    
    def get_agent_context() -> AgentContext: ...
```

### Registry Pattern

```python
# Registered via decorator
@context_registry.register("light")
class LightContextManager(BaseContextManager):
    ...
```

---

## LightContextManager

### Tool-Result Pruning

```python
# Large tool outputs are truncated
if len(tool_result) > DEFAULT_MAX_BYTES:
    truncated = tool_result[:DEFAULT_MAX_BYTES] + TRUNCATION_NOTICE_MARKER
```

### Compactor Prompts

Bilingual (en/zh) system/user prompts for the compaction LLM call. The compactor uses a smaller, faster model to summarize old messages into a rolling context window.

### EstimatedTokenCounter

Cheap token estimation before full count — avoids expensive tokenization for every message.

---

## ReMe Integration

The `LightMemoryManager` wraps ReMe (Retrieval-Enhanced Memory Engine) for:

- **Persistence**: Conversation memory stored on disk
- **Semantic search**: Find relevant past conversations
- **File watching**: Auto-detect changes to `MEMORY.md` files
- **Vector + FTS**: Optional vector embedding and full-text search

### Configuration

```yaml
# ReMe config (auto-generated)
embedding_models:
  default:
    backend: openai
    dimensions: 1024
file_stores:
  default:
    backend: local
    vector_enabled: false
    fts_enabled: true
file_watchers:
  default:
    watch_paths:
      - <workspace>/MEMORY.md
      - <workspace>/memory.md
      - <workspace>/memory/
```
