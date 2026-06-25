# -*- coding: utf-8 -*-
"""Loop detector for agent tool-execution loops.

Detects when an agent is stuck repeating the same tool call with identical
arguments, and injects a corrective observation into the agent's memory so
the LLM can self-correct.  Implements both exact-match (tool name + args
hash) and optional semantic overlap detection.
"""
from __future__ import annotations

import hashlib
import json as _json
import logging
from collections import deque
from typing import Any

from ..constant import (
    LOOP_DETECTION_ENABLED,
    LOOP_DETECTION_WINDOW,
    LOOP_DETECTION_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Observation templates
# ------------------------------------------------------------------

_OBSERVATION_EN = (
    "⚠️ **Loop Detected**: You have called `{tool_name}` with the same "
    "arguments {count} times in the last {window} tool calls. "
    "The previous attempts returned:\n"
    "```\n"
    "{results_summary}\n"
    "```\n\n"
    "**Consider a different approach.** Instead of repeating this call, "
    "try:\n"
    "- Using a different tool to achieve the same goal\n"
    "- Breaking the task into smaller steps\n"
    "- Asking for clarification if you're unsure what to do"
)

_OBSERVATION_ZH = (
    "⚠️ **检测到循环**: 你在最近 {window} 次工具调用中已使用相同参数调用了 "
    "`{tool_name}` {count} 次。之前的尝试返回：\n"
    "```\n"
    "{results_summary}\n"
    "```\n\n"
    "**请尝试不同的方法。** 不要重复此调用，可以：\n"
    "- 使用不同的工具实现相同目标\n"
    "- 将任务分解为更小的步骤\n"
    "- 如果不确定该做什么，请请求澄清"
)


def _make_args_hash(tool_name: str, tool_input: dict[str, Any] | None) -> str:
    """Stable hash of tool name + args for exact-match loop detection."""
    payload = _json.dumps(
        {"name": tool_name, "input": tool_input or {}},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class LoopDetector:
    """Sliding-window loop detector for agent tool calls.

    Tracks recent tool calls and detects when the exact same (tool_name,
    args) tuple appears too frequently within the configured window.

    Usage::

        detector = LoopDetector()
        # Before each tool call:
        observation = detector.check(tool_name, tool_input)
        if observation:
            await memory.add(observation)  # feed back to LLM
        detector.record(tool_name, tool_input)
    """

    def __init__(
        self,
        enabled: bool | None = None,
        window: int | None = None,
        threshold: int | None = None,
    ) -> None:
        self._enabled = (
            LOOP_DETECTION_ENABLED if enabled is None else enabled
        )
        self._window = window or LOOP_DETECTION_WINDOW
        self._threshold = threshold or LOOP_DETECTION_THRESHOLD
        # Sliding window: (tool_name, args_hash, result_summary)
        self._history: deque[tuple[str, str, str]] = deque(maxlen=self._window)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._history.clear()

    def record(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        result_summary: str = "",
    ) -> None:
        """Record a tool call into the sliding window."""
        if not self._enabled:
            return
        args_hash = _make_args_hash(tool_name, tool_input)
        self._history.append((tool_name, args_hash, result_summary))

    def check(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
    ) -> str | None:
        """Check if this tool call would constitute a loop.

        Returns an observation string to inject if a loop is detected,
        or ``None`` if this call is fine.
        """
        if not self._enabled:
            return None
        if len(self._history) < self._threshold:
            return None

        args_hash = _make_args_hash(tool_name, tool_input)

        # Count how many times this exact call appears in the window
        matches: list[str] = []
        for hist_name, hist_hash, hist_result in self._history:
            if hist_name == tool_name and hist_hash == args_hash:
                matches.append(hist_result)

        if len(matches) >= self._threshold:
            # Truncate results for readability
            results_text = "\n---\n".join(
                (r[:200] + "..." if len(r) > 200 else r)
                for r in matches[-3:]  # last 3 results only
            ) or "(no output captured)"
            return _OBSERVATION_EN.format(
                tool_name=tool_name,
                count=len(matches),
                window=len(self._history),
                results_summary=results_text,
            )

        return None

    def reset(self) -> None:
        """Clear the history (e.g., on new session)."""
        self._history.clear()
