# -*- coding: utf-8 -*-
"""Lightweight file snapshot manager for agent rollback.

Before destructive tool calls (write_file, edit_file, execute_shell_command),
a snapshot of affected file hashes is recorded.  If a subsequent verification
detects a regression, the snapshot can be used to restore previous state.

Snapshots are hash-based (SHA-256), not full-file copies, to minimize
storage overhead.  Only when rollback is needed are files restored from
git (if tracked) or temp backups.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..constant import (
    SNAPSHOT_ENABLED,
    SNAPSHOT_MAX_BACKUP_SIZE_MB,
)

logger = logging.getLogger(__name__)

# Tools considered "destructive" — trigger snapshot before execution
_DESTRUCTIVE_TOOLS = frozenset({
    "write_file",
    "edit_file",
    "append_file",
    "execute_shell_command",
})


def _compute_hash(file_path: Path) -> str | None:
    """Compute SHA-256 hash of a file.  Returns None if file doesn't exist."""
    try:
        if not file_path.is_file():
            return None
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        return None


class SnapshotManager:
    """Manages pre-execution file snapshots for rollback.

    Usage::

        snap = SnapshotManager(workspace_dir="/path/to/workspace")
        # Before destructive tool:
        affected = snap.snapshot(tool_name, tool_input)
        # On regression:
        await snap.rollback(affected)
    """

    def __init__(
        self,
        workspace_dir: str | Path | None = None,
        enabled: bool | None = None,
        max_backup_mb: int | None = None,
    ) -> None:
        self._enabled = SNAPSHOT_ENABLED if enabled is None else enabled
        self._max_backup_mb = max_backup_mb or SNAPSHOT_MAX_BACKUP_SIZE_MB
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        # Snapshot log: list of {timestamp, tool, paths: {path: hash}}
        self._history: list[dict[str, Any]] = []
        # Temp backup dir for rollback
        self._backup_dir: Path | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._history.clear()

    def snapshot(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None,
    ) -> dict[str, str]:
        """Record pre-execution state of files affected by this tool.

        Returns a dict of ``{file_path: file_hash}`` for affected files.
        Empty dict if snapshot is disabled or no files are affected.
        """
        if not self._enabled or tool_name not in _DESTRUCTIVE_TOOLS:
            return {}

        paths = self._resolve_affected_paths(tool_input)
        if not paths:
            return {}

        snap_entry: dict[str, str] = {}
        for p in paths:
            h = _compute_hash(p)
            snap_entry[str(p)] = h or "(new file)"

        self._history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "paths": snap_entry,
        })

        # Prune old history
        if len(self._history) > 100:
            self._history = self._history[-50:]

        logger.debug(
            "Snapshot: recorded %d file(s) before '%s'",
            len(snap_entry),
            tool_name,
        )
        return snap_entry

    async def rollback(
        self,
        affected_paths: dict[str, str],
    ) -> dict[str, bool]:
        """Attempt to restore files to their pre-execution state.

        For each file:
        - If tracked by git, restores from git.
        - Otherwise, restores from temp backup (if one was made).

        Returns a dict of ``{file_path: success_bool}``.
        """
        results: dict[str, bool] = {}

        for path_str, expected_hash in affected_paths.items():
            file_path = Path(path_str)
            if not file_path.exists() and expected_hash == "(new file)":
                # File was newly created — nothing to rollback
                results[path_str] = True
                continue

            try:
                # Try git restore first
                restored = await self._git_restore(file_path)
                if restored:
                    results[path_str] = True
                    logger.info(
                        "Rollback: restored %s from git",
                        file_path,
                    )
                    continue

                # Try temp backup
                restored = await self._backup_restore(file_path, expected_hash)
                if restored:
                    results[path_str] = True
                    logger.info(
                        "Rollback: restored %s from backup",
                        file_path,
                    )
                    continue

                results[path_str] = False
                logger.warning(
                    "Rollback: could not restore %s (not in git, no backup)",
                    file_path,
                )
            except Exception as exc:
                results[path_str] = False
                logger.error(
                    "Rollback: error restoring %s: %s",
                    file_path,
                    exc,
                )

        return results

    async def backup_before_change(self, file_path: Path) -> bool:
        """Create a temp backup of a file before it's modified.

        Returns True if backup succeeded.
        """
        if not self._enabled or not file_path.is_file():
            return False

        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self._max_backup_mb:
                logger.debug(
                    "Snapshot: skipping backup of %s (%.1f MB > %d MB limit)",
                    file_path,
                    file_size_mb,
                    self._max_backup_mb,
                )
                return False

            if self._backup_dir is None:
                self._backup_dir = Path(tempfile.mkdtemp(prefix="openspider_snap_"))

            backup_path = self._backup_dir / file_path.name
            shutil.copy2(file_path, backup_path)
            logger.debug("Snapshot: backed up %s", file_path)
            return True
        except OSError as exc:
            logger.warning("Snapshot: backup failed for %s: %s", file_path, exc)
            return False

    async def cleanup(self) -> None:
        """Remove temp backup directory."""
        if self._backup_dir and self._backup_dir.exists():
            try:
                shutil.rmtree(self._backup_dir)
                logger.debug("Snapshot: cleaned up backup dir %s", self._backup_dir)
            except OSError as exc:
                logger.warning("Snapshot: cleanup failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_affected_paths(
        self,
        tool_input: dict[str, Any] | None,
    ) -> list[Path]:
        """Resolve which files are affected by this tool call."""
        if not tool_input or not self._workspace_dir:
            return []

        file_path_str = (
            tool_input.get("filePath")
            or tool_input.get("file_path")
            or tool_input.get("path")
            or ""
        )
        if not file_path_str:
            return []

        file_path = Path(file_path_str)
        if not file_path.is_absolute():
            file_path = self._workspace_dir / file_path

        if file_path.exists():
            return [file_path]
        return []

    async def _git_restore(self, file_path: Path) -> bool:
        """Attempt to restore a file from git."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                "--",
                str(file_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=self._workspace_dir or file_path.parent,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    async def _backup_restore(
        self,
        file_path: Path,
        expected_hash: str,
    ) -> bool:
        """Restore a file from temp backup."""
        if not self._backup_dir:
            return False
        backup_path = self._backup_dir / file_path.name
        if not backup_path.is_file():
            return False
        try:
            shutil.copy2(backup_path, file_path)
            return True
        except OSError:
            return False
