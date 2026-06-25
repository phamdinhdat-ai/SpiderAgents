# -*- coding: utf-8 -*-
"""Self-verification module for agent tool results.

When enabled, after each tool call the agent verifies the result before
committing it to memory.  Failed verifications are fed back as additional
observations so the LLM can self-correct.

Verification strategies:
- ``file_write`` / ``edit_file``: reads back the file and checks content
- ``execute_shell_command``: checks exit code and stderr
- ``search`` / ``grep_search`` / ``glob_search``: checks result count
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..constant import (
    SELF_VERIFY_ENABLED,
    SELF_VERIFY_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Verification result templates
# ------------------------------------------------------------------

_VERIFY_FAIL_FILE_EN = (
    "❌ **Self-Verification Failed**: The file `{file_path}` was written "
    "but the content does not match what was expected.\n"
    "- Expected (first 200 chars): `{expected}`\n"
    "- Actual (first 200 chars): `{actual}`\n\n"
    "Please re-write the file with the correct content."
)

_VERIFY_FAIL_SHELL_EN = (
    "❌ **Self-Verification Failed**: The shell command returned a "
    "non-zero exit code.\n"
    "- Command: `{command}`\n"
    "- Exit code: `{exit_code}`\n"
    "- Stderr: `{stderr}`\n\n"
    "Please investigate the error and try a different approach."
)

_VERIFY_FAIL_SEARCH_EN = (
    "⚠️ **Self-Verification**: The search returned {count} results, "
    "which may indicate an issue.\n"
    "- Tool: `{tool_name}`\n"
    "- Query: `{query}`\n\n"
    "If zero results is unexpected, try broadening your search or "
    "using a different approach."
)

_VERIFY_PASS_EN = (
    "✅ **Self-Verification Passed**: The `{tool_name}` result looks correct."
)


class SelfVerifier:
    """Verifies agent tool results and provides corrective feedback.

    Usage::

        verifier = SelfVerifier(workspace_dir="/path/to/workspace")
        # After tool call:
        verdict = await verifier.verify(tool_name, tool_input, tool_result)
        if verdict:
            await memory.add(verdict)  # feed back to LLM
    """

    # Tools that modify the filesystem (trigger read-back verification)
    _FILE_WRITE_TOOLS = frozenset({
        "write_file",
        "edit_file",
        "append_file",
    })

    # Tools that execute commands (trigger exit-code verification)
    _SHELL_TOOLS = frozenset({
        "execute_shell_command",
        "execute_python_code",
    })

    # Tools that search (trigger result-count verification)
    _SEARCH_TOOLS = frozenset({
        "grep_search",
        "glob_search",
        "file_search",
    })

    def __init__(
        self,
        workspace_dir: str | Path | None = None,
        enabled: bool | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._enabled = SELF_VERIFY_ENABLED if enabled is None else enabled
        self._max_retries = max_retries or SELF_VERIFY_MAX_RETRIES
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        # Per-tool-call retry counter: {tool_call_id: attempts}
        self._retry_counts: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self._retry_counts.clear()

    async def verify(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None,
        tool_result: dict | str | None,
        tool_call_id: str = "",
    ) -> str | None:
        """Verify a tool result and return corrective feedback if needed.

        Returns:
            An observation string if verification failed, ``None`` if passed
            or verification is not applicable.
        """
        if not self._enabled:
            return None

        # Check retry cap for this specific tool call
        current_retries = self._retry_counts.get(tool_call_id, 0)
        if current_retries >= self._max_retries:
            logger.debug(
                "Self-verify: max retries (%d) reached for %s (call %s)",
                self._max_retries,
                tool_name,
                tool_call_id[:8] if tool_call_id else "?",
            )
            return None

        try:
            if tool_name in self._FILE_WRITE_TOOLS:
                verdict = await self._verify_file_write(tool_input)
            elif tool_name in self._SHELL_TOOLS:
                verdict = await self._verify_shell(tool_result)
            elif tool_name in self._SEARCH_TOOLS:
                verdict = await self._verify_search(tool_name, tool_input, tool_result)
            else:
                return None  # No verification strategy for this tool

            if verdict is not None:
                # Increment retry counter
                self._retry_counts[tool_call_id] = current_retries + 1
                logger.info(
                    "Self-verify: failure for %s (call %s, attempt %d/%d)",
                    tool_name,
                    tool_call_id[:8] if tool_call_id else "?",
                    current_retries + 1,
                    self._max_retries,
                )
                return verdict

            return None
        except Exception:
            logger.warning(
                "Self-verify: unexpected error during verification of %s",
                tool_name,
                exc_info=True,
            )
            return None

    async def _verify_file_write(
        self,
        tool_input: dict[str, Any] | None,
    ) -> str | None:
        """Verify file write by reading back the content."""
        if not tool_input or not self._workspace_dir:
            return None

        file_path_str = tool_input.get("filePath") or tool_input.get("file_path") or ""
        if not file_path_str:
            return None

        file_path = Path(file_path_str)
        if not file_path.is_absolute() and self._workspace_dir:
            file_path = self._workspace_dir / file_path

        expected_content = tool_input.get("content") or tool_input.get("newStr") or ""

        try:
            if not file_path.exists():
                return _VERIFY_FAIL_FILE_EN.format(
                    file_path=str(file_path),
                    expected=expected_content[:200],
                    actual="(file does not exist)",
                )

            actual_content = file_path.read_text(encoding="utf-8", errors="replace")

            # Simple check: expected content should be a substring
            if expected_content and expected_content not in actual_content:
                return _VERIFY_FAIL_FILE_EN.format(
                    file_path=str(file_path),
                    expected=expected_content[:200],
                    actual=actual_content[:200],
                )

            return None  # Passed
        except OSError as exc:
            logger.warning(
                "Self-verify: could not read back %s: %s",
                file_path,
                exc,
            )
            return None

    async def _verify_shell(
        self,
        tool_result: dict | str | None,
    ) -> str | None:
        """Verify shell command by checking exit code."""
        if isinstance(tool_result, str):
            result_text = tool_result
            exit_code = None
            stderr = ""
        elif isinstance(tool_result, dict):
            result_text = str(tool_result.get("output", ""))
            exit_code = tool_result.get("exit_code") or tool_result.get("returncode")
            stderr = str(tool_result.get("stderr", ""))
        else:
            return None

        if exit_code is not None and exit_code != 0:
            command = result_text.split("\n")[0][:200] if result_text else "?"
            return _VERIFY_FAIL_SHELL_EN.format(
                command=command,
                exit_code=exit_code,
                stderr=stderr[:500] if stderr else "(none)",
            )

        return None

    async def _verify_search(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None,
        tool_result: dict | str | None,
    ) -> str | None:
        """Verify search results by checking count."""
        if not tool_input:
            return None

        query = tool_input.get("query") or tool_input.get("pattern") or "?"

        # Count results
        if isinstance(tool_result, dict):
            results = tool_result.get("results") or tool_result.get("matches") or []
            count = len(results)
        elif isinstance(tool_result, str):
            count = 0 if not tool_result.strip() else -1  # -1 = unknown
        else:
            return None

        if count == 0:
            return _VERIFY_FAIL_SEARCH_EN.format(
                count=0,
                tool_name=tool_name,
                query=str(query)[:200],
            )

        return None

    def reset_retry_count(self, tool_call_id: str = "") -> None:
        """Reset retry counter for a specific tool call."""
        if tool_call_id:
            self._retry_counts.pop(tool_call_id, None)
        else:
            self._retry_counts.clear()
