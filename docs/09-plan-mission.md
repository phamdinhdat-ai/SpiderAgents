# 09 — Plan & Mission Modes

> Plan mode: structured task decomposition with gated tools.  
> Mission mode: two-phase code-controlled iteration loop.

---

## Plan Mode

### Purpose

Structured task decomposition with gated tool access. Agent must plan before acting.

### State Machine

```
todo ──► in_progress ──► done
  │                        │
  └──────► abandoned ◄─────┘
```

Validated by Pydantic `model_validator` on `SubTaskResponse`.

### Schemas

```python
class SubTaskResponse(BaseModel):
    name: str
    description: str
    expected_outcome: str
    outcome: str | None
    state: Literal["todo", "in_progress", "done", "abandoned"]
    created_at: datetime
    updated_at: datetime

class PlanStateResponse(BaseModel):
    plan_id: str
    title: str
    description: str
    subtasks: list[SubTaskResponse]
    current_subtask_index: int
```

### Tool Gate

```
Agent enters plan mode (/plan <desc>)
    │
    ▼
Plan tool gate ACTIVE
    │  Only create_plan tool available
    ▼
Agent creates plan (SubTask list)
    │
    ▼
User approves plan
    │
    ▼
Plan tool gate RELEASED
    │  All tools available
    ▼
Agent executes subtasks, updating state
```

### Hint System

`SimplePlanToHint` replaces AgentScope's default:
- **Confirmation step**: Agent must present plan, wait for user approval
- **Scoped `no_plan` hint**: Only when runner sets `_plan_tool_gate`
- **Compact plan text**: Completed subtask outcomes dropped

### Plan SSE Streaming

```python
# Frontend subscribes to plan updates
GET /api/plan/stream
    → SSE: { type: "plan_update", plan: {...}, session_id: "..." }
```

---

## Mission Mode

### Two-Phase Execution

```
Phase 1 — PRD
    ├── Agent explores codebase
    ├── Writes prd.json with user stories
    └── Full tool access

Phase 2 — Execution
    ├── Implementation tools DEACTIVATED (via Toolkit groups)
    ├── Engine reads prd.json
    ├── Checks passes on each story
    ├── Injects continuation messages
    └── Loops until all pass or max iterations
```

### PRD Schema

```json
{
    "userStories": [
        {
            "id": "US-1",
            "title": "...",
            "description": "...",
            "acceptanceCriteria": ["..."],
            "priority": "high",
            "passes": false
        }
    ]
}
```

### Toolkit Group Mechanism

```python
# Phase 2: Master agent becomes controller-only
# Implementation tools moved to "mission_impl" group and deactivated
toolkit.create_tool_group("mission_impl", ...)
for tool in ["edit_file", "browser_use", "desktop_screenshot"]:
    toolkit.tools[tool].group = "mission_impl"

# Deactivated for Phase 2
toolkit.update_tool_groups(["mission_impl"], active=False)
```

The master agent delegates ALL work to workers via:
```bash
openspider agents chat --background --task-id <id>
```

### Validation

`prd.json` is validated on every iteration:
- Must have `userStories` array (non-empty)
- Each story must have: `id`, `title`, `description`, `acceptanceCriteria`, `priority`
- `passes` flag tracked per story

### Completion

When all stories pass or max iterations reached:
- Generate completion summary with pass/fail counts
- Restore implementation tools
