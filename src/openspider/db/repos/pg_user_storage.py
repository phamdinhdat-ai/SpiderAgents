# -*- coding: utf-8 -*-
"""PostgreSQL-backed user storage manager.

Replaces the file-based :class:`UserStorageManager` with SQLAlchemy
queries against ``user_configs`` and ``session_messages`` tables.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from openspider.app.users.models import UserConfig as UserConfigModel
from openspider.db.models import UserConfig, SessionMessage

logger = logging.getLogger(__name__)


def _sf():
    """Lazy session-factory accessor."""
    from openspider.db.engine import get_session_factory

    return get_session_factory()


class PgUserStorageManager:
    """PostgreSQL-backed manager for per-user config and session resolution."""

    async def ensure_user_dirs(self, username: str, agent_id: str = "default") -> None:
        """No-op — PostgreSQL does not need directory scaffolding."""
        pass

    # ------------------------------------------------------------------
    # Per-user config
    # ------------------------------------------------------------------

    async def load_user_config(self, username: str) -> UserConfigModel:
        sf = _sf()
        if sf is None:
            return UserConfigModel()

        async with sf() as session:
            result = await session.execute(
                select(UserConfig).where(UserConfig.username == username),
            )
            row = result.scalar_one_or_none()
            if row is None:
                return UserConfigModel()

            return UserConfigModel(
                mcp_clients=row.mcp_clients or [],
                tools=UserConfigModel(
                    enabled_tools=row.tools_enabled or [],
                    disabled_tools=row.tools_disabled or [],
                ) if (row.tools_enabled or row.tools_disabled) else None,
                extra=row.extra or {},
            )

    async def save_user_config(self, username: str, config: UserConfigModel) -> None:
        sf = _sf()
        if sf is None:
            return

        tools_data = config.tools.model_dump() if config.tools else {}
        now = datetime.now(timezone.utc)

        async with sf() as session:
            stmt = pg_insert(UserConfig).values(
                username=username,
                mcp_clients=[c.model_dump() for c in (config.mcp_clients or [])],
                tools_enabled=tools_data.get("enabled_tools", []),
                tools_disabled=tools_data.get("disabled_tools", []),
                extra=config.extra or {},
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=["username"],
                set_={
                    "mcp_clients": [c.model_dump() for c in (config.mcp_clients or [])],
                    "tools_enabled": tools_data.get("enabled_tools", []),
                    "tools_disabled": tools_data.get("disabled_tools", []),
                    "extra": config.extra or {},
                    "updated_at": now,
                },
            )
            await session.execute(stmt)

    # ------------------------------------------------------------------
    # Session directory resolution
    # ------------------------------------------------------------------

    def resolve_session_save_dir(
        self,
        username: Optional[str],
        agent_id: str,
        legacy_workspace_dir: Path,
    ) -> str:
        if not username:
            return str(legacy_workspace_dir / "sessions")
        return f"pg://users/{username}/workspaces/{agent_id}/sessions"

    # ------------------------------------------------------------------
    # Session listing (admin dashboard)
    # ------------------------------------------------------------------

    async def list_user_session_dirs(self) -> list[tuple[str, str, str]]:
        sf = _sf()
        if sf is None:
            return []

        async with sf() as session:
            result = await session.execute(
                select(
                    SessionMessage.user_id,
                    SessionMessage.session_id,
                    func.count().label("msg_count"),
                ).group_by(
                    SessionMessage.user_id,
                    SessionMessage.session_id,
                ),
            )
            rows = result.all()
            return [(r.user_id, r.session_id, str(r.msg_count)) for r in rows]

    # ------------------------------------------------------------------
    # Session migration (workspace files → PG)
    # ------------------------------------------------------------------

    async def migrate_workspace_sessions_to_user_dirs(
        self, workspace_dir: Path, agent_id: str,
    ) -> int:
        import json as _json

        sf = _sf()
        if sf is None:
            logger.warning("PG not available – skipping session migration.")
            return 0

        sessions_dir = workspace_dir / "sessions"
        if not sessions_dir.is_dir():
            return 0

        sentinel = sessions_dir / ".pg-migration-done"
        if sentinel.exists():
            return -1

        count = 0
        async with sf() as session:
            for entry in sessions_dir.glob("*.json"):
                if entry.name.startswith("."):
                    continue
                try:
                    data = _json.loads(entry.read_text(encoding="utf-8"))
                    messages = (
                        data.get("agent", {})
                        .get("memory", {})
                        .get("memories", [])
                    )
                    for seq, msg in enumerate(messages):
                        stmt = pg_insert(SessionMessage).values(
                            chat_id=data.get("id", entry.stem),
                            session_id=entry.stem,
                            user_id=data.get("user_id", ""),
                            role=msg.get("role", "unknown") if isinstance(msg, dict) else "unknown",
                            type=msg.get("type", "text") if isinstance(msg, dict) else "text",
                            content=msg.get("content", {}) if isinstance(msg, dict) else {},
                            msg_metadata=msg.get("metadata", {}) if isinstance(msg, dict) else {},
                            sequence_number=seq,
                            created_at=datetime.now(timezone.utc),
                        ).on_conflict_do_nothing()
                        await session.execute(stmt)
                    count += 1
                except Exception:
                    logger.warning("Failed to migrate session %s", entry, exc_info=True)

        sentinel.touch()
        if count:
            logger.info("Migrated %d sessions to PG for %s.", count, workspace_dir)
        return count
