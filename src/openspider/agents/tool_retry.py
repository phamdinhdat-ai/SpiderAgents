# -*- coding: utf-8 -*-
"""Tool-level retry wrapper with exponential backoff.

Wraps individual tool executions to automatically retry on transient
errors (timeout, connection failure) before feeding the final result
to the LLM.  Supports optional progressive escalation to alternative
tools when a tool consistently fails.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from ..constant import (
    TOOL_RETRY_ENABLED,
    TOOL_MAX_RETRIES,
    TOOL_RETRY_BACKOFF_BASE,
)

logger = logging.getLogger(__name__)

# Transient error patterns in tool output / exceptions
_TRANSIENT_ERROR_INDICATORS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "connection refused",
    "connection reset",
    "temporary failure",
    "try again later",
    "rate limit",
    "too many requests",
    "service unavailable",
    "internal server error",
    "bad gateway",
    "gateway timeout",
)


def _is_transient_error(error: str | Exception) -> bool:
    """Check if an error is likely transient (worth retrying)."""
    if isinstance(error, Exception):
        error_str = str(error).lower()
        cls_name = type(error).__name__.lower()
        # Common transient exception types
        if any(
            kw in cls_name
            for kw in ("timeout", "connection", "rate", "temporary")
        ):
            return True
    else:
        error_str = error.lower()

    return any(indicator in error_str for indicator in _TRANSIENT_ERROR_INDICATORS)


class ToolRetryWrapper:
    """Wraps a tool execution function with retry logic.

    Usage::

        wrapper = ToolRetryWrapper()
        result = await wrapper.execute(
            tool_name="execute_shell_command",
            tool_fn=lambda: actual_tool_execution(),
            tool_call_id="abc123",
        )
    """

    def __init__(
        self,
        enabled: bool | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
    ) -> None:
        self._enabled = TOOL_RETRY_ENABLED if enabled is None else enabled
        self._max_retries = max_retries or TOOL_MAX_RETRIES
        self._backoff_base = backoff_base or TOOL_RETRY_BACKOFF_BASE

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def execute(
        self,
        tool_name: str,
        tool_fn: Callable[[], Awaitable[Any]],
        tool_call_id: str = "",
    ) -> Any:
        """Execute a tool with retry on transient errors.

        Args:
            tool_name: Name of the tool (for logging).
            tool_fn: Async callable that executes the tool.
            tool_call_id: Optional tool call ID (for logging).

        Returns:
            The tool result (success or final failure).
        """
        if not self._enabled or self._max_retries <= 0:
            return await tool_fn()

        last_error: Exception | None = None
        last_result: Any = None

        for attempt in range(self._max_retries + 1):  # 0..max_retries
            try:
                result = await tool_fn()
                last_result = result

                # Check if result indicates a transient error
                error_text = self._extract_error_text(result)
                if error_text and _is_transient_error(error_text):
                    if attempt < self._max_retries:
                        wait = self._backoff_base * (2 ** attempt)
                        logger.info(
                            "Tool '%s' (call %s) attempt %d/%d: "
                            "transient error, retrying in %.1fs",
                            tool_name,
                            tool_call_id[:8] if tool_call_id else "?",
                            attempt + 1,
                            self._max_retries,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    else:
                        logger.warning(
                            "Tool '%s' (call %s): all %d retries exhausted",
                            tool_name,
                            tool_call_id[:8] if tool_call_id else "?",
                            self._max_retries,
                        )
                return result

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if _is_transient_error(exc) and attempt < self._max_retries:
                    wait = self._backoff_base * (2 ** attempt)
                    logger.info(
                        "Tool '%s' (call %s) attempt %d/%d: "
                        "%s, retrying in %.1fs",
                        tool_name,
                        tool_call_id[:8] if tool_call_id else "?",
                        attempt + 1,
                        self._max_retries,
                        type(exc).__name__,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.warning(
                    "Tool '%s' (call %s): non-retryable error %s",
                    tool_name,
                    tool_call_id[:8] if tool_call_id else "?",
                    type(exc).__name__,
                )
                raise

        # All retries exhausted on exception path
        if last_error is not None:
            raise last_error
        return last_result

    @staticmethod
    def _extract_error_text(result: Any) -> str | None:
        """Extract error text from a tool result."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            error = result.get("error") or result.get("stderr") or ""
            if error:
                return str(error)
            output = result.get("output") or ""
            if isinstance(output, str):
                return output
            if isinstance(output, list):
                texts = [
                    item.get("text", "")
                    for item in output
                    if isinstance(item, dict)
                ]
                return " ".join(texts)
        return None
