# -*- coding: utf-8 -*-
"""Shared connection-state management for the OpenSpider CLI.

Stores the active server URL in ``~/.openspider/connection.json`` so
that other CLI commands can decide whether to use a local agent runtime
or route through a remote server.

Usage::

    from openspider.cli.connection import is_connected, get_base_url

    if is_connected():
        _via_server(get_base_url())
    else:
        _via_local()
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..constant import WORKING_DIR

CONNECTION_FILE = "connection.json"


class ConnectionInfo(BaseModel):
    """Serialised form of an active server connection."""

    url: str = ""
    """Server base URL (e.g. ``http://192.168.1.100:8088``)."""

    connected_at: str = ""
    """ISO-8601 UTC timestamp of when the connection was established."""

    agent_id: str = "default"
    """Default agent ID to use when talking to the server."""


# ------------------------------------------------------------------
# File I/O
# ------------------------------------------------------------------


def _connection_path() -> Path:
    """Return the absolute path to ``connection.json``."""
    return WORKING_DIR / CONNECTION_FILE


def get_connection() -> Optional[ConnectionInfo]:
    """Return the current connection info, or ``None``."""
    path = _connection_path()
    if not path.exists():
        return None
    try:
        return ConnectionInfo.model_validate_json(
            path.read_text(encoding="utf-8"),
        )
    except Exception:
        return None


def set_connection(url: str, agent_id: str = "default") -> ConnectionInfo:
    """Store a new connection and return its info."""
    info = ConnectionInfo(
        url=url.rstrip("/"),
        connected_at=datetime.now(timezone.utc).isoformat(),
        agent_id=agent_id,
    )
    _connection_path().parent.mkdir(parents=True, exist_ok=True)
    _connection_path().write_text(
        info.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return info


def clear_connection() -> None:
    """Remove any stored connection info."""
    path = _connection_path()
    if path.exists():
        path.unlink()


# ------------------------------------------------------------------
# Convenience queries
# ------------------------------------------------------------------


def is_connected() -> bool:
    """Return ``True`` if a server connection is currently stored."""
    conn = get_connection()
    return conn is not None and bool(conn.url)


def get_base_url() -> str | None:
    """Return the stored server URL, or ``None``."""
    conn = get_connection()
    return conn.url if conn else None


def get_connected_agent_id() -> str:
    """Return the agent ID from the stored connection, defaulting to ``"default"``."""
    conn = get_connection()
    return conn.agent_id if conn else "default"
