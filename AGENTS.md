<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **SpiderAgents** (51961 symbols, 83755 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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