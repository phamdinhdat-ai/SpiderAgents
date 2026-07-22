# -*- coding: utf-8 -*-
"""Unified settings persistence — PostgreSQL or JSON file.

When ``OPENSPIDER_DATABASE_ENABLED`` is ``True``, settings are stored in
the ``user_settings`` PostgreSQL table (keyed by a reserved ``"system"``
user).  Otherwise they fall back to ``WORKING_DIR/settings.json``.

The file is always written as a backup even when PG is active, so that
disabling the database later does not lose the last-known settings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..constant import DATABASE_ENABLED, WORKING_DIR

logger = logging.getLogger(__name__)

_SETTINGS_FILE = WORKING_DIR / "settings.json"


# ---------------------------------------------------------------------------
# File helpers (kept for backward compat and dual-write)
# ---------------------------------------------------------------------------


def _file_load() -> dict:
    """Load settings from ``settings.json``."""
    if _SETTINGS_FILE.is_file():
        try:
            return json.loads(_SETTINGS_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _file_save(data: dict) -> None:
    """Persist settings to ``settings.json``."""
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        "utf-8",
    )


# ---------------------------------------------------------------------------
# Unified store
# ---------------------------------------------------------------------------


class SettingsStore:
    """Dual-backend settings store.

    Usage::

        store = SettingsStore()
        data = await store.load()
        data["language"] = "en"
        await store.save(data)
    """

    def __init__(self) -> None:
        self._pg_enabled = DATABASE_ENABLED

    async def load(self) -> dict:
        """Return all settings.

        When PG is enabled, returns PG data merged on top of the
        file data (file wins for keys present in both, since the file
        is always kept up-to-date).
        """
        file_data = _file_load()

        if not self._pg_enabled:
            return file_data

        try:
            from ..db.repos.pg_settings_store import PgSettingsStore

            pg_store = PgSettingsStore()
            pg_data = await pg_store.load()
        except Exception:
            logger.warning("Failed to load settings from PG — using file.", exc_info=True)
            return file_data

        # Merge: PG base, file overrides
        merged = {**pg_data, **file_data}
        return merged

    async def save(self, data: dict) -> None:
        """Persist *data* to both backends.

        The file is always written.  PG is written only when enabled.
        """
        # Always write file (fast, serves as backup)
        _file_save(data)

        if not self._pg_enabled:
            return

        try:
            from ..db.repos.pg_settings_store import PgSettingsStore

            pg_store = PgSettingsStore()
            await pg_store.save(data)
        except Exception:
            logger.warning("Failed to persist settings to PG.", exc_info=True)

    @property
    def pg_enabled(self) -> bool:
        """Return ``True`` when the PostgreSQL backend is active."""
        return self._pg_enabled
