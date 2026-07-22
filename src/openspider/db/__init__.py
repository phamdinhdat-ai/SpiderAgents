# -*- coding: utf-8 -*-
"""PostgreSQL database layer for OpenSpider.

Provides SQLAlchemy async engine, session management, and repository
implementations for all persistent data (users, MCP configs, chat
history, sessions, knowledge documents, and user settings).

Feature flag: set ``OPENSPIDER_DATABASE_ENABLED=true`` to use
PostgreSQL instead of the legacy SQLite + JSON file storage.
"""

from .engine import (
    DatabaseManager,
    get_async_session,
    init_db,
    is_database_enabled,
)

__all__ = [
    "DatabaseManager",
    "get_async_session",
    "init_db",
    "is_database_enabled",
]
