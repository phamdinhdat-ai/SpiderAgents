# -*- coding: utf-8 -*-
"""PostgreSQL implementation of BaseChatRepository.

Replaces :class:`JsonChatRepository` — same interface, but all
filter/lookup operations use SQL instead of O(N) list scans, and
writes use atomic ``INSERT ... ON CONFLICT``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from openspider.app.runner.models import ChatSpec, ChatsFile
from openspider.app.runner.repo.base import BaseChatRepository
from openspider.app.channels.schema import DEFAULT_CHANNEL
from openspider.db.models import Chat

logger = logging.getLogger(__name__)


def _get_session_factory():
    """Lazy accessor — avoids capturing None at import time."""
    from openspider.db.engine import get_session_factory

    return get_session_factory()


class PgChatRepository(BaseChatRepository):
    """Chat repository backed by PostgreSQL."""

    def __init__(self, path=None):
        self._path = path or "postgresql"

    @property
    def path(self):
        return self._path

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        sf = _get_session_factory()
        if sf is None:
            raise RuntimeError("Database not started")
        async with sf() as sess:
            yield sess
            await sess.commit()

    async def load(self) -> ChatsFile:
        try:
            async with self._session() as sess:
                result = await sess.execute(
                    select(Chat).order_by(Chat.updated_at.desc()),
                )
                rows = result.scalars().all()
                return ChatsFile(
                    version=1,
                    chats=[_chat_to_spec(r) for r in rows],
                )
        except RuntimeError:
            return ChatsFile(version=1, chats=[])

    async def save(self, chats_file: ChatsFile) -> None:
        pass  # No-op — PG writes go through individual upsert/delete

    async def get_chat(self, chat_id: str) -> Optional[ChatSpec]:
        try:
            async with self._session() as sess:
                result = await sess.execute(
                    select(Chat).where(Chat.id == chat_id),
                )
                row = result.scalar_one_or_none()
                return _chat_to_spec(row) if row else None
        except RuntimeError:
            return None

    async def get_chat_by_id(
        self, session_id: str, user_id: str, channel: str = DEFAULT_CHANNEL,
    ) -> Optional[ChatSpec]:
        try:
            async with self._session() as sess:
                result = await sess.execute(
                    select(Chat)
                    .where(
                        Chat.session_id == session_id,
                        Chat.user_id == user_id,
                        Chat.channel == channel,
                    )
                    .order_by(Chat.updated_at.desc())
                    .limit(1),
                )
                row = result.scalar_one_or_none()
                return _chat_to_spec(row) if row else None
        except RuntimeError:
            return None

    async def upsert_chat(self, spec: ChatSpec) -> None:
        async with self._session() as sess:
            stmt = pg_insert(Chat).values(
                id=spec.id,
                name=spec.name,
                session_id=spec.session_id,
                user_id=spec.user_id,
                channel=spec.channel,
                agent_id=spec.agent_id,
                status=spec.status,
                pinned=spec.pinned,
                meta=spec.meta or {},
                created_at=spec.created_at,
                updated_at=spec.updated_at,
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": spec.name,
                    "session_id": spec.session_id,
                    "user_id": spec.user_id,
                    "channel": spec.channel,
                    "agent_id": spec.agent_id,
                    "status": spec.status,
                    "pinned": spec.pinned,
                    "meta": spec.meta or {},
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await sess.execute(stmt)

    async def delete_chats(self, chat_ids: list[str]) -> bool:
        if not chat_ids:
            return False
        try:
            async with self._session() as sess:
                result = await sess.execute(
                    delete(Chat).where(Chat.id.in_(chat_ids)),
                )
                return result.rowcount > 0
        except RuntimeError:
            return False

    async def filter_chats(
        self, user_id: Optional[str] = None, channel: Optional[str] = None,
    ) -> list[ChatSpec]:
        try:
            async with self._session() as sess:
                stmt = select(Chat).order_by(Chat.updated_at.desc())
                if user_id is not None:
                    stmt = stmt.where(Chat.user_id == user_id)
                if channel is not None:
                    stmt = stmt.where(Chat.channel == channel)
                result = await sess.execute(stmt)
                return [_chat_to_spec(r) for r in result.scalars().all()]
        except RuntimeError:
            return []


def _chat_to_spec(row: Chat) -> ChatSpec:
    return ChatSpec(
        id=row.id,
        name=row.name,
        session_id=row.session_id,
        user_id=row.user_id,
        channel=row.channel,
        agent_id=row.agent_id or "",
        status=row.status,
        pinned=bool(row.pinned),
        meta=row.meta if isinstance(row.meta, dict) else {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
