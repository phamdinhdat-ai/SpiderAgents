# 08 — Configuration System

> Pydantic model hierarchy, env var system, config loading, agent profiles.

---

## Pydantic Model Hierarchy

### Root Config (`config.json`)

```python
class Config(BaseModel):
    channels: ChannelConfig[]     # Union of all channel types
    security: SecurityConfig
        tool_guard: ToolGuardConfig
        file_guard: FileGuardConfig
    acp: ACPConfig                # ACP agent definitions
    active_llm: ModelSlotConfig   # (provider_id, model)
    user_timezone: str
    language: str
```

### Agent Profile (`<workspace>/agent.json`)

```python
class AgentProfileConfig(BaseModel):
    id: str                       # Unique agent identifier
    name: str                     # Display name
    description: str
    language: str                 # "en" | "zh" | etc.
    
    running: AgentsRunningConfig
        max_iters: int            # Max ReAct loop iterations
        max_input_length: int     # Max input token length
        memory_compact_threshold: int
        heartbeat: HeartbeatConfig
        parallel_tool_calls: bool
    
    tools: ToolsConfig
        builtin_tools: dict[str, ToolConfig]
            enabled: bool
            async_execution: bool
    
    active_model: ModelSlotConfig
        provider_id: str
        model: str
    
    approval_level: ToolExecutionLevel  # STRICT | SMART | AUTO | OFF
    
    mcp: MCPConfig
    acp: ACPConfig
    channels: ...                 # Per-agent channel configs
```

---

## Config Loading

```python
# Thread-safe, cached, mtime-invalidated
config = load_config()                    # from config.json
agent_config = load_agent_config(agent_id) # from <workspace>/agent.json

# Validation
strict_validate_config_file(path)  # Full Pydantic validation pass
```

**Cache strategy**: Configs are cached in memory. On next access, mtime is checked — if file changed, reload and re-validate.

---

## Env Var System

### `_get_env()` — Fallback Chain

```python
# constant.py
def _get_env(key: str, default: str = "") -> str:
    """
    Lookup order:
    1. The key as-is (e.g. OPENSPIDER_FOO)
    2. If OPENSPIDER_*: check QWENPAW_* legacy variant
    3. If QWENPAW_*: check OPENSPIDER_* canonical variant
    4. COPAW_* legacy variant (last resort)
    """
```

### EnvVarLoader — Type-Safe Access

```python
class EnvVarLoader:
    @staticmethod
    def get_bool(env_var: str, default: bool = False) -> bool: ...
    
    @staticmethod
    def get_float(env_var: str, default: float = 0.0,
                  min_value=None, max_value=None,
                  allow_inf=False) -> float: ...
    
    @staticmethod
    def get_int(env_var: str, default: int = 0,
                min_value=None, max_value=None) -> int: ...
    
    @staticmethod
    def get_str(env_var: str, default: str = "") -> str: ...
```

### Key Env Vars

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENSPIDER_WORKING_DIR` | `~/.openspider` | Root data directory |
| `OPENSPIDER_SECRET_DIR` | `{WORKING_DIR}.secret` | Encrypted secrets |
| `OPENSPIDER_CONFIG_FILE` | `config.json` | Main config file |
| `OPENSPIDER_LOG_LEVEL` | `info` | Log level |
| `OPENSPIDER_CORS_ORIGINS` | (empty) | CORS allowed origins |
| `OPENSPIDER_LLM_MAX_CONCURRENT` | `10` | Max concurrent LLM calls |
| `OPENSPIDER_LLM_MAX_QPM` | `600` | Max queries per minute |
| `OPENSPIDER_TOOL_GUARD_APPROVAL_TIMEOUT_SECONDS` | `300` | Approval timeout |
| `OPENSPIDER_RUNNING_IN_CONTAINER` | `false` | Docker detection |

---

## Working Directory Priority

```
1. OPENSPIDER_WORKING_DIR env var → use it
2. Default → ~/.openspider (created if missing)
```

---

## Persistent Env Store (`envs/`)

Environment variables can be persisted to `envs.json` under `SECRET_DIR`:

```python
load_envs_into_environ()  # Called during package init
save_envs(envs_dict)      # Persist to disk
```

**Protected bootstrap keys** (from process env only, not persisted):
- `OPENSPIDER_WORKING_DIR`
- `OPENSPIDER_SECRET_DIR`
