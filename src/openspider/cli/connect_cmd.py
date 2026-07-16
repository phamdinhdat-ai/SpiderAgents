# -*- coding: utf-8 -*-
"""``openspider connect`` — manage the CLI's server connection.

When connected, all CLI commands route through the remote server at the
configured URL.  When disconnected, the CLI uses the local agent runtime
(no server needed).
"""
from __future__ import annotations

from typing import Optional

import click

from .connection import (
    clear_connection,
    get_connection,
    is_connected,
    set_connection,
)
from .http import is_server_running as _tcp_check


@click.group("connect")
def connect_group() -> None:
    """Manage the server connection for CLI commands.

    \b
    When connected, all CLI commands route through the remote
    server.  When disconnected, the CLI uses the local agent
    runtime (no server — tools, MCP, skills run locally).
    """


@connect_group.command("to")
@click.option(
    "--url",
    required=True,
    help="Server URL, e.g. http://192.168.1.100:8088",
)
@click.option(
    "--agent-id",
    default="default",
    show_default=True,
    help="Default agent ID to use when talking to the server.",
)
def connect_to(url: str, agent_id: str) -> None:
    """Connect the CLI to a running OpenSpider server.

    \b
    All subsequent commands (repl, agents chat, cron, etc.) will
    route through this server instead of running locally.

    \b
    Examples:
      openspider connect to --url http://192.168.1.100:8088
      openspider connect to --url http://localhost:9090 --agent-id research
    """
    url = url.rstrip("/")

    # Quick connectivity check
    click.echo("Checking connectivity ... ", nl=False)
    try:
        import httpx
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{url}/api/health")
            r.raise_for_status()
    except Exception as exc:
        click.echo(click.style("✗", fg="red"))
        raise click.ClickException(
            f"Cannot reach server at {url}.\n"
            f"  Error: {exc}\n"
            f"  Make sure the server is running: openspider app\n"
        ) from exc

    click.echo(click.style("✓", fg="green"))

    info = set_connection(url, agent_id)
    click.echo(
        f"✓ Connected to {click.style(url, fg='cyan')}\n"
        f"  Agent: {agent_id}\n"
        f"  All CLI commands will now route through this server.\n"
        f"  Use {click.style('openspider connect disconnect', fg='yellow')}"
        f" to return to local mode."
    )


@connect_group.command("disconnect")
def connect_disconnect() -> None:
    """Disconnect from the server and return to local mode.

    \b
    All subsequent CLI commands will use the local agent runtime
    (tools, MCP, skills run locally — no server needed).
    """
    if not is_connected():
        click.echo("Already disconnected (local mode).")
        return

    clear_connection()
    click.echo("✓ Disconnected — CLI is now in local mode.")


@connect_group.command("status")
def connect_status() -> None:
    """Show the current connection state."""
    if not is_connected():
        click.echo("Mode: local (no server connected)")
        click.echo("  All commands run from local config and files.")
        click.echo(
            f"  Connect to a server with: "
            f"{click.style('openspider connect to --url <url>', fg='yellow')}",
        )
        return

    info = get_connection()
    if info is None:
        click.echo("Mode: local (no server connected)")
        return

    click.echo(
        f"Mode: {click.style('connected', fg='green')}\n"
        f"  URL:      {click.style(info.url, fg='cyan')}\n"
        f"  Agent:    {info.agent_id}\n"
        f"  Since:    {info.connected_at}"
    )

    # Quick liveness check
    try:
        from urllib.parse import urlparse
        parsed = urlparse(info.url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8088
        if _tcp_check(host, port, timeout=1.0):
            click.echo(f"  Status:   {click.style('reachable ✓', fg='green')}")
        else:
            click.echo(f"  Status:   {click.style('unreachable ✗', fg='red')}")
    except Exception:
        pass
