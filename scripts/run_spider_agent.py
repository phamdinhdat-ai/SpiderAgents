#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run SpiderAgent directly from Python — single query or interactive chat.

Usage:
    # Single query (one-shot)
    python scripts/run_spider_agent.py --query "What is the current time?"

    # Interactive chat (REPL loop)
    python scripts/run_spider_agent.py --interactive

    # With a specific agent profile
    python scripts/run_spider_agent.py --agent-id default --query "Hello!"

    # Stream output (shows tool calls and reasoning in real time)
    python scripts/run_spider_agent.py --query "List files in ~/" --stream

    # Headless — no config.json? Set provider + model via env:
    #   OPENAI_API_KEY=sk-... \
    #   OPENSPIDER_ACTIVE_LLM_PROVIDER=openai \
    #   OPENSPIDER_ACTIVE_LLM_MODEL=gpt-4o \
    #   python scripts/run_spider_agent.py --query "Hello!"

Requirements:
    - ``pip install -e ".[dev]"`` (or ``pip install openspider``)
    - A valid ``~/.openspider/config.json`` (run ``openspider init --defaults`` first)
    - API key set via env var (e.g. ``OPENAI_API_KEY``) or config.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import openspider.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from openspider.agents import SpiderAgent
from openspider.config.config import load_agent_config
from openspider.constant import WORKING_DIR
from agentscope.message import Msg

logger = logging.getLogger("spider_agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SpiderAgent from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Single query to send to the agent (one-shot mode).",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Start an interactive REPL chat session.",
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        default="default",
        help="Agent profile ID in config.json (default: 'default').",
    )
    parser.add_argument(
        "--stream", "-s",
        action="store_true",
        help="Enable streaming output (show messages as they arrive).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--workspace-dir",
        type=str,
        default=None,
        help="Override working directory (default: ~/.openspider).",
    )
    return parser.parse_args()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy third-party loggers
    for mod in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
        logging.getLogger(mod).setLevel(logging.WARNING)


def _resolve_model_display(agent_config) -> str:
    """Resolve a human-readable model name for display.

    Checks the agent-specific slot first, then falls back to the
    global ``active_model.json``.
    """
    if agent_config.active_model and agent_config.active_model.provider_id:
        return f"{agent_config.active_model.provider_id}/{agent_config.active_model.model}"
    from openspider.providers.provider_manager import ProviderManager
    global_active = ProviderManager.get_instance().get_active_model()
    if global_active and global_active.provider_id:
        return f"{global_active.provider_id}/{global_active.model} (global)"
    return "NOT CONFIGURED"


def _check_model_configured(agent_config) -> None:
    """Exit with a helpful message if no model is configured anywhere."""
    display = _resolve_model_display(agent_config)
    if display == "NOT CONFIGURED":
        print(
            "\n⚠️  No model configured!\n"
            "   Run one of these first:\n"
            "     openspider models config          (interactive setup)\n"
            "     openspider models set-llm          (pick provider + model)\n\n"
            "   Or set environment variables:\n"
            "     $env:OPENAI_API_KEY = \"sk-...\"\n"
            "     openspider models config-key openai\n"
            "     openspider models set-llm\n",
            file=sys.stderr,
        )
        sys.exit(1)


async def run_single_query(
    agent_id: str,
    query: str,
    workspace_dir: Path | None = None,
    stream: bool = False,
) -> None:
    """Create a SpiderAgent and run a single query.

    Args:
        agent_id: Agent profile ID.
        query: The user's query string.
        workspace_dir: Optional workspace override.
        stream: Whether to print streaming output.
    """
    agent_config = load_agent_config(agent_id)
    wdir = workspace_dir or WORKING_DIR
    _check_model_configured(agent_config)

    logger.info(
        "Creating SpiderAgent (agent_id=%s, model=%s)...",
        agent_id,
        _resolve_model_display(agent_config),
    )

    agent = SpiderAgent(
        agent_config=agent_config,
        workspace_dir=wdir,
        request_context={
            "session_id": "cli-single-query",
            "user_id": "cli-user",
            "channel": "console",
            "agent_id": agent_id,
        },
    )

    messages = [
        Msg(name="user", role="user", content=query),
    ]

    if stream:
        # Enable streaming — print each block as it arrives
        agent.set_console_output_enabled(enabled=True)
        print(f"\n{'─' * 60}")
        print(f"  Query: {query}")
        print(f"{'─' * 60}\n")

    logger.info("Running agent...")
    reply = await agent(messages)

    if stream:
        print(f"\n{'─' * 60}")
        print(f"  Response:")
        print(f"{'─' * 60}\n")

    # Print final response
    content = reply.get_text_content() if reply else "(no response)"
    print(content)


async def run_interactive(
    agent_id: str,
    workspace_dir: Path | None = None,
) -> None:
    """Start an interactive REPL chat with SpiderAgent.

    Args:
        agent_id: Agent profile ID.
        workspace_dir: Optional workspace override.
    """
    agent_config = load_agent_config(agent_id)
    wdir = workspace_dir or WORKING_DIR
    _check_model_configured(agent_config)

    logger.info(
        "Starting interactive SpiderAgent (agent_id=%s, model=%s)...",
        agent_id,
        _resolve_model_display(agent_config),
    )

    agent = SpiderAgent(
        agent_config=agent_config,
        workspace_dir=wdir,
        request_context={
            "session_id": "cli-interactive",
            "user_id": "cli-user",
            "channel": "console",
            "agent_id": agent_id,
        },
    )
    # Disable streaming to avoid double-printing from auto-continue
    # re-reasoning.  We capture and print the final reply ourselves.
    agent.set_console_output_enabled(enabled=False)

    print(f"\n{'=' * 60}")
    print(f"  🕷️  SpiderAgent Interactive Chat")
    print(f"  Agent: {agent_id}  |  Model: {_resolve_model_display(agent_config)}")
    print(f"  Type '/exit' to quit, '/help' for commands")
    print(f"{'=' * 60}\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue

        if query.lower() in ("/exit", "/quit", "/q"):
            print("Goodbye!")
            break

        if query.lower() == "/help":
            print(
                "Commands:\n"
                "  /exit, /quit, /q  — Exit chat\n"
                "  /help             — Show this help\n"
                "  /new              — Start a new conversation\n"
                "  /compact          — Compact conversation memory\n"
            )
            continue

        try:
            messages = [Msg(name="user", role="user", content=query)]
            reply = await agent(messages)
            # Print the final reply (avoiding duplicates from streaming)
            text = reply.get_text_content() if reply else ""
            if text:
                print(f"Agent: {text}")
        except Exception as e:
            print(f"Error: {e}")
            logger.debug("Agent error", exc_info=True)


async def main() -> None:
    args = parse_args()
    _setup_logging(args.verbose)

    workspace_dir = Path(args.workspace_dir).expanduser() if args.workspace_dir else None

    if args.query:
        await run_single_query(
            agent_id=args.agent_id,
            query=args.query,
            workspace_dir=workspace_dir,
            stream=args.stream,
        )
    elif args.interactive:
        await run_interactive(
            agent_id=args.agent_id,
            workspace_dir=workspace_dir,
        )
    else:
        print("Error: specify --query or --interactive.  Use --help for usage.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
