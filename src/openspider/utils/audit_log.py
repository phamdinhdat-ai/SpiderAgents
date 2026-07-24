# -*- coding: utf-8 -*-
"""Structured security audit log.

Writes JSONL records to a rotating file for post-incident review.
All records include: timestamp (ISO-8601 UTC), event type, session/agent
context, and a freeform ``detail`` dict.

Usage::

    from openspider.utils.audit_log import audit

    audit(
        event="tool_guard.blocked",
        session_id=session_id,
        agent_id=agent_id,
        detail={"tool": tool_name, "reason": "command_injection"},
    )

The log file path is controlled by ``OPENSPIDER_AUDIT_LOG_FILE``
(fallback ``QWENPAW_AUDIT_LOG_FILE``).  When the env var is absent,
the file defaults to ``{DATA_DIR}/audit.jsonl``.

Rotation is handled by ``logging.handlers.RotatingFileHandler`` —
default 10 MiB per file, 5 backups.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Any

from ..constant import AUDIT_LOG_MAX_BYTES, AUDIT_LOG_BACKUP_COUNT

_AUDIT_LOGGER_NAME = "openspider.audit"
# (AUDIT_LOG_MAX_BYTES, AUDIT_LOG_BACKUP_COUNT migrated to constant.py)

_audit_logger: logging.Logger | None = None


def _get_audit_file_path() -> str | None:
    """Return the configured audit log file path, or *None* to disable."""
    for env_var in (
        "OPENSPIDER_AUDIT_LOG_FILE",
        "OPENSPIDER_AUDIT_LOG_FILE",
    ):
        path = os.environ.get(env_var, "").strip()
        if path:
            return path
    # Fall back to DATA_DIR if set
    data_dir = os.environ.get("OPENSPIDER_DATA_DIR") or os.environ.get(
        "OPENSPIDER_DATA_DIR"
    )
    if data_dir:
        return os.path.join(data_dir, "audit.jsonl")
    return None


def _build_audit_logger() -> logging.Logger:
    """Build and cache the rotating-file audit logger."""
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    logger.propagate = False  # Don't send audit records to root logger

    if logger.handlers:
        return logger  # Already configured

    file_path = _get_audit_file_path()
    if file_path:
        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            handler: logging.Handler = logging.handlers.RotatingFileHandler(
                file_path,
                maxBytes=AUDIT_LOG_MAX_BYTES,
                backupCount=AUDIT_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        except OSError as exc:
            # Fall back to stderr if the file cannot be opened
            logging.getLogger(__name__).warning(
                "Audit log file unavailable (%s). "
                "Audit events will be written to stderr only.",
                exc,
            )
            handler = logging.StreamHandler()
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def audit(
    event: str,
    *,
    session_id: str = "",
    agent_id: str = "",
    user_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    """Write one structured audit record.

    Args:
        event:       Dot-separated event name, e.g. ``"approval.granted"``.
        session_id:  Session that triggered the event (may be abbreviated).
        agent_id:    Agent involved (empty string if not applicable).
        user_id:     User who triggered the event (optional).
        detail:      Arbitrary extra fields merged into the record.
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = _build_audit_logger()

    record: dict[str, Any] = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
    }
    # Attach the current correlation/request ID when available
    try:
        from .context import request_id_ctx

        rid = request_id_ctx.get()
        if rid:
            record["request_id"] = rid
    except Exception:  # pragma: no cover
        pass
    if session_id:
        record["session_id"] = session_id
    if agent_id:
        record["agent_id"] = agent_id
    if user_id:
        record["user_id"] = user_id
    if detail:
        record.update(detail)

    _audit_logger.info(json.dumps(record, ensure_ascii=False, default=str))
