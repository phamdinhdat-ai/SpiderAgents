# -*- coding: utf-8 -*-
"""Per-user data isolation, config overlay, and session tracking.

When auth is enabled, each authenticated user gets their own storage
space under ``USERS_DIR/<sha256(username)>/`` for sessions, memory,
files, and config overrides (MCP, tools, plugins).  Admin users can
view activity across all users via the :class:`UserSessionTracker`.

Public API
----------
- :func:`get_user_storage_dir` / :func:`get_user_sessions_dir` — path helpers
  (re-exported from ``openspider.constant``).
- :class:`UserStorageManager` — directory scaffolding and CRUD for
  per-user config and files.
- :class:`UserSessionTracker` — scans user directories to build
  audit/session-tracking data for admins.
"""

from __future__ import annotations

from .storage import UserStorageManager
from .tracker import UserSessionTracker

__all__ = [
    "UserStorageManager",
    "UserSessionTracker",
]
