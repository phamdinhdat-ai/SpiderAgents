# -*- coding: utf-8 -*-
"""MCP Simulation Server — basic calculation & utility tools for testing.

Purpose: Provide a lightweight, observable MCP server so you can watch how
OpenSpider agents discover and invoke remote MCP tools at runtime.

Start the server::

    python -m openspider.app.mcp.server.sim_server --port 8100

Then add an MCP client entry in the agent config (via Console UI or
``agent.json``)::

    {
      "calc_sim": {
        "name": "Calculation Simulator",
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8100/mcp",
        "enabled": true
      }
    }

The agent will discover the tools below automatically via ``list_tools()``
and call them during conversations.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from mcp.server import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Calculation Simulator",
    instructions=(
        "A basic MCP server providing arithmetic and utility tools for "
        "testing agent integration.  All tools are stateless and "
        "side-effect-free."
    ),
)


# ---------------------------------------------------------------------------
# Arithmetic tools
# ---------------------------------------------------------------------------


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The sum a + b.
    """
    result = a + b
    logger.info("add(%s, %s) = %s", a, b, result)
    return result


@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract b from a.

    Args:
        a: First number.
        b: Number to subtract.

    Returns:
        The difference a - b.
    """
    result = a - b
    logger.info("subtract(%s, %s) = %s", a, b, result)
    return result


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The product a * b.
    """
    result = a * b
    logger.info("multiply(%s, %s) = %s", a, b, result)
    return result


@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide a by b.

    Args:
        a: Numerator.
        b: Denominator (must not be zero).

    Returns:
        The quotient a / b, or an error message if b is zero.
    """
    if b == 0:
        logger.warning("divide(%s, %s) — division by zero", a, b)
        return "Error: Division by zero"
    result = a / b
    logger.info("divide(%s, %s) = %s", a, b, result)
    return result


# ---------------------------------------------------------------------------
# Utility tools
# ---------------------------------------------------------------------------


@mcp.tool()
def echo(message: str) -> str:
    """Echo the input message back to the caller.

    Useful for verifying that MCP tool round-trips work correctly.

    Args:
        message: Any text string.

    Returns:
        The same text, prefixed with "Echo: ".
    """
    logger.info("echo(%s)", message)
    return f"Echo: {message}"


@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> int:
    """Generate a random integer between min_val and max_val (inclusive).

    Args:
        min_val: Minimum value (default 1).
        max_val: Maximum value (default 100).

    Returns:
        A random integer in [min_val, max_val].
    """
    result = random.randint(min_val, max_val)
    logger.info("random_number(%s, %s) = %s", min_val, max_val, result)
    return result


@mcp.tool()
def current_time() -> str:
    """Return the current server time in ISO-8601 format (UTC).

    Returns:
        ISO-8601 datetime string, e.g. "2026-07-18T12:34:56.789012+00:00".
    """
    result = datetime.now(timezone.utc).isoformat()
    logger.info("current_time() = %s", result)
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI args and start the MCP simulation server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MCP Simulation Server — basic tools for agent testing",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8100,
        help="TCP port to listen on (default: 8100)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="IP address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info(
        "Starting MCP Simulation Server on %s:%s/mcp (transport=streamable-http)",
        args.host,
        args.port,
    )

    # Re-create with the requested host/port so CLI args take effect.
    global mcp  # noqa: PLW0603
    mcp = FastMCP(
        "Calculation Simulator",
        host=args.host,
        port=args.port,
        streamable_http_path="/mcp",
    )

    # Re-register tools on the new instance
    _register_tools()

    mcp.run(transport="streamable-http")


def _register_tools() -> None:
    """Re-register all tools — called after CLI-driven FastMCP re-creation."""
    mcp.tool()(add)
    mcp.tool()(subtract)
    mcp.tool()(multiply)
    mcp.tool()(divide)
    mcp.tool()(echo)
    mcp.tool()(random_number)
    mcp.tool()(current_time)


if __name__ == "__main__":
    main()
