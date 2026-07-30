# -*- coding: utf-8 -*-
"""In-memory store for agent file-creation events.

Bounded: at most _MAX_EVENTS kept; events older than _MAX_AGE_SECONDS
are dropped when reading.
"""
from __future__ import annotations

import asyncio
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

# session_id -> [file_event, ...]
_files: Dict[str, List[Dict[str, Any]]] = {}
_lock = asyncio.Lock()
_MAX_AGE_SECONDS = 600  # 10 min
_MAX_EVENTS_PER_SESSION = 200


async def append(
    session_id: str,
    file_path: str,
    tool_name: str,
    action: str,
    file_size: int = 0,
) -> None:
    """Append a file creation event for a session."""
    if not session_id or not file_path:
        return

    path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "text/plain"

    event: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "file_path": file_path,
        "file_name": path.name,
        "file_size": file_size,
        "tool_name": tool_name,
        "action": action,
        "created_at": time.time(),
        "mime_type": mime_type,
    }

    async with _lock:
        session_events = _files.setdefault(session_id, [])
        session_events.append(event)
        # Bound per-session event list
        if len(session_events) > _MAX_EVENTS_PER_SESSION:
            session_events[:] = session_events[-_MAX_EVENTS_PER_SESSION:]

        # Clean expired events
        _prune_expired_locked()


async def take(session_id: str) -> List[Dict[str, Any]]:
    """Return and remove all events for the session (consumed on read)."""
    if not session_id:
        return []
    async with _lock:
        _prune_expired_locked()
        events = _files.pop(session_id, [])
        return events


async def take_all() -> List[Dict[str, Any]]:
    """Return and remove all non-expired events from all sessions."""
    async with _lock:
        _prune_expired_locked()
        all_events: List[Dict[str, Any]] = []
        for session_events in _files.values():
            all_events.extend(session_events)
        _files.clear()
        return all_events


async def get_all(session_id: str) -> List[Dict[str, Any]]:
    """Return all events for a session without consuming them."""
    if not session_id:
        return []
    async with _lock:
        _prune_expired_locked()
        return list(_files.get(session_id, []))


async def get_active_sessions() -> List[str]:
    """Return list of session IDs that have events."""
    async with _lock:
        _prune_expired_locked()
        return [sid for sid, events in _files.items() if events]


async def clear_session(session_id: str) -> None:
    """Clear all events for a session."""
    if not session_id:
        return
    async with _lock:
        _files.pop(session_id, None)


async def remove_event(session_id: str, file_path: str) -> bool:
    """Remove a single file event from a session. Returns True if removed."""
    if not session_id or not file_path:
        return False
    async with _lock:
        events = _files.get(session_id, [])
        original_len = len(events)
        _files[session_id] = [e for e in events if e["file_path"] != file_path]
        if not _files[session_id]:
            del _files[session_id]
        return len(_files.get(session_id, [])) < original_len


def _prune_expired_locked() -> None:
    """Drop expired events in-place. Caller must hold _lock."""
    cutoff = time.time() - _MAX_AGE_SECONDS
    empty_sessions: List[str] = []
    for sid, events in _files.items():
        _files[sid] = [e for e in events if e["created_at"] >= cutoff]
        if not _files[sid]:
            empty_sessions.append(sid)
    for sid in empty_sessions:
        del _files[sid]
