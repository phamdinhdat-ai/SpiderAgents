# -*- coding: utf-8 -*-
"""PostgreSQL-backed settings persistence.

Stores global UI settings (language, storage backends, etc.) in the
``user_settings`` table under a reserved ``"system"`` username so they
are available regardless of which user is logged in.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from openspider.db.models import UserSetting

logger = logging.getLogger(__name__)

_SYSTEM_USER = "system"


class PgSettingsStore:
    """Read/write global settings from PostgreSQL ``user_settings`` table.

    All settings are scoped to the reserved ``"system"`` username so
    they act as global defaults independent of any authenticated user.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load(self) -> dict:
        """Return all global settings as a flat dict.

        Nested structures (like ``storage_backends``) are stored as
        JSON strings and transparently decoded here.
        """
        from openspider.db.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            logger.warning("DB not started — returning empty settings.")
            return {}

        async with sf() as session:
            result = await session.execute(
                select(UserSetting).where(
                    UserSetting.username == _SYSTEM_USER,
                ),
            )
            rows = result.scalars().all()

        data: dict = {}
        for row in rows:
            val = row.value
            # Auto-decode JSON values
            if val.startswith("{") or val.startswith("["):
                try:
                    data[row.key] = json.loads(val)
                except json.JSONDecodeError:
                    data[row.key] = val
            else:
                data[row.key] = val

        return data

    async def save(self, data: dict) -> None:
        """Persist *data* to the ``user_settings`` table.

        Each top-level key becomes a row.  Nested dicts/lists are
        serialised as JSON strings so they survive round-tripping.
        """
        from openspider.db.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            logger.warning("DB not started — settings not persisted.")
            return

        now = datetime.now(timezone.utc)

        async with sf() as session:
            for key, value in data.items():
                # Serialise structured values
                if isinstance(value, (dict, list)):
                    str_value = json.dumps(value, ensure_ascii=False)
                else:
                    str_value = str(value)

                stmt = pg_insert(UserSetting).values(
                    username=_SYSTEM_USER,
                    key=key,
                    value=str_value,
                    updated_at=now,
                ).on_conflict_do_update(
                    index_elements=["username", "key"],
                    set_={"value": str_value, "updated_at": now},
                )
                await session.execute(stmt)

        logger.debug("Settings persisted to PG: %d keys.", len(data))

    async def get(self, key: str) -> str | None:
        """Read a single setting by key."""
        from openspider.db.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            return None

        async with sf() as session:
            result = await session.execute(
                select(UserSetting).where(
                    UserSetting.username == _SYSTEM_USER,
                    UserSetting.key == key,
                ),
            )
            row = result.scalar_one_or_none()
            return row.value if row else None

    async def set(self, key: str, value: str) -> None:
        """Write a single setting key."""
        await self.save({key: value})
