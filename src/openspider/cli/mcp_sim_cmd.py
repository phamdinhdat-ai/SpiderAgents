# -*- coding: utf-8 -*-
"""CLI ``openspider mcp-sim`` — start a local MCP simulation server."""

from __future__ import annotations

import click


@click.command("mcp-sim")
@click.option(
    "--port",
    default=8100,
    type=int,
    help="TCP port to listen on (default: 8100)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    type=str,
    help="IP address to bind to (default: 127.0.0.1)",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Logging level (default: INFO)",
)
def mcp_sim_cmd(port: int, host: str, log_level: str) -> None:
    """Start a local MCP simulation server for testing agent integration.

    The server exposes basic calculation and utility tools (add, subtract,
    multiply, divide, echo, random_number, current_time) via streamable
    HTTP transport.

    After starting, configure an MCP client in the agent pointing to
    ``http://HOST:PORT/mcp`` with transport ``streamable_http``.

    \b
    Examples:
        openspider mcp-sim
        openspider mcp-sim --port 9000
        openspider mcp-sim --host 0.0.0.0 --port 8100 --log-level DEBUG
    """
    import sys

    from ..app.mcp.server.sim_server import main as sim_main

    # Forward CLI args to the sim server's argparse entry point
    sys.argv = [
        "mcp-sim",
        "--port", str(port),
        "--host", host,
        "--log-level", log_level,
    ]
    sim_main()
