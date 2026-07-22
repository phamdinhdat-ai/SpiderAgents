# -*- coding: utf-8 -*-
"""SQLAlchemy ORM models for PostgreSQL storage.

All persistent data that was previously stored across SQLite
(``user_data.db``), JSON files (``auth.json``, ``chats.json``,
session files, ``config.json``) is modelled here as SQLAlchemy
declarative models.

Tables
------
* **users** — registered user accounts (was ``auth.json``).
* **auth_meta** — key-value metadata (JWT secret, etc.).
* **token_revocations** — revoked JWT token IDs.
* **mcp_servers** — per-user MCP client configurations.
* **knowledge_documents** — per-user knowledge document registry.
* **user_settings** — free-form key-value settings per user.
* **chats** — chat specifications (was ``chats.json``).
* **session_messages** — chat history / agent session state.
* **user_configs** — per-user configuration overrides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# ============================================================================
# Users & Auth
# ============================================================================


class User(Base):
    """Registered user account.

    Replaces the ``users`` dict in ``SECRET_DIR/auth.json``.
    """

    __tablename__ = "openspider_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), default="user", nullable=False,
    )  # "admin" or "user"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuthMeta(Base):
    """Global auth metadata (was the ``jwt_secret`` top-level key in auth.json).

    Uses a simple key-value pattern so additional metadata can be added
    without schema changes.
    """

    __tablename__ = "auth_meta"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TokenRevocation(Base):
    """Revoked JWT token IDs (was ``revoked_tokens_meta`` in auth.json).

    Expired entries are periodically cleaned by
    :func:`openspider.app.auth._clean_expired_revocations`.
    """

    __tablename__ = "token_revocations"

    jti: Mapped[str] = mapped_column(
        String(64), primary_key=True,
    )
    expires_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
    )  # Unix timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# MCP servers (was SQLite table ``user_mcp_servers``)
# ============================================================================


class MCPServer(Base):
    """Per-user MCP client configuration."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    username: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    transport: Mapped[str] = mapped_column(String(32), default="stdio")
    url: Mapped[str] = mapped_column(Text, default="")
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    command: Mapped[str] = mapped_column(Text, default="")
    args: Mapped[list] = mapped_column(JSON, default=list)
    env: Mapped[dict] = mapped_column(JSON, default=dict)
    cwd: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# Knowledge documents (was SQLite table ``user_knowledge_documents``)
# ============================================================================


class KnowledgeDocument(Base):
    """Per-user knowledge document registry."""

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    username: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    kb_name: Mapped[str] = mapped_column(String(255), default="default")
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="private")
    shared_with: Mapped[list] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(128), default="")
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "idx_kb_content_hash",
            "username",
            "content_hash",
            "filename",
        ),
    )


# ============================================================================
# User settings (was SQLite table ``user_settings``)
# ============================================================================


class UserSetting(Base):
    """Free-form key-value settings per user."""

    __tablename__ = "user_settings"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ============================================================================
# Chats (was ``chats.json``)
# ============================================================================


class Chat(Base):
    """Chat specification (ChatSpec).

    Was stored in ``workspace/<agent_id>/chats.json`` and per-user
    ``WORKING_DIR/user_data/<username>/chats.json`` files.
    """

    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    name: Mapped[str] = mapped_column(String(512), default="New Chat")
    session_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    channel: Mapped[str] = mapped_column(String(64), default="console")
    agent_id: Mapped[str] = mapped_column(
        String(255), default="", index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), default="idle",
    )  # "idle" or "running"
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_chats_session", "session_id", "user_id", "channel"),
    )


# ============================================================================
# Session messages (was per-session JSON files)
# ============================================================================


class SessionMessage(Base):
    """Chat history / agent session state messages.

    Each row represents one message within a chat session.  The full
    session state (agent memory) was previously serialised as a single
    JSON file per session; here it is normalised into individual rows
    for efficient querying.
    """

    __tablename__ = "session_messages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    chat_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # "user", "assistant", "system", "tool"
    type: Mapped[str] = mapped_column(
        String(64), default="text",
    )  # "text", "plugin_call_output", etc.
    content: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    msg_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    sequence_number: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_session_msgs", "session_id", "user_id", "sequence_number"),
    )


# ============================================================================
# User config overlay (was ``USERS_DIR/<hash>/config.json``)
# ============================================================================


class UserConfig(Base):
    """Per-user configuration overrides.

    Was stored as ``USERS_DIR/<sha256(username)>/config.json``.
    """

    __tablename__ = "user_configs"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    mcp_clients: Mapped[list] = mapped_column(JSON, default=list)
    tools_enabled: Mapped[list] = mapped_column(JSON, default=list)
    tools_disabled: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
