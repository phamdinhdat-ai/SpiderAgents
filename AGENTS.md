<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **SpiderAgents** (33053 symbols, 55836 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/SpiderAgents/context` | Codebase overview, check index freshness |
| `gitnexus://repo/SpiderAgents/clusters` | All functional areas |
| `gitnexus://repo/SpiderAgents/processes` | All execution flows |
| `gitnexus://repo/SpiderAgents/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

---

# SpiderAgents / OpenSpider — Project Instructions

## Product Direction: AgentSpider

AgentSpider is the owner's long-term platform for bringing conversational AI,
executable commands and jobs, and infrastructure integrations into one coherent
experience. Treat this product direction as the basis for feature decisions.
The repository is named SpiderAgents; the active implementation is OpenSpider.
Keep existing package names, CLI commands, and `OPENSPIDER_*` configuration unless
a branding migration is explicitly requested.

The three product pillars are:

- **Chat**: users express intent, retain conversation context, and follow agent
  progress through streaming responses and clear tool feedback.
- **Commands and jobs**: turn intent into executable tasks, plans, and scheduled
  work with visible status, results, failures, and approval requests.
- **Infrastructure connections**: connect agents to external tools, services,
  and infrastructure through MCP and existing extension mechanisms. Describe
  supported integrations from code; distinguish proposed capabilities from
  those already implemented.

Prefer complete user journeys: request in chat, inspect the intended action,
approve when required, execute through the existing runner and tool guard,
and receive a traceable result. Preserve user and agent isolation, protect
credentials, and make failures actionable when adding infrastructure actions.
Never treat an LLM response as proof that a job or infrastructure action succeeded.

## Working Map

| Area | Starting point |
|------|----------------|
| Web console (React, TypeScript, Vite) | `console/` |
| Application and API | `src/openspider/app/` |
| Conversation execution | `src/openspider/app/runner/`, `src/openspider/agents/` |
| Plans and scheduled jobs | `src/openspider/plan/`, `src/openspider/app/crons/` |
| MCP and extensions | `src/openspider/app/mcp/`, `src/openspider/plugins/` |
| Messaging channels | `src/openspider/app/channels/` |
| Model providers | `src/openspider/providers/` |
| Approvals and tool security | `src/openspider/app/approvals/`, `src/openspider/security/` |
| Persistence and configuration | `src/openspider/db/`, `src/openspider/config/` |
| Tests | `tests/unit/`, `tests/contract/`, `tests/integration/` |

For backend changes, use `src/openspider/`; update the shared console, tests,
deployment files, or documentation when the feature requires them. The frozen
`src/qwenpaw/` baseline must remain untouched unless explicitly requested.

## Collaboration and Verification

- Communicate in Vietnamese by default with this owner; keep code identifiers
  and established technical terminology consistent with the repository.
- Read existing implementation and applicable instructions before changing it.
  Keep changes focused on the requested outcome and preserve unrelated work.
- For chat, job, or integration changes, check the relevant API, execution path,
  persistence, and console behavior rather than stopping at an isolated helper.
- Use the existing approval gate for privileged actions. Do not log or embed
  real credentials in code, examples, or documentation.
- Run checks relevant to the change and report what passed and what could not
  run. On Windows without Make, use `python -m pytest tests/unit/ -x -q --tb=line`
  for the equivalent of `make quick`; scope tests to affected behavior as needed.
- For console changes, use the scripts in `console/package.json`: `npm run lint`,
  `npm run build`, and relevant Vitest tests (`npx vitest run <test-path>`), from
  `console/`.
- Report the delivered behavior, verification results, and remaining limitations.

## Critical Rule: OpenSpider is the Active Target

**OpenSpider** (`src/openspider/`) is the active development branch. **QwenPaw** legacy baseline (`src/qwenpaw/`) is the legacy baseline — structurally identical but frozen.

- **All new features & bugfixes go into `src/openspider/` only.**
- **NEVER modify `src/qwenpaw/`** unless explicitly asked. It exists only as a reference baseline.
- The two trees were kept in sync; OpenSpider now diverges with the `OPENSPIDER_*` env-var migration and other improvements.

Full architecture docs: [README_openspider.md](README_openspider.md)

## Build & Test

```bash
pip install -e ".[dev]"          # dev install
make test                        # Full suite
make test-unit                   # Unit only (fast)
make quick                       # Unit, fail-fast (-x -q)
make test-contract               # Channel/provider contracts
make test-integration            # Integration (requires running app)
make coverage-full               # HTML + terminal coverage
```

See [Makefile](Makefile) for all targets. `pytest` uses `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed). Coverage threshold: **30%** on `src/openspider`.

