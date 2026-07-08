# -*- coding: utf-8 -*-
"""Session tracker for admin monitoring — scans user directories."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
import orjson

from ...constant import get_user_storage_dir, USERS_DIR
from .storage import UserStorageManager
from .models import (
    AdminSessionsResponse,
    UserActivitySummary,
    UserSessionInfo,
)

logger = logging.getLogger(__name__)


class UserSessionTracker:
    """Scans per-user session directories to build admin dashboard data.

    Uses the same session-file reading pattern as
    :class:`openspider.agent_stats.service.AgentStatsService`.

    Usage::

        tracker = UserSessionTracker()
        summary = await tracker.get_all_users_summary(agent_id="default")
    """

    def __init__(self) -> None:
        self._storage = UserStorageManager()

    # ------------------------------------------------------------------
    # All-users summary (admin dashboard)
    # ------------------------------------------------------------------

    async def get_all_users_summary(
        self,
        agent_id: str = "default",
    ) -> AdminSessionsResponse:
        """Scan all user directories and build an aggregate summary.

        Args:
            agent_id: The agent identifier to scope sessions to.

        Returns:
            ``AdminSessionsResponse`` with per-user summaries.
        """
        users: list[UserActivitySummary] = []
        total_sessions = 0
        active_sessions = 0

        dir_tuples = await self._storage.list_user_session_dirs()

        for user_hash, agent, sessions_dir in dir_tuples:
            if agent != agent_id:
                continue
            user_summary = await self._build_user_summary(
                user_hash,
                sessions_dir,
            )
            if user_summary is not None:
                users.append(user_summary)
                total_sessions += user_summary.total_sessions
                active_sessions += user_summary.active_sessions

        # Sort by last_active descending
        users.sort(
            key=lambda u: u.last_active or "",
            reverse=True,
        )

        return AdminSessionsResponse(
            users=users,
            total_users=len(users),
            total_sessions=total_sessions,
            active_sessions=active_sessions,
        )

    # ------------------------------------------------------------------
    # Single-user sessions
    # ------------------------------------------------------------------

    async def get_user_sessions(
        self,
        username: str,
        agent_id: str = "default",
    ) -> list[UserSessionInfo]:
        """Return all sessions for a specific user.

        Args:
            username: The authenticated username (raw, not hashed).
            agent_id: The agent identifier.

        Returns:
            List of ``UserSessionInfo``, newest first.
        """
        user_dir = get_user_storage_dir(username)
        sessions_dir = (
            user_dir / "workspaces" / agent_id / "sessions"
        )
        if not sessions_dir.is_dir():
            return []

        sessions: list[UserSessionInfo] = []
        try:
            for entry in sorted(
                sessions_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            ):
                info = await self._read_session_info(entry)
                if info is not None:
                    sessions.append(info)
        except OSError:
            pass

        return sessions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_user_summary(
        self,
        user_hash: str,
        sessions_dir: Path,
    ) -> Optional[UserActivitySummary]:
        """Build a single user's activity summary from session files."""
        try:
            entries = list(sessions_dir.glob("*.json"))
        except OSError:
            return None

        total_sessions = 0
        active_count = 0
        total_messages = 0
        last_active = ""

        for entry in entries:
            info = await self._read_session_info(entry)
            if info is None:
                continue
            total_sessions += 1
            total_messages += info.message_count
            if info.status == "running":
                active_count += 1
            if info.last_active and (
                not last_active or info.last_active > last_active
            ):
                last_active = info.last_active

        return UserActivitySummary(
            username=user_hash,
            total_sessions=total_sessions,
            active_sessions=active_count,
            total_messages=total_messages,
            last_active=last_active,
        )

    async def _read_session_info(
        self,
        filepath: Path,
    ) -> Optional[UserSessionInfo]:
        """Extract high-level info from a single session JSON file.

        Returns ``None`` if the file cannot be read or has no messages.
        """
        try:
            async with aiofiles.open(
                filepath,
                "rb",
            ) as f:
                raw = await f.read()
            data = orjson.loads(raw)
        except (OSError, orjson.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        # Extract messages from agent memory
        memories = (
            data.get("agent", {})
            .get("memory", {})
            .get("memories")
        ) or data.get("agent", {}).get("memory", {}).get("content", [])
        if not memories:
            return None

        msg_count = len(memories)
        last_ts = ""
        for msg_item in reversed(memories):
            if isinstance(msg_item, list) and len(msg_item) > 0:
                msg_data = msg_item[0]
            elif isinstance(msg_item, dict):
                msg_data = msg_item
            else:
                continue
            if isinstance(msg_data, dict):
                ts = msg_data.get("timestamp")
                if ts:
                    last_ts = str(ts)
                    break

        # Determine status (heuristic: if last message is user → idle)
        status = "idle"
        if memories:
            last = memories[-1]
            if isinstance(last, list) and len(last) > 0:
                last_data = last[0]
            elif isinstance(last, dict):
                last_data = last
            else:
                last_data = {}
            if isinstance(last_data, dict):
                if last_data.get("role") == "user":
                    status = "idle"
                else:
                    status = "running"

        return UserSessionInfo(
            session_id=filepath.stem,
            channel="",
            last_active=last_ts,
            message_count=msg_count,
            status=status,
        )

    # ------------------------------------------------------------------
    # Force logout helpers
    # ------------------------------------------------------------------

    async def revoke_user_tokens(self, username: str) -> bool:
        """Revoke all tokens for a user by rotating the JWT secret.

        Delegates to :func:`openspider.app.auth.revoke_all_tokens`.
        """
        from ..auth import revoke_all_tokens as _revoke_all

        return _revoke_all()

    async def delete_user_session_file(
        self,
        username: str,
        session_id: str,
        agent_id: str = "default",
    ) -> bool:
        """Delete a single session file for a user.

        Args:
            username: The authenticated username (raw).
            session_id: The session identifier (filename stem).
            agent_id: The agent identifier.

        Returns:
            ``True`` if the file was deleted, ``False`` if not found.
        """
        from ...constant import get_user_sessions_dir

        sessions_dir = get_user_sessions_dir(username, agent_id)
        # session_id might contain chars that were already sanitized, so
        # search by glob
        import fnmatch

        try:
            for entry in sessions_dir.glob("*.json"):
                if fnmatch.fnmatch(entry.stem, session_id):
                    entry.unlink()
                    return True
        except OSError:
            pass
        return False
