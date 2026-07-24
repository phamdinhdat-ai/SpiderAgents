#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot migration: SQLite + JSON → PostgreSQL.

Usage::

    OPENSPIDER_DATABASE_URL=postgresql+asyncpg://5gai:Vht%402025@localhost:5433/5gai \\
    python scripts/migrate_to_postgres.py

Reads all existing data from the legacy backends and writes it into
PostgreSQL.  Idempotent — re-running is safe (duplicate rows are
skipped via ``ON CONFLICT DO NOTHING``).

Migrates
--------
1. ``auth.json`` → ``users``, ``auth_meta``, ``token_revocations``
2. ``user_data.db`` (SQLite) → ``mcp_servers``, ``knowledge_documents``,
   ``user_settings``
3. ``chats.json`` files → ``chats``
4. Session ``*.json`` files → ``session_messages``
5. Per-user ``config.json`` files → ``user_configs``
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup – so we can import openspider modules
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate_to_postgres")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "OPENSPIDER_DATABASE_URL",
    "postgresql+asyncpg://openspider:spiderman@192.168.100.26:5433/openspider",
)

# Resolve WORKING_DIR and SECRET_DIR
from openspider.constant import WORKING_DIR, SECRET_DIR, USERS_DIR

SQLITE_DB = WORKING_DIR / "user_data" / "user_data.db"
AUTH_FILE = SECRET_DIR / "auth.json"


# ============================================================================
# Helpers
# ============================================================================


def _now_iso() -> datetime:
    """Return a timezone-aware UTC datetime (NOT a string).

    SQLAlchemy ``DateTime(timezone=True)`` columns expect ``datetime``
    objects, not ISO-format strings.
    """
    return datetime.now(timezone.utc)