## Database Configuration

OpenSpider uses **SQLite + JSON files** by default for all persistent data (auth, MCP config, chat history, settings, knowledge docs).

To switch to **PostgreSQL**, set these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSPIDER_DATABASE_ENABLED` | `false` | Set to `true` to use PostgreSQL for all storage |
| `OPENSPIDER_DATABASE_URL` | `postgresql+asyncpg://localhost:5433/openspider` | PostgreSQL connection URL (asyncpg driver) |

### Quick Start with PostgreSQL

```bash
# 1. Start the database
docker compose -f docker-compose.postgres.yaml up -d

# 2. Enable PG in your environment
export OPENSPIDER_DATABASE_ENABLED=true

# 3. (First time) Migrate existing data from SQLite/JSON
python scripts/migrate_to_postgres.py

# 4. Start normally
openspider app
```

### Architecture

When PG is enabled, data migrates as follows:

| Data | File/SQLite (legacy) | PostgreSQL table |
|------|---------------------|-----------------|
| Users & passwords | `auth.json` | `openspider_users` |
| JWT secret | `auth.json` (encrypted) | `auth_meta` |
| Token revocation | `auth.json` | `token_revocations` |
| MCP server configs | `user_data.db` | `mcp_servers` |
| Knowledge documents | `user_data.db` | `knowledge_documents` |
| User settings | `user_data.db` | `user_settings` |
| Chat list | `chats.json` | `chats` |
| Chat history | Session JSON files | `session_messages` |
| User config overlay | `config.json` per user | `user_configs` |

The file-based storage remains fully functional as fallback when `OPENSPIDER_DATABASE_ENABLED` is `false` or unset.

See `.env.example` for all available environment variables.

## Code Conventions

- **Pydantic everywhere**: config, provider info, plan schemas — `BaseModel`, `model_validate()` for cross-module loads.
- **Async-first**: all I/O is `async def`; `asyncio.Lock`/`asyncio.Future`; never block the event loop.
- **Env-var namespace**: `OPENSPIDER_*` is canonical. Legacy `OPENSPIDER_*` and `COPAW_*` fall back via `_get_env()` in [`constant.py`](src/openspider/constant.py). Use `EnvVarLoader` for type-safe access. **NEW env vars MUST use `OPENSPIDER_*` prefix.**
- **Skills are Markdown**: each skill is `SKILL.md` + optional Python scripts, bilingual (`*-en/`, `*-zh/`).
- **AgentScope foundation**: agents, runner, exceptions extend `agentscope`/`agentscope-runtime` primitives.

## Key Patterns

### Approval Gate (security)
`ToolGuardMixin` → `ApprovalService.create_pending()` → suspend runner → user resolves → `resolve_request()` → runner resumes. Never auto-approve without a real resolution signal. See `app/approvals/service.py`.

### Multi-Agent Lazy Loading
`MultiAgentManager` creates `Workspace` on first request; lock released during slow startup for parallelism.

### Provider Pattern
Implement `Provider` ABC in `providers/<name>_provider.py`, register in `ProviderManager`, add `ProviderInfo` Pydantic model with capability flags.

### Channel Pattern
Subclass `BaseChannel` in `app/channels/<name>/channel.py`, implement `start()`, `stop()`, message routing. Add contract tests in `tests/contract/channels/`.

## Development Focus Areas (OpenSpider Improvements)

When working on `openspider`, prioritize:
1. **Interaction**: faster SSE streaming, richer slash-command feedback, improved multi-turn context in `app/runner/`.
2. **Processing**: parallelise subtask execution in `plan/`, increase `LLM_MAX_CONCURRENT` default, reduce per-tool overhead.
3. **Branding migration**: finish `OPENSPIDER_*` → `OPENSPIDER_*` migration in `constant.py` (backward-compat fallback exists).
4. **Project name**: `PROJECT_NAME = "OpenSpider"` in `constant.py`.

## Security Rules

YAML rule files in `security/tool_guard/rules/signatures/`: `command_injection`, `data_exfiltration`, `hardcoded_secrets`, `obfuscation`, `prompt_injection`, `social_engineering`, `supply_chain`, `unauthorized_tool_use`. `ExecLevel`: `FREE` / `APPROVAL_REQUIRED` / `BLOCKED`. Never bypass `ToolGuardMixin`.

## External Docs (Link, Don't Duplicate)

- Full architecture & component map: [README_openspider.md](README_openspider.md)
- Contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md)
- Feature development instructions: [.github/instructions/feature-development.instructions.md](.github/instructions/feature-development.instructions.md)
