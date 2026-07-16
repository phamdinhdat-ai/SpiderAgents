## -*- coding: utf-8 -*-
"""Local agent runtime — creates and manages SpiderAgent without a server.

The :class:`LocalAgentSession` encapsulates the full agent lifecycle:
loading config, initializing MCP clients, registering tools and skills,
and running the ReAct loop — all from local files.  This is the
foundation for serverless ``openspider repl`` and ``openspider agents chat``.

Reference: :func:`task_cmd._run_task` demonstrates the pattern this
module generalises (adding MCP support and session reuse).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from ..agents.react_agent import SpiderAgent
from ..app.mcp.manager import MCPClientManager
from ..config.config import load_agent_config

logger = logging.getLogger(__name__)

# Logger names to suppress during interactive chat so raw ReAct loop
# messages don't pollute the REPL display.
_AGENT_LOG_SUPPRESS = frozenset({
    "openspider.agents.react_agent",
    "openspider.agents",
    "openspider.providers",
    "openspider.app.runner",
})


class _SuppressAgentLogs:
    """Context manager that temporarily raises log levels for agent modules."""

    def __init__(self, level: int = logging.WARNING):
        self._level = level
        self._saved: dict[str, int] = {}

    def __enter__(self):
        for name in _AGENT_LOG_SUPPRESS:
            lg = logging.getLogger(name)
            self._saved[name] = lg.level
            lg.setLevel(self._level)
        return self

    def __exit__(self, *args):
        for name, lvl in self._saved.items():
            logging.getLogger(name).setLevel(lvl)


class LocalAgentSession:
    """Creates and manages a local SpiderAgent instance.

    Loads agent config, MCP clients, skills, and tools from local
    files — no server required.  Wraps the async lifecycle so CLI
    commands can use it synchronously via ``asyncio.run()``.

    Usage::

        session = LocalAgentSession(agent_id="default")
        await session.start()
        try:
            reply = await session.chat("Hello, what can you do?")
            print(reply)
        finally:
            await session.stop()
    """

    def __init__(self, agent_id: str = "default") -> None:
        self.agent_id = agent_id
        self.agent: SpiderAgent | None = None
        self._mcp_manager: MCPClientManager | None = None
        self._started = False
        # Limit ReAct iterations in interactive mode to prevent
        # runaway auto-continue loops.
        self._interactive_max_iters = 30

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize agent, MCP clients, tools, and skills.

        Steps:

        1. Load agent config from ``workspace/<id>/agent.json``
        2. Initialize MCP clients from config (both stdio & HTTP)
        3. Create ``SpiderAgent`` with MCP clients and workspace
        4. Capped max_iters for interactive mode
        5. Register MCP tools on the agent's toolkit
        """
        if self._started:
            return

        # 1. Load agent config from local files
        agent_config = load_agent_config(self.agent_id)

        # Cap max_iters to prevent runaway auto-continue in interactive mode
        original_max = agent_config.running.max_iters
        if original_max > self._interactive_max_iters:
            agent_config.running.max_iters = self._interactive_max_iters
            logger.info(
                "Capped max_iters from %d to %d for interactive mode",
                original_max,
                self._interactive_max_iters,
            )

        # 2. Initialize MCP clients from agent config
        mcp_clients: list[Any] = []
        if agent_config.mcp:
            self._mcp_manager = MCPClientManager()
            try:
                await self._mcp_manager.init_from_config(agent_config.mcp)
                mcp_clients = await self._mcp_manager.get_clients()
                if mcp_clients:
                    logger.info(
                        "Loaded %d MCP client(s) for agent '%s'",
                        len(mcp_clients),
                        self.agent_id,
                    )
            except Exception:
                logger.warning(
                    "Failed to load some MCP clients for agent '%s'",
                    self.agent_id,
                    exc_info=True,
                )

        # 3. Resolve workspace directory
        workspace_dir: Path | None = None
        if agent_config.workspace_dir:
            workspace_dir = Path(agent_config.workspace_dir).expanduser()

        # 4. Create SpiderAgent
        self.agent = SpiderAgent(
            agent_config=agent_config,
            mcp_clients=mcp_clients,
            workspace_dir=workspace_dir,
            request_context={
                "channel": "cli",
                "user_id": "cli-user",
                "agent_id": self.agent_id,
            },
        )

        # 5. Register MCP tools (must be called after super().__init__)
        if mcp_clients:
            await self.agent.register_mcp_clients()

        self._started = True
        logger.info(
            "Local agent '%s' started (model: %s)",
            self.agent_id,
            agent_config.active_model.model
            if agent_config.active_model
            else "default",
        )

    async def stop(self) -> None:
        """Close MCP clients and clean up resources."""
        if self._mcp_manager is not None:
            try:
                await self._mcp_manager.close_all()
            except Exception:
                logger.debug(
                    "Error closing MCP clients",
                    exc_info=True,
                )
        self._started = False

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(self, text: str) -> str:
        """Send a message to the agent and return the response text.

        Args:
            text: The user's message.

        Returns:
            The agent's plain-text response.
        """
        if not self._started or self.agent is None:
            raise RuntimeError(
                "Session not started. Call session.start() first.",
            )

        from agentscope.message import Msg

        response = await self.agent.reply(
            [Msg(name="user", role="user", content=text)],
        )
        return response.get_text_content() if response else ""

    async def chat_with_timeout(
        self,
        text: str,
        timeout: float = 300.0,
        *,
        progress_callback=None,
    ) -> dict[str, Any]:
        """Send a message with a timeout, returning a structured result.

        Log output from the agent loop is suppressed so it doesn't
        clutter the interactive REPL display.

        Args:
            text: The user's message.
            timeout: Maximum seconds to wait for a response.
            progress_callback: Optional ``callable(str)`` invoked with
                progress messages (e.g. "thinking...", "auto-continue").

        Returns:
            ``{"status": "success"|"timeout"|"error",
            "response": "...", "elapsed_seconds": ...}``
        """
        import time

        if not self._started or self.agent is None:
            return {
                "status": "error",
                "response": "",
                "error": "Session not started",
            }

        from agentscope.message import Msg

        t0 = time.monotonic()
        with _SuppressAgentLogs(logging.WARNING):
            try:
                response = await asyncio.wait_for(
                    self.agent.reply(
                        [Msg(name="user", role="user", content=text)],
                    ),
                    timeout=timeout,
                )
                elapsed = time.monotonic() - t0
                return {
                    "status": "success",
                    "elapsed_seconds": round(elapsed, 2),
                    "response": response.get_text_content() if response else "",
                }
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t0
                return {
                    "status": "timeout",
                    "elapsed_seconds": round(elapsed, 2),
                    "timeout_seconds": timeout,
                    "response": "",
                }
            except Exception as exc:
                elapsed = time.monotonic() - t0
                return {
                    "status": "error",
                    "elapsed_seconds": round(elapsed, 2),
                    "error": str(exc),
                    "response": "",
                }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def is_started(self) -> bool:
        """Return ``True`` if :meth:`start` has completed successfully."""
        return self._started
