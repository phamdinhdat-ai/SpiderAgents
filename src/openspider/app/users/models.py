# -*- coding: utf-8 -*-
"""Pydantic models for per-user data and admin session tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Per-user config overlay
# ---------------------------------------------------------------------------


class UserMCPClientOverride(BaseModel):
    """A single MCP client configuration that a user can enable/disable
    or customize independently of the workspace-level defaults."""

    name: str
    description: str = ""
    enabled: bool = True
    transport: str = "stdio"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str = ""


class UserToolsOverride(BaseModel):
    """Per-user tool preferences overlay."""

    enabled_tools: list[str] = Field(default_factory=list)
    """Tool names the user has explicitly enabled."""

    disabled_tools: list[str] = Field(default_factory=list)
    """Tool names the user has explicitly disabled.

    Disabled tools take precedence over enabled ones when there is
    a conflict.
    """


class UserConfig(BaseModel):
    """Per-user configuration overrides persisted to ``config.json``.

    This is an *additive overlay* on top of the workspace-level
    ``agent.json``.  Only fields the user customises need to appear;
    missing fields inherit workspace defaults.
    """

    mcp_clients: list[UserMCPClientOverride] = Field(default_factory=list)
    """MCP clients the user wants to add or override."""

    tools: UserToolsOverride | None = None
    """Per-user tool preferences (enable/disable list)."""

    extra: dict[str, Any] = Field(default_factory=dict)
    """Catch-all for future per-user settings."""


# ---------------------------------------------------------------------------
# Admin session tracking models
# ---------------------------------------------------------------------------


class UserSessionInfo(BaseModel):
    """A single session belonging to a user."""

    session_id: str
    channel: str = ""
    last_active: str = ""  # ISO-8601 timestamp of most recent message
    message_count: int = 0
    status: str = "idle"  # idle / running


class UserActivitySummary(BaseModel):
    """Aggregate summary for one user, shown in admin dashboard."""

    username: str
    role: str = "user"
    total_sessions: int = 0
    active_sessions: int = 0
    total_messages: int = 0
    last_active: str = ""  # ISO-8601 timestamp
    created_at: str = ""  # ISO-8601 timestamp (from auth.json user record)


class AdminSessionsResponse(BaseModel):
    """Response body for ``GET /auth/admin/sessions``."""

    users: list[UserActivitySummary] = Field(default_factory=list)
    total_users: int = 0
    total_sessions: int = 0
    active_sessions: int = 0


class AdminUserSessionsResponse(BaseModel):
    """Response body for ``GET /auth/admin/users/{username}/sessions``."""

    username: str
    sessions: list[UserSessionInfo] = Field(default_factory=list)
    total: int = 0
