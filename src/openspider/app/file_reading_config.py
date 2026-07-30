# -*- coding: utf-8 -*-
"""In-memory store for file reading enabled/disabled status per session.

Controls whether agent tools are allowed to read specific files
within a chat session. Default: all files are enabled (readable).
"""
from __future__ import annotations

import asyncio
from typing import Set

# session_id -> set of disabled file paths
_configs: dict[str, Set[str]] = {}
_lock = asyncio.Lock()


async def set_file_enabled(
    session_id: str,
    file_path: str,
    enabled: bool,
) -> None:
    """Enable or disable reading for a file in a session."""
    if not session_id or not file_path:
        return
    async with _lock:
        disabled = _configs.setdefault(session_id, set())
        if enabled:
            disabled.discard(file_path)
            # Clean up empty session entries
            if not disabled:
                del _configs[session_id]
        else:
            disabled.add(file_path)


async def get_disabled_files(session_id: str) -> Set[str]:
    """Return the set of disabled file paths for a session."""
    if not session_id:
        return set()
    async with _lock:
        return set(_configs.get(session_id, set()))


async def is_file_enabled(session_id: str, file_path: str) -> bool:
    """Check if a file is enabled for reading (default: True)."""
    if not session_id or not file_path:
        return True
    async with _lock:
        disabled = _configs.get(session_id, set())
        return file_path not in disabled


async def clear_session(session_id: str) -> None:
    """Clear all config for a session."""
    if not session_id:
        return
    async with _lock:
        _configs.pop(session_id, None)
