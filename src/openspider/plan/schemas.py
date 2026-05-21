# -*- coding: utf-8 -*-
"""Pydantic response schemas for plan API endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Valid state transitions: maps a current state to the set of states it
# may legally transition into.  Used by the model_validator below so that
# callers that supply both ``prev_state`` and ``state`` are checked.
_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "todo": frozenset({"in_progress", "abandoned"}),
    "in_progress": frozenset({"done", "abandoned", "todo"}),
    "done": frozenset(),       # terminal — no further transitions
    "abandoned": frozenset(),  # terminal — no further transitions
}


class SubTaskResponse(BaseModel):
    """A single subtask in the plan response."""

    name: str
    description: str
    expected_outcome: str
    outcome: str | None = None
    state: Literal["todo", "in_progress", "done", "abandoned"] = "todo"
    prev_state: str | None = Field(
        default=None,
        exclude=True,
        description="Previous state — used only for transition validation, "
        "not serialised in API responses.",
    )
    created_at: str | None = None
    finished_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _check_state_transition(cls, values: Any) -> Any:
        """Reject illegal state transitions when prev_state is supplied."""
        if not isinstance(values, dict):
            return values
        prev = values.get("prev_state")
        current = values.get("state")
        if prev is not None and current is not None and prev != current:
            allowed = _VALID_TRANSITIONS.get(prev)
            if allowed is not None and current not in allowed:
                raise ValueError(
                    f"Invalid subtask state transition: "
                    f"{prev!r} → {current!r}. "
                    f"Allowed: {sorted(allowed) or 'none (terminal state)'}",
                )
        return values


class PlanStateResponse(BaseModel):
    """Top-level plan state returned by ``GET /plan/current``."""

    id: str
    name: str
    description: str
    expected_outcome: str
    state: Literal["todo", "in_progress", "done", "abandoned"] = "todo"
    prev_state: str | None = Field(
        default=None,
        exclude=True,
        description="Previous state — used only for transition validation, "
        "not serialised in API responses.",
    )
    subtasks: list[SubTaskResponse] = Field(default_factory=list)
    created_at: str | None = None
    finished_at: str | None = None
    outcome: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _check_state_transition(cls, values: Any) -> Any:
        """Reject illegal state transitions when prev_state is supplied."""
        if not isinstance(values, dict):
            return values
        prev = values.get("prev_state")
        current = values.get("state")
        if prev is not None and current is not None and prev != current:
            allowed = _VALID_TRANSITIONS.get(prev)
            if allowed is not None and current not in allowed:
                raise ValueError(
                    f"Invalid plan state transition: "
                    f"{prev!r} → {current!r}. "
                    f"Allowed: {sorted(allowed) or 'none (terminal state)'}",
                )
        return values


class PlanConfigResponse(BaseModel):
    """Plan configuration returned/accepted by config endpoints."""

    enabled: bool = False


def plan_to_response(plan) -> PlanStateResponse:
    """Convert an AgentScope ``Plan`` object to a ``PlanStateResponse``."""
    subtasks = [
        SubTaskResponse(
            name=st.name,
            description=st.description,
            expected_outcome=st.expected_outcome,
            outcome=st.outcome,
            state=st.state,
            created_at=st.created_at,
            finished_at=st.finished_at,
        )
        for st in plan.subtasks
    ]
    return PlanStateResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        expected_outcome=plan.expected_outcome,
        state=plan.state,
        subtasks=subtasks,
        created_at=plan.created_at,
        finished_at=plan.finished_at,
        outcome=plan.outcome,
    )
