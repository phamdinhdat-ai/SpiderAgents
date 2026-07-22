# -*- coding: utf-8 -*-
"""Global UI settings (language, theme, storage backends, etc.).

When ``OPENSPIDER_DATABASE_ENABLED`` is ``True``, settings are persisted
in PostgreSQL (``user_settings`` table).  Otherwise they live in
``WORKING_DIR/settings.json``.  The file is always kept up-to-date as
a backup.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, HTTPException

from ...agents.skill_system.registry import (
    set_builtin_skill_language_preference,
)
from ...constant import DATABASE_ENABLED, WORKING_DIR
from ..settings_store import SettingsStore, _file_load, _file_save

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

_SETTINGS_FILE = WORKING_DIR / "settings.json"

_VALID_LANGUAGES = {"en", "zh", "ja", "ru", "pt-BR", "id", "vi"}


async def _load() -> dict:
    """Load settings from the active backend."""
    store = SettingsStore()
    return await store.load()


async def _save(data: dict) -> None:
    """Persist settings to the active backend(s)."""
    store = SettingsStore()
    await store.save(data)


@router.get("/language", summary="Get UI language")
async def get_language() -> dict:
    data = await _load()
    return {"language": data.get("language", "en")}


@router.put("/language", summary="Update UI language")
async def put_language(
    body: dict = Body(..., description='e.g. {"language": "en"}'),
) -> dict:
    language = body.get("language", "").strip()
    if language not in _VALID_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid language, must be one of "
            f"{sorted(_VALID_LANGUAGES)}",
        )
    data = await _load()
    data["language"] = language
    await _save(data)
    # Update cached builtin preference since it falls back to UI language.
    if not data.get("builtin_skill_language"):
        set_builtin_skill_language_preference(
            "vi" if language.startswith("vi") else "en",
        )
    return {"language": language}


# ---------------------------------------------------------------------------
# Storage backends configuration
# ---------------------------------------------------------------------------


@router.get("/storage", summary="Get storage backend configuration")
async def get_storage_config() -> dict:
    """Return the current file-storage and vector-store backend settings."""
    data = await _load()
    return data.get("storage_backends", {})


@router.put("/storage", summary="Update storage backend configuration")
async def put_storage_config(
    body: dict = Body(..., description="Storage backend configuration"),
) -> dict:
    """Update file-storage and/or vector-store backend settings.

    Example request body::

        {
          "file_storage": {
            "backend": "minio",
            "minio_endpoint": "play.min.io:9000",
            "minio_access_key": "...",
            "minio_secret_key": "...",
            "minio_bucket": "openspider-kb",
            "minio_secure": false
          },
          "vector_store": {
            "backend": "qdrant",
            "qdrant_url": "http://localhost:6333"
          }
        }

    Only the keys that are provided are updated — other settings
    are left unchanged.
    """
    data = await _load()
    current = data.get("storage_backends", {})

    # Merge incoming config into current (shallow merge per section)
    for section in ("file_storage", "vector_store"):
        if section in body and isinstance(body[section], dict):
            current.setdefault(section, {}).update(body[section])

    data["storage_backends"] = current
    await _save(data)
    logger.info("Storage backends configuration updated")
    return current


@router.get("/storage/status", summary="Check storage backend connectivity")
async def get_storage_status() -> dict:
    """Test connectivity to the configured storage backends.

    Attempts to connect to the configured file-storage and
    vector-store backends and reports whether each is reachable.
    """
    data = await _load()
    sb = data.get("storage_backends", {})
    results = {}

    # File storage status
    fs_cfg = sb.get("file_storage", {})
    fs_backend = fs_cfg.get("backend", "local")
    if fs_backend == "minio":
        try:
            from minio import Minio
            client = Minio(
                fs_cfg.get("minio_endpoint", ""),
                access_key=fs_cfg.get("minio_access_key", ""),
                secret_key=fs_cfg.get("minio_secret_key", ""),
                secure=fs_cfg.get("minio_secure", False),
            )
            client.list_buckets()
            results["file_storage"] = {
                "backend": "minio",
                "reachable": True,
                "message": "MinIO connection successful",
            }
        except ImportError:
            results["file_storage"] = {
                "backend": "minio",
                "reachable": False,
                "message": "minio package not installed",
            }
        except Exception as exc:
            results["file_storage"] = {
                "backend": "minio",
                "reachable": False,
                "message": str(exc),
            }
    else:
        results["file_storage"] = {
            "backend": "local",
            "reachable": True,
            "message": "Local storage available",
        }

    # Vector store status
    vs_cfg = sb.get("vector_store", {})
    vs_backend = vs_cfg.get("backend", "auto")
    if vs_backend == "qdrant":
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(
                url=vs_cfg.get("qdrant_url", ""),
                api_key=vs_cfg.get("qdrant_api_key") or None,
            )
            client.get_collections()
            results["vector_store"] = {
                "backend": "qdrant",
                "reachable": True,
                "message": "Qdrant connection successful",
            }
        except ImportError:
            results["vector_store"] = {
                "backend": "qdrant",
                "reachable": False,
                "message": "qdrant-client package not installed",
            }
        except Exception as exc:
            results["vector_store"] = {
                "backend": "qdrant",
                "reachable": False,
                "message": str(exc),
            }
    elif vs_backend == "milvus":
        try:
            from pymilvus import connections
            if vs_cfg.get("milvus_uri"):
                connections.connect(
                    alias="status_check",
                    uri=vs_cfg["milvus_uri"],
                    token=vs_cfg.get("milvus_token") or None,
                )
            else:
                connections.connect(
                    alias="status_check",
                    host=vs_cfg.get("milvus_host", "localhost"),
                    port=vs_cfg.get("milvus_port", "19530"),
                )
            connections.disconnect("status_check")
            results["vector_store"] = {
                "backend": "milvus",
                "reachable": True,
                "message": "Milvus connection successful",
            }
        except ImportError:
            results["vector_store"] = {
                "backend": "milvus",
                "reachable": False,
                "message": "pymilvus package not installed",
            }
        except Exception as exc:
            results["vector_store"] = {
                "backend": "milvus",
                "reachable": False,
                "message": str(exc),
            }
    else:
        results["vector_store"] = {
            "backend": vs_backend,
            "reachable": True,
            "message": "Auto-detected or local backend",
        }

    return results


# ---------------------------------------------------------------------------
# Database backend status
# ---------------------------------------------------------------------------


@router.get("/database/status", summary="Get PostgreSQL database status")
async def get_database_status() -> dict:
    """Return the current database backend configuration and health.

    Reports whether PostgreSQL is enabled, whether the connection is
    healthy, and a masked version of the connection URL for diagnostics.
    """
    from ...constant import DATABASE_URL as _URL
    from ..settings_store import SettingsStore

    store = SettingsStore()

    result: dict = {
        "enabled": store.pg_enabled,
        "reachable": False,
        "url": _mask_url(_URL) if store.pg_enabled else "",
        "message": "Database backend is disabled.",
    }

    if not store.pg_enabled:
        return result

    try:
        from ...db.engine import get_engine
        from sqlalchemy import text

        engine = get_engine()
        if engine is not None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            result["reachable"] = True
            result["message"] = "PostgreSQL connection healthy."
        else:
            result["message"] = "Engine not initialised."
    except Exception as exc:
        result["reachable"] = False
        result["message"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Return *url* with the password replaced by ``***``."""
    import re

    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

