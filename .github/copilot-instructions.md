# SpiderAgents / OpenSpider — Copilot Instructions

## Project Overview

**OpenSpider** (`src/openspider/`) is a self-hosted personal AI agent assistant — a rebrand/evolution of **QwenPaw** (`src/qwenpaw/`). Both trees are currently in sync; `openspider` is the active development target with goals of better interaction responsiveness and processing throughput. All new features go into `src/openspider/`. Do not modify `src/qwenpaw/` unless explicitly asked.

## Architecture

```
src/openspider/
├── agents/          # QwenPawAgent (ReActAgent subclass) + ToolGuardMixin + SkillSystem + MCP tools
├── app/             # FastAPI app, DynamicMultiAgentRunner, channels (15+), routers, runner, workspace, crons, mcp
├── providers/       # Provider ABC + OpenAI/Anthropic/Gemini/Ollama/etc. adapters
├── plan/            # PlanStateResponse / SubTaskResponse schemas + broadcast helpers
├── config/          # load_config(), timezone, context
├── security/        # YAML rule engine (tool_guard) + skill_scanner
├── envs/            # persisted env var store
├── cli/             # rich CLI entry points
├── plugins/         # plugin loader/registry
└── token_usage/     # usage buffer + storage
```

Key data flow: HTTP/channel message → `DynamicMultiAgentRunner` (routes by `X-Agent-Id`) → `Workspace` (lazy-loaded via `MultiAgentManager`) → `Runner` → `QwenPawAgent` → tool calls → `ToolGuardMixin` → `ApprovalService` (if security rule trips) → LLM provider.

## Code Style & Conventions

- **Pydantic everywhere**: config, provider info, plan schemas — use `BaseModel`, `model_validate()` for cross-module loads.
- **Async-first**: all I/O is `async def`; use `asyncio.Lock` / `asyncio.Future`; never block the event loop.
- **Env-var namespace**: `OPENSPIDER_*` for new env vars. Legacy `QWENPAW_*` and `COPAW_*` fall back via `_get_env()` in `constant.py`. Follow the same `EnvVarLoader` pattern.
- **Skills are Markdown**: each skill is a directory with `SKILL.md` + optional Python scripts, bilingual (`*-en/`, `*-zh/`).
- **Approval gate pattern**: `ToolGuardMixin` → `ApprovalService.create_pending()` → suspend runner → user resolves → `resolve_request()` → runner resumes. See [`app/approvals/service.py`](../src/openspider/app/approvals/service.py).
- **AgentScope foundation**: agent, runner, and exception hierarchy extend `agentscope` / `agentscope-runtime` primitives. Exceptions inherit from `agentscope_runtime`.
- **Multi-agent lazy loading**: `MultiAgentManager` creates `Workspace` on first request; lock released during slow startup for parallelism.

## Build & Test

```bash
pip install -e ".[dev]"          # dev install
make test                        # full test suite
make test-unit                   # unit tests only (fast)
make quick                       # unit tests, fail-fast (-x -q)
make test-contract               # channel/provider contract tests
make test-integration            # integration tests (requires running app)
make coverage-full               # HTML + terminal coverage report
```

`pytest` is configured with `asyncio_mode = "auto"` — all async tests run without extra decoration. Coverage threshold: 30% (`src/openspider`). Test markers: `slow`, `unit`, `contract`, `integration`.

## OpenSpider vs QwenPaw — What to Improve

When extending `openspider` beyond the qwenpaw baseline, focus on:
1. **Interaction**: faster SSE streaming, richer slash-command feedback, improved multi-turn context handling in `app/runner/`.
2. **Processing**: parallelise subtask execution in `plan/`, increase `LLM_MAX_CONCURRENT` default, reduce per-tool overhead in `agents/tools/`.
3. **Env-var prefix**: migrate constants in `constant.py` from `QWENPAW_` → `OPENSPIDER_` with backward-compat fallback.
4. **Project name**: `PROJECT_NAME = "OpenSpider"` in `constant.py`.

## Integration Points

- **AgentScope / agentscope-runtime**: core agent loop, runner engine, `ChatModelBase`, toolkit.
- **APScheduler**: cron scheduling in `app/crons/`.
- **MCP (Model Context Protocol)**: `HttpStatefulClient` / `StdIOStatefulClient` in `app/mcp/`.
- **Channels**: each channel in `app/channels/<name>/channel.py` inherits `BaseChannel`. Add new channels there.
- **LLM concurrency**: `LLM_MAX_CONCURRENT=10`, `LLM_MAX_QPM=600` (env-tunable).

## Security

- `security/tool_guard/rules/signatures/` — YAML rule files: `command_injection`, `data_exfiltration`, `hardcoded_secrets`, `obfuscation`, `prompt_injection`, `social_engineering`, `supply_chain`, `unauthorized_tool_use`.
- `ExecLevel` enum: `FREE` / `APPROVAL_REQUIRED` / `BLOCKED`.
- Never bypass `ToolGuardMixin` checks; never auto-approve without a real resolution signal.
- Auth middleware lives in `app/_app.py`.
