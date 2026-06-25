# 03 — Provider Pattern

> LLM provider abstraction, model creation chain, rate limiting, retry logic.

---

## Provider ABC

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

---

## Provider Implementations

| Provider | Chat Model Class | Notes |
|----------|-----------------|-------|
| `OpenAIProvider` | `OpenAIChatModel` | Also handles DashScope, TokenPlan; LangFuse tracing |
| `AnthropicProvider` | `AnthropicChatModel` | Claude models |
| `GeminiProvider` | `GeminiChatModel` | Google AI |
| `OllamaProvider` | `OllamaChatModel` | Local Ollama |
| `LMStudioProvider` | `LMStudioChatModel` | Local LM Studio |
| `OpenRouterProvider` | `OpenRouterChatModel` | Multi-provider aggregator |

---

## ModelInfo (Pydantic)

```python
class ModelInfo(BaseModel):
    id: str                    # Model identifier used in API calls
    name: str                  # Human-readable model name
    supports_multimodal: bool | None   # None = not yet probed
    supports_image: bool | None
    supports_video: bool | None
    probe_source: str | None   # "documentation" or "probed"
    is_free: bool              # Free to use (no API cost)
    generate_kwargs: dict      # Per-model generation overrides
```

---

## Model Creation Chain

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
    │  - Retry on: 429, 500, 502, 503, 504, 529 + network errors
    │  - Streaming: semaphore slot released after first chunk
    │
    ▼
TokenRecordingModelWrapper(ChatModel)  [usage tracking]
    │  - Records prompt_tokens, completion_tokens per call
    │  - Per-session aggregation
    │
    ▼
Return (model, formatter) tuple
```

---

## ProviderManager (Singleton)

```python
class ProviderManager:
    # Pre-defines built-in models for:
    # ModelScope, DashScope, Aliyun TokenPlan, OpenAI, Anthropic,
    # Gemini, Ollama, DeepSeek, Grok
    
    async def list_providers() -> list[ProviderInfo]: ...
    async def add_custom_provider(info: ProviderInfo) -> None: ...
    def get_chat_model(provider_id, model_id) -> ChatModelBase: ...
```

**Secret encryption**: `api_key` fields encrypted via Fernet before disk storage; decrypted on load via `decrypt_dict_fields()`.

---

## Rate Limiting

### LLMRateLimiter (Singleton)

```
LLMRateLimiter
    ├── asyncio.Semaphore ──► caps concurrent LLM calls
    │   └── Configurable: OPENSPIDER_LLM_MAX_CONCURRENT (default: 10)
    │
    ├── QPM sliding window ──► 60-second window, proactive wait
    │   └── Configurable: OPENSPIDER_LLM_MAX_QPM (default: 600)
    │
    └── Global pause on 429 ──► eliminates thundering herd
        ├── Pause: OPENSPIDER_LLM_RATE_LIMIT_PAUSE (default: 5.0s)
        └── Jitter: OPENSPIDER_LLM_RATE_LIMIT_JITTER (default: 1.0s)
```

### RetryChatModel

Wraps `ChatModelBase` with exponential backoff:

```
Retry on: 429, 500, 502, 503, 504, 529 + network errors
    ├── Max retries: OPENSPIDER_LLM_MAX_RETRIES (default: 3)
    ├── Backoff base: OPENSPIDER_LLM_BACKOFF_BASE (default: 1.0)
    └── Backoff cap: OPENSPIDER_LLM_BACKOFF_CAP (default: 10.0)
```

---

## Model Capability Cache

`get_capability_cache()` — caches multimodal capability probe results from `multimodal_prober.py` to avoid repeated API calls.

**Probe flow**:
1. Check documentation source first (fast)
2. If unknown, run actual probe (sends test multimodal request)
3. Cache result for session duration
