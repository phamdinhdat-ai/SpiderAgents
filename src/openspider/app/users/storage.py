# -*- coding: utf-8 -*-
"""Per-user directory scaffolding and config persistence."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiofiles

from ...constant import (
    get_user_config_path,
    get_user_files_dir,
    get_user_memory_dir,
    get_user_sessions_dir,
    get_user_storage_dir,
)
from .models import UserConfig

logger = logging.getLogger(__name__)

# Sentinel file written into a migrated session directory so the
# startup migration runs only once per workspace.
_MIGRATION_SENTINEL = ".user-migration-done"


class UserStorageManager:
    """Manages per-user directory creation and per-user config I/O.

    Usage::

        mgr = UserStorageManager()
        await mgr.ensure_user_dirs("alice", "default")
        config = await mgr.load_user_config("alice")
    """

    # ------------------------------------------------------------------
    # Directory scaffolding
    # ------------------------------------------------------------------

    async def ensure_user_dirs(
        self,
        username: str,
        agent_id: str = "default",
    ) -> None:
        """Create all per-user directories if they do not exist.

        Creates the user's root dir, workspace sessions dir, memory dir,
        and files dir.  Safe to call on every login — existing dirs are
        a no-op.

        Args:
            username: The authenticated username.
            agent_id: The agent identifier (usually ``"default"``).
        """
        dirs: list[Path] = [
            get_user_storage_dir(username),
            get_user_sessions_dir(username, agent_id),
            get_user_memory_dir(username, agent_id),
            get_user_files_dir(username),
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Per-user config (MCP, tools, plugins overlay)
    # ------------------------------------------------------------------

    async def load_user_config(self, username: str) -> UserConfig:
        """Load the per-user config overlay file.

        Returns an empty ``UserConfig`` when the file does not exist so
        callers always get a safe default.

        Args:
            username: The authenticated username.

        Returns:
            Parsed ``UserConfig`` (never ``None``).
        """
        path = get_user_config_path(username)
        if not path.is_file():
            return UserConfig()

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                raw = await f.read()
            return UserConfig.model_validate(json.loads(raw))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load user config %s: %s. Using defaults.",
                path,
                exc,
            )
            return UserConfig()

    async def save_user_config(
        self,
        username: str,
        config: UserConfig,
    ) -> None:
        """Atomically persist the per-user config overlay.

        Args:
            username: The authenticated username.
            config: The config to save.
        """
        path = get_user_config_path(username)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp = path.with_suffix(path.suffix + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(
                config.model_dump_json(indent=2, exclude_none=True),
            )
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    # Session directory resolution for SafeJSONSession
    # ------------------------------------------------------------------

    def resolve_session_save_dir(
        self,
        username: Optional[str],
        agent_id: str,
        legacy_workspace_dir: Path,
    ) -> str:
        """Return the session save-dir for a given user + agent.

        When *username* is ``None`` or empty (auth disabled), returns
        the legacy ``workspace_dir / "sessions"`` path so existing
        deployments are unaffected.

        When *username* is provided, returns the user-scoped path and
        ensures the directory exists.

        Args:
            username: Authenticated username, or ``None`` when auth is off.
            agent_id: The agent identifier.
            legacy_workspace_dir: Fallback workspace dir for legacy mode.

        Returns:
            Absolute path string for the session directory.
        """
        if not username:
            return str(legacy_workspace_dir / "sessions")

        user_dir = get_user_sessions_dir(username, agent_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        return str(user_dir)

    # ------------------------------------------------------------------
    # Startup migration: workspace sessions → user dirs
    # ------------------------------------------------------------------

    async def migrate_workspace_sessions_to_user_dirs(
        self,
        workspace_dir: Path,
        agent_id: str,
    ) -> int:
        """One-time migration of legacy session files into user dirs.

        Scans ``workspace_dir / sessions /`` for ``*.json`` files whose
        filenames match the ``{user_id}_{session_id}.json`` pattern and
        **copies** them into the appropriate per-user directory.

        The original files are left in place so the migration is
        non-destructive.  A ``.user-migration-done`` sentinel file is
        written afterward to skip subsequent startups.

        Args:
            workspace_dir: The agent workspace directory.
            agent_id: The agent identifier.

        Returns:
            Number of session files migrated, or ``-1`` if already done.
        """
        sessions_dir = workspace_dir / "sessions"
        sentinel = sessions_dir / _MIGRATION_SENTINEL

        if sentinel.exists():
            logger.debug(
                "User-session migration already done for %s.",
                workspace_dir,
            )
            return -1

        if not sessions_dir.is_dir():
            sessions_dir.mkdir(parents=True, exist_ok=True)
            sentinel.touch()
            return 0

        count = 0
        try:
            entries = list(sessions_dir.glob("*.json"))
        except OSError:
            entries = []

        for entry in entries:
            stem = entry.stem  # "safe_uid_safe_sid"
            # Filenames use ``_`` as the separator between safe_uid and
            # safe_sid (from SafeJSONSession._get_save_path).  Split on
            # the first ``_`` that appears after a plausible user-id
            # prefix (heuristic: user_id is the first segment before any
            # sanitized ``--`` that marks channel prefixes).
            parts = stem.split("_", 1)
            if len(parts) < 2:
                continue  # session with no user_id segment — skip

            safe_uid, _safe_sid = parts
            # We cannot reverse the sanitization, but we can still
            # store under the sanitized name.  The real username mapping
            # lives in auth.json, not in the session filename.
            # Therefore we store under a generic "legacy" user bucket
            # within the users dir, keyed by the safe_uid.
            dest_dir = get_user_storage_dir(
                safe_uid,
            ) / "workspaces" / agent_id / "sessions"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / entry.name

            if not dest.exists():
                try:
                    import shutil

                    shutil.copy2(str(entry), str(dest))
                    count += 1
                except OSError as exc:
                    logger.warning(
                        "Failed to migrate session %s → %s: %s",
                        entry,
                        dest,
                        exc,
                    )

        sentinel.touch()
        if count:
            logger.info(
                "Migrated %d legacy session files to user dirs for %s.",
                count,
                workspace_dir,
            )
        return count

    async def list_user_session_dirs(
        self,
    ) -> list[tuple[str, str, Path]]:
        """Scan ``USERS_DIR`` for user/agent/sessions directories.

        Returns:
            List of ``(username_hash, agent_id, sessions_dir)`` tuples.
        """
        if not get_user_storage_dir("").parent.is_dir():
            return []

        result: list[tuple[str, str, Path]] = []
        usr_root = get_user_storage_dir("").parent  # USERS_DIR itself
        try:
            for user_hash_dir in usr_root.iterdir():
                if not user_hash_dir.is_dir():
                    continue
                workspaces_dir = user_hash_dir / "workspaces"
                if not workspaces_dir.is_dir():
                    continue
                for agent_dir in workspaces_dir.iterdir():
                    if not agent_dir.is_dir():
                        continue
                    sessions_dir = agent_dir / "sessions"
                    if sessions_dir.is_dir():
                        result.append(
                            (user_hash_dir.name, agent_dir.name, sessions_dir),
                        )
        except OSError:
            pass
        return result
