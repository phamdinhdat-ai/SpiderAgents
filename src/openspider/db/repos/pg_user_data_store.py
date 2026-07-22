# -*- coding: utf-8 -*-
"""PostgreSQL-backed UserDataStore.

Drop-in replacement for :class:`openspider.app.user_data_store.UserDataStore`
that uses SQLAlchemy async sessions instead of sqlite3.

Same public API — callers (MCP router, knowledge router, settings
router) require zero changes.  All methods manage their own sessions
internally via the global ``_session_factory``.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from openspider.db.models import KnowledgeDocument, MCPServer, UserSetting

logger = logging.getLogger(__name__)


class PgUserDataStore:
    """PostgreSQL-backed per-user data store (MCP, knowledge, settings).

    Instantiated once at application startup and attached to
    ``app.state.user_data_store``.  Shares the same method signatures
    as the legacy :class:`UserDataStore`.
    """

    def __init__(self) -> None:
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """No-op — the PG engine is managed by DatabaseManager."""
        self._started = True
        logger.info("PgUserDataStore started.")

    async def close(self) -> None:
        """No-op."""
        self._started = False
        logger.info("PgUserDataStore closed.")

    # ------------------------------------------------------------------
    # Internal: session management
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session, committing on success."""
        from openspider.db.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            raise RuntimeError("Database not started")
        async with sf() as sess:
            yield sess
            await sess.commit()

    # ------------------------------------------------------------------
    # MCP servers
    # ------------------------------------------------------------------

    async def list_mcp_servers(self, username: str) -> list[dict[str, Any]]:
        """Return all MCP server configs for *username*."""
        async with self._session() as sess:
            result = await sess.execute(
                select(MCPServer)
                .where(MCPServer.username == username)
                .order_by(MCPServer.name),
            )
            return [_mcp_to_dict(r) for r in result.scalars().all()]

    async def get_mcp_server(
        self, username: str, server_id: str,
    ) -> dict[str, Any] | None:
        """Get a single MCP server by id."""
        async with self._session() as sess:
            result = await sess.execute(
                select(MCPServer).where(
                    MCPServer.id == server_id,
                    MCPServer.username == username,
                ),
            )
            row = result.scalar_one_or_none()
            return _mcp_to_dict(row) if row else None

    async def save_mcp_server(
        self, username: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update an MCP server config."""
        now = datetime.now(timezone.utc)

        values = {
            "id": data["id"],
            "username": username,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "enabled": data.get("enabled", True),
            "transport": data.get("transport", "stdio"),
            "url": data.get("url", ""),
            "headers": data.get("headers", {}),
            "command": data.get("command", ""),
            "args": data.get("args", []),
            "env": data.get("env", {}),
            "cwd": data.get("cwd", ""),
            "updated_at": now,
        }

        existing = await self.get_mcp_server(username, data["id"])
        async with self._session() as sess:
            if existing:
                stmt = pg_insert(MCPServer).values(
                    id=data["id"], **values,
                ).on_conflict_do_update(
                    index_elements=["id"],
                    set_=values,
                )
            else:
                values["created_at"] = now
                stmt = pg_insert(MCPServer).values(**values)
            await sess.execute(stmt)

        return await self.get_mcp_server(username, data["id"]) or data

    async def delete_mcp_server(
        self, username: str, server_id: str,
    ) -> bool:
        """Delete an MCP server. Returns True if a row was removed."""
        async with self._session() as sess:
            result = await sess.execute(
                select(MCPServer).where(
                    MCPServer.id == server_id,
                    MCPServer.username == username,
                ),
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await sess.delete(row)
            return True

    # ------------------------------------------------------------------
    # Knowledge documents
    # ------------------------------------------------------------------

    async def list_knowledge_documents(
        self,
        username: str,
        kb_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return knowledge documents for *username*."""
        async with self._session() as sess:
            stmt = select(KnowledgeDocument).where(
                KnowledgeDocument.username == username,
            )
            if kb_name:
                stmt = stmt.where(KnowledgeDocument.kb_name == kb_name)
            stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
            result = await sess.execute(stmt)
            return [_kb_to_dict(r) for r in result.scalars().all()]

    async def get_knowledge_document(
        self, username: str, doc_id: str,
    ) -> dict[str, Any] | None:
        """Get a single knowledge document."""
        async with self._session() as sess:
            result = await sess.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.username == username,
                ),
            )
            row = result.scalar_one_or_none()
            return _kb_to_dict(row) if row else None

    async def save_knowledge_document(
        self, username: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert or update a knowledge document record."""
        now = datetime.now(timezone.utc)

        values = {
            "username": username,
            "filename": data.get("filename", ""),
            "file_path": data.get("file_path", ""),
            "kb_name": data.get("kb_name", "default"),
            "mime_type": data.get("mime_type"),
            "size": data.get("size", 0),
            "status": data.get("status", "pending"),
            "chunk_count": data.get("chunk_count", 0),
            "error_message": data.get("error_message"),
            "owner": data.get("owner", username),
            "scope": data.get("scope", "private"),
            "shared_with": data.get("shared_with", []),
            "content_hash": data.get("content_hash", ""),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }

        existing = await self.get_knowledge_document(username, data["id"])
        async with self._session() as sess:
            if existing:
                stmt = pg_insert(KnowledgeDocument).values(
                    id=data["id"], **values,
                ).on_conflict_do_update(
                    index_elements=["id"],
                    set_=values,
                )
            else:
                values["created_at"] = now
                stmt = pg_insert(KnowledgeDocument).values(id=data["id"], **values)
            await sess.execute(stmt)

        return await self.get_knowledge_document(username, data["id"]) or data

    async def delete_knowledge_document(
        self, username: str, doc_id: str,
    ) -> bool:
        """Delete a knowledge document record."""
        async with self._session() as sess:
            result = await sess.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.username == username,
                ),
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await sess.delete(row)
            return True

    async def find_duplicate_document(
        self,
        username: str,
        filename: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """Check for duplicate document by hash and filename."""
        async with self._session() as sess:
            result = await sess.execute(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.username == username,
                    KnowledgeDocument.content_hash == content_hash,
                    KnowledgeDocument.filename == filename,
                    KnowledgeDocument.status == "ready",
                )
                .limit(1),
            )
            row = result.scalar_one_or_none()
            return _kb_to_dict(row) if row else None

    async def count_knowledge_documents(
        self,
        username: str,
        kb_name: str = "default",
    ) -> int:
        """Return the number of knowledge documents for a user/KB."""
        from sqlalchemy import func as sqlfunc

        async with self._session() as sess:
            result = await sess.execute(
                select(sqlfunc.count()).select_from(KnowledgeDocument).where(
                    KnowledgeDocument.username == username,
                    KnowledgeDocument.kb_name == kb_name,
                ),
            )
            return result.scalar() or 0

    # ------------------------------------------------------------------
    # User settings (key-value)
    # ------------------------------------------------------------------

    async def get_setting(self, username: str, key: str) -> str | None:
        """Read a single user setting."""
        async with self._session() as sess:
            result = await sess.execute(
                select(UserSetting).where(
                    UserSetting.username == username,
                    UserSetting.key == key,
                ),
            )
            row = result.scalar_one_or_none()
            return row.value if row else None

    async def set_setting(self, username: str, key: str, value: str) -> None:
        """Write a user setting (upsert)."""
        now = datetime.now(timezone.utc)
        async with self._session() as sess:
            stmt = pg_insert(UserSetting).values(
                username=username,
                key=key,
                value=value,
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=["username", "key"],
                set_={"value": value, "updated_at": now},
            )
            await sess.execute(stmt)

    async def delete_setting(self, username: str, key: str) -> bool:
        """Delete a user setting."""
        async with self._session() as sess:
            result = await sess.execute(
                select(UserSetting).where(
                    UserSetting.username == username,
                    UserSetting.key == key,
                ),
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await sess.delete(row)
            return True

    # ------------------------------------------------------------------
    # Content hashing utility (stateless — same as legacy)
    # ------------------------------------------------------------------

    @staticmethod
    def hash_file(file_path) -> str:
        """Compute SHA-256 hex digest of a file's contents."""
        import hashlib
        from pathlib import Path

        sha = hashlib.sha256()
        path = Path(file_path)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def hash_content(content: bytes | str) -> str:
        """Compute SHA-256 hex digest of in-memory content."""
        import hashlib

        sha = hashlib.sha256()
        if isinstance(content, str):
            sha.update(content.encode("utf-8"))
        else:
            sha.update(content)
        return sha.hexdigest()


# ---------------------------------------------------------------------------
# Internal: row → dict conversion
# ---------------------------------------------------------------------------


def _mcp_to_dict(row: MCPServer) -> dict[str, Any]:
    """Convert an MCPServer ORM row to the legacy dict format."""
    return {
        "id": row.id,
        "username": row.username,
        "name": row.name,
        "description": row.description,
        "enabled": 1 if row.enabled else 0,
        "transport": row.transport,
        "url": row.url,
        "headers": row.headers if isinstance(row.headers, dict) else {},
        "command": row.command,
        "args": row.args if isinstance(row.args, list) else [],
        "env": row.env if isinstance(row.env, dict) else {},
        "cwd": row.cwd,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _kb_to_dict(row: KnowledgeDocument) -> dict[str, Any]:
    """Convert a KnowledgeDocument ORM row to the legacy dict format."""
    return {
        "id": row.id,
        "username": row.username,
        "filename": row.filename,
        "file_path": row.file_path,
        "kb_name": row.kb_name,
        "mime_type": row.mime_type or "",
        "size": row.size,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "error_message": row.error_message or "",
        "owner": row.owner or row.username,
        "scope": row.scope,
        "shared_with": row.shared_with if isinstance(row.shared_with, list) else [],
        "content_hash": row.content_hash,
        "metadata": row.doc_metadata if isinstance(row.doc_metadata, dict) else {},
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