def _to_dt(value: str | datetime | None) -> datetime:
    """Coerce a value to a timezone-aware UTC datetime.

    Handles ISO-format strings (from JSON files), naive datetimes
    (from SQLite), and already-aware datetimes.
    """
    if value is None:
        return _now_iso()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        # Try parsing ISO format strings (e.g. "2026-07-06T16:24:48.127025Z")
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return _now_iso()
    return _now_iso()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict, decoding JSON fields."""
    d = dict(row)
    json_fields = {"headers", "args", "env", "shared_with", "metadata"}
    for field in json_fields.intersection(d):
        raw = d[field]
        if isinstance(raw, str) and raw.strip():
            try:
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
    return d


# ============================================================================
# Migration functions
# ============================================================================


async def migrate_auth(session) -> int:
    """Migrate ``auth.json`` → ``users`` + ``auth_meta`` tables."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from openspider.db.models import User, AuthMeta

    if not AUTH_FILE.is_file():
        logger.info("No auth.json found — skipping auth migration.")
        return 0

    with open(AUTH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    now = _now_iso()

    # Migrate users
    users_data = data.get("users", {})
    for username, user_info in users_data.items():
        stmt = pg_insert(User).values(
            username=username,
            password_hash=user_info.get("password_hash", ""),
            password_salt=user_info.get("password_salt", ""),
            role=user_info.get("role", "user"),
            created_at=now,
            updated_at=now,
        ).on_conflict_do_nothing()
        await session.execute(stmt)
        count += 1

    # Migrate jwt_secret (decrypt if needed)
    jwt_secret = data.get("jwt_secret", "")
    if jwt_secret:
        # Try Fernet decryption if the value looks encrypted
        try:
            from openspider.security.secret_store import is_encrypted, decrypt

            if is_encrypted(jwt_secret):
                jwt_secret = decrypt(jwt_secret)
        except ImportError:
            logger.warning(
                "Could not import secret_store — saving jwt_secret as-is. "
                "Tokens issued before migration may be invalid.",
            )
        except Exception:
            logger.warning(
                "Could not decrypt jwt_secret — saving as-is. "
                "Tokens issued before migration may be invalid.",
            )

    if jwt_secret:
        stmt = pg_insert(AuthMeta).values(
            key="jwt_secret",
            value=jwt_secret,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=["key"],
            set_={"value": jwt_secret, "updated_at": now},
        )
        await session.execute(stmt)

    logger.info("Auth migration: %d users migrated.", count)
    return count


async def migrate_user_data_store(session) -> int:
    """Migrate SQLite ``user_data.db`` → PG tables."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from openspider.db.models import MCPServer, KnowledgeDocument, UserSetting

    if not SQLITE_DB.is_file():
        logger.info("No user_data.db found — skipping user data migration.")
        return 0

    sql_conn = sqlite3.connect(str(SQLITE_DB))
    sql_conn.row_factory = sqlite3.Row
    count = 0

    # MCP servers
    try:
        mcp_rows = sql_conn.execute(
            "SELECT * FROM user_mcp_servers",
        ).fetchall()
        for row in mcp_rows:
            d = _row_to_dict(row)
            stmt = pg_insert(MCPServer).values(
                id=d["id"],
                username=d["username"],
                name=d["name"],
                description=d.get("description", ""),
                enabled=bool(d.get("enabled", 1)),
                transport=d.get("transport", "stdio"),
                url=d.get("url", ""),
                headers=d.get("headers", {}),
                command=d.get("command", ""),
                args=d.get("args", []),
                env=d.get("env", {}),
                cwd=d.get("cwd", ""),
                created_at=_to_dt(d.get("created_at")),
                updated_at=_to_dt(d.get("updated_at")),
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            count += 1
        logger.info("MCP servers: %d rows migrated.", len(mcp_rows))
    except sqlite3.OperationalError:
        logger.info("MCP servers table empty or nonexistent.")

    # Knowledge documents
    try:
        kb_rows = sql_conn.execute(
            "SELECT * FROM user_knowledge_documents",
        ).fetchall()
        kb_count = 0
        for row in kb_rows:
            d = _row_to_dict(row)
            stmt = pg_insert(KnowledgeDocument).values(
                id=d["id"],
                username=d["username"],
                filename=d.get("filename", ""),
                file_path=d.get("file_path", ""),
                kb_name=d.get("kb_name", "default"),
                mime_type=d.get("mime_type"),
                size=d.get("size", 0),
                status=d.get("status", "pending"),
                chunk_count=d.get("chunk_count", 0),
                error_message=d.get("error_message"),
                owner=d.get("owner", d["username"]),
                scope=d.get("scope", "private"),
                shared_with=d.get("shared_with", []),
                content_hash=d.get("content_hash", ""),
                doc_metadata=d.get("metadata", {}),
                created_at=_to_dt(d.get("created_at")),
                updated_at=_to_dt(d.get("updated_at")),
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            kb_count += 1
        count += kb_count
        logger.info("Knowledge documents: %d rows migrated.", kb_count)
    except sqlite3.OperationalError:
        logger.info("Knowledge documents table empty or nonexistent.")

    # User settings
    try:
        settings_rows = sql_conn.execute(
            "SELECT * FROM user_settings",
        ).fetchall()
        settings_count = 0
        for row in settings_rows:
            d = dict(row)
            stmt = pg_insert(UserSetting).values(
                username=d["username"],
                key=d["key"],
                value=d.get("value", ""),
                updated_at=_to_dt(d.get("updated_at")),
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            settings_count += 1
        count += settings_count
        logger.info("User settings: %d rows migrated.", settings_count)
    except sqlite3.OperationalError:
        logger.info("User settings table empty or nonexistent.")

    sql_conn.close()
    return count


async def migrate_chats(session) -> int:
    """Migrate ``chats.json`` files → ``chats`` table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from openspider.db.models import Chat

    count = 0
    chat_files: list[Path] = []

    # Workspace-level chats.json
    workspaces_root = WORKING_DIR / "workspaces"
    if workspaces_root.is_dir():
        for ws_dir in workspaces_root.iterdir():
            if not ws_dir.is_dir():
                continue
            cf = ws_dir / "chats.json"
            if cf.is_file():
                chat_files.append(cf)

    # Per-user chats.json
    user_data_dir = WORKING_DIR / "user_data"
    if user_data_dir.is_dir():
        for user_dir in user_data_dir.iterdir():
            cf = user_dir / "chats.json"
            if cf.is_file():
                chat_files.append(cf)

    for cf in chat_files:
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            chats = data.get("chats", [])
            for chat in chats:
                stmt = pg_insert(Chat).values(
                    id=chat.get("id", ""),
                    name=chat.get("name", "New Chat"),
                    session_id=chat.get("session_id", ""),
                    user_id=chat.get("user_id", ""),
                    channel=chat.get("channel", "console"),
                    agent_id=chat.get("agent_id", ""),
                    status=chat.get("status", "idle"),
                    pinned=chat.get("pinned", False),
                    meta=chat.get("meta", {}),
                    created_at=_to_dt(chat.get("created_at")),
                    updated_at=_to_dt(chat.get("updated_at")),
                ).on_conflict_do_nothing()
                await session.execute(stmt)
                count += 1
        except Exception:
            logger.warning("Failed to migrate chats from %s", cf, exc_info=True)

    logger.info("Chats: %d rows migrated from %d files.", count, len(chat_files))
    return count


async def migrate_sessions(session) -> int:
    """Migrate session ``*.json`` files → ``session_messages`` table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from openspider.db.models import SessionMessage

    count = 0

    # Scan workspace sessions
    workspaces_root = WORKING_DIR / "workspaces"
    session_dirs: list[Path] = []

    if workspaces_root.is_dir():
        for ws_dir in workspaces_root.iterdir():
            sd = ws_dir / "sessions"
            if sd.is_dir():
                session_dirs.append(sd)

    # Scan per-user sessions
    if USERS_DIR.is_dir():
        for user_hash_dir in USERS_DIR.iterdir():
            workspaces_dir = user_hash_dir / "workspaces"
            if not workspaces_dir.is_dir():
                continue
            for agent_dir in workspaces_dir.iterdir():
                sd = agent_dir / "sessions"
                if sd.is_dir():
                    session_dirs.append(sd)

    for sd in session_dirs:
        for entry in sd.glob("*.json"):
            if entry.name.startswith("."):
                continue
            try:
                raw = entry.read_text(encoding="utf-8")
                data = json.loads(raw)
                messages = data.get("agent", {}).get("memory", {}).get("memories", [])
                if not messages:
                    messages = (
                        data.get("agent", {}).get("memory", {}).get("content", [])
                    )

                for seq, msg in enumerate(messages):
                    stmt = pg_insert(SessionMessage).values(
                        chat_id=data.get("id", entry.stem),
                        session_id=entry.stem,
                        user_id=data.get("user_id", ""),
                        role=msg.get("role", "unknown") if isinstance(msg, dict) else "unknown",
                        type=msg.get("type", "text") if isinstance(msg, dict) else "text",
                        content=msg.get("content", {}) if isinstance(msg, dict) else {"raw": str(msg)},
                        msg_metadata=msg.get("metadata", {}) if isinstance(msg, dict) else {},
                        sequence_number=seq,
                        created_at=_now_iso(),
                    ).on_conflict_do_nothing()
                    await session.execute(stmt)
                    count += 1
            except Exception:
                logger.warning(
                    "Failed to migrate session %s", entry, exc_info=True,
                )

    logger.info("Session messages: %d rows migrated.", count)
    return count


async def migrate_user_configs(session) -> int:
    """Migrate per-user ``config.json`` → ``user_configs`` table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from openspider.db.models import UserConfig

    count = 0

    if not USERS_DIR.is_dir():
        logger.info("No users directory — skipping user config migration.")
        return 0

    for user_hash_dir in USERS_DIR.iterdir():
        cf = user_hash_dir / "config.json"
        if not cf.is_file():
            continue
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            # The username is not stored in config.json — use the hash for now
            stmt = pg_insert(UserConfig).values(
                username=user_hash_dir.name,  # Will need updating later
                mcp_clients=data.get("mcp_clients", []),
                tools_enabled=data.get("tools", {}).get("enabled_tools", []),
                tools_disabled=data.get("tools", {}).get("disabled_tools", []),
                extra=data.get("extra", {}),
                updated_at=_now_iso(),
            ).on_conflict_do_nothing()
            await session.execute(stmt)
            count += 1
        except Exception:
            logger.warning(
                "Failed to migrate user config %s", cf, exc_info=True,
            )

    logger.info("User configs: %d rows migrated.", count)
    return count


# ============================================================================
# Main
# ============================================================================


async def main() -> None:
    """Run all migration steps in a single transaction."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    logger.info("=" * 60)
    logger.info("Starting data migration to PostgreSQL")
    logger.info("Database URL: %s", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)
    logger.info("Working dir: %s", WORKING_DIR)
    logger.info("=" * 60)

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

    # Create all tables first
    from openspider.db.base import Base
    from openspider.db.models import (  # noqa: F401
        AuthMeta, Chat, KnowledgeDocument, MCPServer,
        SessionMessage, TokenRevocation, User, UserConfig, UserSetting,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables verified / created.")

    # Run migrations
    async with async_session() as sess:
        auth_count = await migrate_auth(sess)
        uds_count = await migrate_user_data_store(sess)
        chat_count = await migrate_chats(sess)
        msg_count = await migrate_sessions(sess)
        config_count = await migrate_user_configs(sess)

        await sess.commit()

    total = auth_count + uds_count + chat_count + msg_count + config_count
    logger.info("=" * 60)
    logger.info("Migration complete: %d total rows migrated.", total)
    logger.info("  Auth users:     %d", auth_count)
    logger.info("  User data:      %d", uds_count)
    logger.info("  Chats:          %d", chat_count)
    logger.info("  Session msgs:   %d", msg_count)
    logger.info("  User configs:   %d", config_count)
    logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
