# -*- coding: utf-8 -*-
"""SQLAlchemy async engine, session factory, and connection management.

Reads ``OPENSPIDER_DATABASE_URL`` from environment (with fallback
default) and creates a configured async engine.  Provides:

* ``DatabaseManager`` — singleton lifecycle (start / close).
* ``get_async_session`` — FastAPI dependency that yields an async session.
* ``init_db`` — create all tables on first startup.
* ``is_database_enabled`` — feature-flag check.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from openspider.constant import (
    DATABASE_ENABLED,
    DATABASE_URL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine singleton
# ---------------------------------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def is_database_enabled() -> bool:
    """Return ``True`` when PostgreSQL storage is enabled."""
    return DATABASE_ENABLED


def get_engine() -> Optional[AsyncEngine]:
    """Return the current async engine, or ``None`` if not started."""
    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Return the current session factory, or ``None`` if not started."""
    return _session_factory


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an :class:`AsyncSession` and closes it.

    Usage::

        @router.get("/items")
        async def list_items(
            session: AsyncSession = Depends(get_async_session),
        ):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialised – call DatabaseManager.start() first")

    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Database manager (singleton lifecycle)
# ---------------------------------------------------------------------------


class DatabaseManager:
    """Singleton-style lifecycle manager for the PostgreSQL connection.

    Instantiate once at application startup, call ``start()`` /
    ``close()`` around the lifespan.  Stores the engine and session
    factory in module-level globals for access by dependencies and
    repositories.

    Usage::

        db = DatabaseManager()
        await db.start()
        app.state.db_manager = db
        ...
        await db.close()
    """

    def __init__(self) -> None:
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the async engine and session factory."""
        global _engine, _session_factory  # pylint: disable=global-statement

        if not DATABASE_ENABLED:
            logger.info("Database backend disabled – skipping PostgreSQL startup.")
            return

        logger.info("Starting PostgreSQL connection to %s...", _mask_url(DATABASE_URL))

        _engine = create_async_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )

        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Verify connectivity
        try:
            async with _engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL connection verified.")
        except Exception:
            logger.error("PostgreSQL connection failed – check DATABASE_URL.")
            await _engine.dispose()
            _engine = None
            _session_factory = None
            raise

        self._started = True

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        global _engine, _session_factory  # pylint: disable=global-statement

        if _engine is not None:
            await _engine.dispose()
            _engine = None
            _session_factory = None
            logger.info("PostgreSQL connection closed.")
        self._started = False

    @property
    def started(self) -> bool:
        """Return ``True`` if the database manager has been started."""
        return self._started


async def init_db() -> None:
    """Create all tables from registered ORM models.

    Safe to call on every startup — uses ``CREATE TABLE IF NOT EXISTS``
    internally.
    """
    if _engine is None:
        logger.warning("Engine not started – skipping table creation.")
        return

    # Import all models so they register with Base.metadata
    from .models import (  # noqa: F401  pylint: disable=unused-import
        AuthMeta,
        Chat,
        KnowledgeDocument,
        MCPServer,
        SessionMessage,
        TokenRevocation,
        User,
        UserConfig,
        UserSetting,
    )

    from .base import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables verified / created.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Return *url* with the password replaced by ``***`` for logging."""
    import re

    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)
