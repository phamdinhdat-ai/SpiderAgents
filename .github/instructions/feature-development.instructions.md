---
description: "Use when adding new features, updating existing functionality, creating new files, or modifying modules in src/openspider/. Covers pre-implementation research, import validation, structure placement, and logical reasoning steps."
applyTo: "src/openspider/**"
---

# Feature Development — OpenSpider

## 1. Research Before Writing Code

Before writing any new code or modifying an existing module:

1. **Search for existing implementations first.** Use `grep_search` or `semantic_search` to check whether the feature, utility, or pattern already exists somewhere in `src/openspider/`. Duplicate logic is forbidden.
2. **Read the target file in full** before editing it. Understand its imports, class hierarchy, and existing method signatures.
3. **Trace the relevant execution flow.** For anything touching the agent loop, identify where it sits in the chain:
   `HTTP/channel → DynamicMultiAgentRunner → Workspace → Runner → QwenPawAgent → ToolGuardMixin → Provider`
4. **Check the contract for the module you are extending.** If adding a channel, read `BaseChannel`. If adding a provider, read `Provider` ABC in `providers/provider.py`. If adding a tool, read `ToolGuardMixin` in `agents/tool_guard_mixin.py`.

## 2. Decide the Correct Placement

Place new code in the right layer — do not invent new top-level packages:

| What you are adding | Where it goes |
|---|---|
| New LLM provider adapter | `src/openspider/providers/<name>_provider.py` |
| New channel (Slack, Discord, etc.) | `src/openspider/app/channels/<name>/channel.py` inheriting `BaseChannel` |
| New agent tool | `src/openspider/agents/tools/` |
| New FastAPI router | `src/openspider/app/routers/` |
| New background job / cron | `src/openspider/app/crons/` |
| New Pydantic schema | Closest domain module (`plan/`, `agents/schema.py`, `config/`) |
| New env var constant | `src/openspider/constant.py` via `EnvVarLoader` with `OPENSPIDER_` prefix |
| New security rule | `src/openspider/security/tool_guard/rules/signatures/<rule>.yaml` |
| New skill | `src/openspider/agents/skills/<name>-en/SKILL.md` (+ `-zh/` sibling) |

## 3. Validate Imports Before Finalising

After writing new code:

1. **Verify every import resolves.** Cross-check that every imported name is exported from its source module. Use `grep_search` on the import path if uncertain.
2. **Use the project's import style:**
   - Internal absolute imports: `from openspider.app.channels.base import BaseChannel`
   - Avoid star imports (`from module import *`)
   - Third-party packages must already be listed in `pyproject.toml`; add them there if new
3. **Check `__init__.py` re-exports.** If a symbol must be public, expose it via the package's `__init__.py`.
4. **Run `get_errors`** on every edited file after making changes to catch type errors and unresolved imports before committing.

## 4. Follow Project Conventions

- **Async-first**: all I/O functions must be `async def`. Never use blocking calls (`requests.get`, `time.sleep`) inside async code.
- **Pydantic models**: use `BaseModel` with `model_validate()` for all structured data crossing module boundaries. No plain dicts as public API.
- **Env vars**: new constants go into `constant.py` using `EnvVarLoader` with `OPENSPIDER_*` prefix and a `QWENPAW_*` fallback where backward-compat is needed.
- **Security gate**: any new tool that executes external commands or accesses external systems **must** be registered with `ToolGuardMixin`. Do not bypass the approval gate.
- **All new features go into `src/openspider/`**. Never touch `src/qwenpaw/` unless explicitly asked.
- **No silent state mutation**: runner and workspace state changes must go through the defined lock/Future pattern; never mutate shared state outside an `asyncio.Lock`.

## 5. Logical Reasoning Checklist

Before finalising any implementation, answer these questions explicitly:

- [ ] Does this change duplicate something that already exists?
- [ ] Is this placed in the correct architectural layer?
- [ ] Do all imports resolve and match the project's import style?
- [ ] Are all I/O operations async?
- [ ] Does any new tool or external call pass through `ToolGuardMixin`?
- [ ] Are new env vars using `OPENSPIDER_*` prefix and registered in `constant.py`?
- [ ] Have I run `get_errors` on all modified files?
- [ ] Does the change require a corresponding test in `tests/unit/` or `tests/contract/`?

## 6. File Creation Rules

When creating a new file:

- Match the naming convention of siblings in the same directory (e.g., `<name>_provider.py`, `<name>_channel.py`).
- Include the module-level `__init__.py` export if the symbol is meant to be public.
- Never create top-level files outside the established directory tree without explicit approval.
- New Python files must start with any required module-level `from __future__ import annotations` if type-hinting requires it, followed by stdlib → third-party → internal imports in that order.
