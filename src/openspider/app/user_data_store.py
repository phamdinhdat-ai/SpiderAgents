# -*- coding: utf-8 -*-
"""User-scoped data store backed by SQLite.

Replaces agent-scoped ``agent.json`` fields (MCP, knowledge registry)
with per-user storage so that switching agents does not change the
user's MCP servers, knowledge documents, or settings.

Database location: ``{WORKING_DIR}/user_data/user_data.db``

Tables
------
* **user_mcp_servers** — MCP client configs owned by a user.
* **user_knowledge_documents** — Knowledge document registry per user.
* **user_settings** — Free-form key-value settings per user.

All write operations use a single WAL-mode connection serialised through
an ``asyncio.Lock`` so they are safe for concurrent async tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..constant import WORKING_DIR

logger = logging.getLogger(__name__)

DB_DIR = WORKING_DIR / "user_data"
DB_PATH = DB_DIR / "user_data.db"

# ---------------------------------------------------------------------------
# Schema (kept in sync via _migrate on every start)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_mcp_servers (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    enabled         INTEGER DEFAULT 1,
    transport       TEXT DEFAULT 'stdio',
    url             TEXT DEFAULT '',
    headers         TEXT DEFAULT '{}',
    command         TEXT DEFAULT '',
    args            TEXT DEFAULT '[]',
    env             TEXT DEFAULT '{}',
    cwd             TEXT DEFAULT '',
    created_at      TEXT,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_mcp_username
    ON user_mcp_servers(username);

CREATE TABLE IF NOT EXISTS user_knowledge_documents (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL,
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    kb_name         TEXT DEFAULT 'default',
    mime_type       TEXT,
    size            INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pending',
    chunk_count     INTEGER DEFAULT 0,
    error_message   TEXT,
    owner           TEXT,
    scope           TEXT DEFAULT 'private',
    shared_with     TEXT DEFAULT '',
    content_hash    TEXT DEFAULT '',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_kb_username
    ON user_knowledge_documents(username);

CREATE INDEX IF NOT EXISTS idx_kb_content_hash
    ON user_knowledge_documents(username, content_hash, filename);

CREATE TABLE IF NOT EXISTS user_settings (
    username        TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           TEXT DEFAULT '',
    updated_at      TEXT,
    PRIMARY KEY (username, key)
);

CREATE INDEX IF NOT EXISTS idx_settings_username
    ON user_settings(username);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class UserDataStore:
    """Singleton-style access to the per-user SQLite store.

    Instantiated once at application startup and attached to
    ``app.state.user_data_store``.
    """

    def __init__(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the database and ensure schema is up to date."""
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        logger.info("UserDataStore started: %s", DB_PATH)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("UserDataStore closed")

    # ------------------------------------------------------------------
    # MCP servers
    # ------------------------------------------------------------------

    async def list_mcp_servers(self, username: str) -> list[dict[str, Any]]:
        """Return all MCP server configs for *username*."""
        return await self._run(
            "SELECT * FROM user_mcp_servers WHERE username=? ORDER BY name",
            (username,),
            many=True,
        )

    async def get_mcp_server(
        self, username: str, server_id: str,
    ) -> dict[str, Any] | None:
        """Get a single MCP server by id (must belong to *username*)."""
        return await self._run(
            "SELECT * FROM user_mcp_servers WHERE id=? AND username=?",
            (server_id, username),
        )

    async def save_mcp_server(
        self, username: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update an MCP server config. Returns the stored row."""
        now = datetime.now(timezone.utc).isoformat()
        data["username"] = username
        data.setdefault("description", "")
        data.setdefault("enabled", 1)
        data.setdefault("transport", "stdio")
        data.setdefault("url", "")
        data.setdefault("headers", "{}")
        data.setdefault("command", "")
        data.setdefault("args", "[]")
        data.setdefault("env", "{}")
        data.setdefault("cwd", "")
        data["updated_at"] = now

        existing = await self.get_mcp_server(username, data["id"])
        if existing:
            await self._run(
                """UPDATE user_mcp_servers
                   SET name=?, description=?, enabled=?, transport=?,
                       url=?, headers=?, command=?, args=?, env=?,
                       cwd=?, updated_at=?
                   WHERE id=? AND username=?""",
                (
                    data["name"], data["description"], data["enabled"],
                    data["transport"], data["url"], data["headers"],
                    data["command"], data["args"], data["env"],
                    data["cwd"], now, data["id"], username,
                ),
            )
        else:
            data["created_at"] = now
            await self._run(
                """INSERT INTO user_mcp_servers
                   (id, username, name, description, enabled, transport,
                    url, headers, command, args, env, cwd, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data["id"], username, data["name"], data["description"],
                    data["enabled"], data["transport"], data["url"],
                    data["headers"], data["command"], data["args"],
                    data["env"], data["cwd"], data["created_at"],
                    data["updated_at"],
                ),
            )
        return await self.get_mcp_server(username, data["id"]) or data

    async def delete_mcp_server(self, username: str, server_id: str) -> bool:
        """Delete an MCP server. Returns True if a row was removed."""
        async with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_mcp_servers WHERE id=? AND username=?",
                (server_id, username),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Knowledge documents
    # ------------------------------------------------------------------

    async def list_knowledge_documents(
        self,
        username: str,
        kb_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return knowledge documents for *username*, optionally filtered."""
        if kb_name:
            rows = await self._run(
                """SELECT * FROM user_knowledge_documents
                   WHERE username=? AND kb_name=?
                   ORDER BY created_at DESC""",
                (username, kb_name),
                many=True,
            )
        else:
            rows = await self._run(
                """SELECT * FROM user_knowledge_documents
                   WHERE username=?
                   ORDER BY created_at DESC""",
                (username,),
                many=True,
            )
        return rows

    async def get_knowledge_document(
        self, username: str, doc_id: str,
    ) -> dict[str, Any] | None:
        """Get a single knowledge document."""
        return await self._run(
            "SELECT * FROM user_knowledge_documents WHERE id=? AND username=?",
            (doc_id, username),
        )

    async def save_knowledge_document(
        self, username: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update a knowledge document record."""
        now = datetime.now(timezone.utc).isoformat()
        data["username"] = username
        data.setdefault("filename", "")
        data.setdefault("file_path", "")
        data.setdefault("kb_name", "default")
        data.setdefault("mime_type", "")
        data.setdefault("size", 0)
        data.setdefault("status", "pending")
        data.setdefault("chunk_count", 0)
        data.setdefault("error_message", "")
        data.setdefault("owner", username)
        data.setdefault("scope", "private")
        data.setdefault("shared_with", "")
        data.setdefault("content_hash", "")
        data.setdefault("metadata", "{}")
        data["updated_at"] = now

        existing = await self.get_knowledge_document(username, data["id"])
        if existing:
            await self._run(
                """UPDATE user_knowledge_documents
                   SET filename=?, file_path=?, kb_name=?, mime_type=?,
                       size=?, status=?, chunk_count=?, error_message=?,
                       owner=?, scope=?, shared_with=?, content_hash=?,
                       metadata=?, updated_at=?
                   WHERE id=? AND username=?""",
                (
                    data["filename"], data["file_path"], data["kb_name"],
                    data["mime_type"], data["size"], data["status"],
                    data["chunk_count"], data["error_message"],
                    data["owner"], data["scope"], data["shared_with"],
                    data["content_hash"], data["metadata"],
                    now, data["id"], username,
                ),
            )
        else:
            data["created_at"] = now
            await self._run(
                """INSERT INTO user_knowledge_documents
                   (id, username, filename, file_path, kb_name, mime_type,
                    size, status, chunk_count, error_message, owner, scope,
                    shared_with, content_hash, metadata, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data["id"], username, data["filename"], data["file_path"],
                    data["kb_name"], data["mime_type"], data["size"],
                    data["status"], data["chunk_count"],
                    data["error_message"], data["owner"], data["scope"],
                    data["shared_with"], data["content_hash"],
                    data["metadata"], data["created_at"], data["updated_at"],
                ),
            )
        return await self.get_knowledge_document(username, data["id"]) or data

    async def delete_knowledge_document(
        self, username: str, doc_id: str,
    ) -> bool:
        """Delete a knowledge document record."""
        async with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_knowledge_documents WHERE id=? AND username=?",
                (doc_id, username),
            )
            self._conn.commit()
            return cur.rowcount > 0

    async def find_duplicate_document(
        self,
        username: str,
        filename: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """Check if a document with the same hash and filename already exists.

        Returns the existing document dict or ``None``.
        """
        return await self._run(
            """SELECT * FROM user_knowledge_documents
               WHERE username=? AND content_hash=? AND filename=? AND status='ready'
               LIMIT 1""",
            (username, content_hash, filename),
        )

    async def count_knowledge_documents(
        self,
        username: str,
        kb_name: str = "default",
    ) -> int:
        """Return the number of knowledge documents for a user/KB."""
        row = await self._run(
            """SELECT COUNT(*) as cnt FROM user_knowledge_documents
               WHERE username=? AND kb_name=?""",
            (username, kb_name),
        )
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # User settings (key-value)
    # ------------------------------------------------------------------

    async def get_setting(self, username: str, key: str) -> str | None:
        """Read a single user setting."""
        row = await self._run(
            "SELECT value FROM user_settings WHERE username=? AND key=?",
            (username, key),
        )
        return row["value"] if row else None

    async def set_setting(self, username: str, key: str, value: str) -> None:
        """Write a user setting (insert or update)."""
        now = datetime.now(timezone.utc).isoformat()
        await self._run(
            """INSERT OR REPLACE INTO user_settings (username, key, value, updated_at)
               VALUES (?,?,?,?)""",
            (username, key, value, now),
        )

    async def delete_setting(self, username: str, key: str) -> bool:
        """Delete a user setting. Returns True if a row was removed."""
        async with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_settings WHERE username=? AND key=?",
                (username, key),
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Content hashing utility
    # ------------------------------------------------------------------

    @staticmethod
    def hash_file(file_path: Path) -> str:
        """Compute SHA-256 hex digest of a file's contents."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def hash_content(content: bytes | str) -> str:
        """Compute SHA-256 hex digest of an in-memory string or bytes."""
        sha = hashlib.sha256()
        if isinstance(content, str):
            sha.update(content.encode("utf-8"))
        else:
            sha.update(content)
        return sha.hexdigest()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(
        self,
        sql: str,
        params: tuple = (),
        *,
        many: bool = False,
    ) -> Any:
        """Execute *sql* on the background thread and return the result."""
        return await asyncio.to_thread(self._execute, sql, params, many)

    def _execute(
        self,
        sql: str,
        params: tuple,
        many: bool,
    ) -> Any:
        """Synchronous execute under the async lock (called via to_thread)."""
        if self._conn is None:
            raise RuntimeError("UserDataStore not started")
        cur = self._conn.execute(sql, params)
        if many:
            rows = cur.fetchall()
            return [_row_to_dict(r) for r in rows]
        row = cur.fetchone()
        if row is None:
            return None
        # For non-SELECT statements, return None after commit
        if not sql.lstrip().upper().startswith(("SELECT", "PRAGMA")):
            self._conn.commit()
            return None
        return _row_to_dict(row)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict, decoding JSON fields.

    Fields whose names suggest JSON content (``headers``, ``args``, ``env``,
    ``shared_with``, ``metadata``) are parsed if they are non-empty strings.
    """
    d = dict(row)
    json_fields = {"headers", "args", "env", "shared_with", "metadata"}
    for field in json_fields.intersection(d):
        raw = d[field]
        if isinstance(raw, str) and raw.strip():
            try:
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass  # keep as string
    return d
