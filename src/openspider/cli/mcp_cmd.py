# -*- coding: utf-8 -*-
"""CLI ``openspider mcp`` — manage MCP server integrations for agents.

MCP (Model Context Protocol) servers provide additional tools to agents
(e.g. web search, filesystem access, database queries).  This command
group lets you configure, validate, and test MCP servers from the CLI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Optional

import click

from ..app.mcp.manager import MCPClientManager
from ..config import get_config_path, load_config, save_config
from ..config.config import Config, MCPClientConfig, MCPConfig
from .utils import prompt_choice, prompt_confirm

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Helpers shared between commands and interactive configuration
# ------------------------------------------------------------------


def _collect_env_vars_interactive() -> dict[str, str]:
    """Loop: prompt KEY=VALUE pairs until the user enters an empty key."""
    env: dict[str, str] = {}
    first = True
    while True:
        if first:
            if not prompt_confirm(
                "Add environment variables?",
                default=False,
            ):
                break
            first = False
        kv = click.prompt(
            "  Env var (KEY=VALUE format, empty to finish)",
            default="",
            show_default=False,
        ).strip()
        if not kv:
            break
        if "=" not in kv:
            click.echo(
                click.style(
                    "  Expected KEY=VALUE format. Skipping.",
                    fg="yellow",
                ),
            )
            continue
        k, v = kv.split("=", 1)
        env[k.strip()] = v.strip()
        click.echo(f"  ✓ {k.strip()} = {v.strip()}")
    return env


def _collect_headers_interactive() -> dict[str, str]:
    """Loop: prompt Header-Name=Value pairs until the user enters empty."""
    headers: dict[str, str] = {}
    first = True
    while True:
        if first:
            if not prompt_confirm(
                "Add HTTP headers?",
                default=False,
            ):
                break
            first = False
        kv = click.prompt(
            "  Header (Name=Value format, empty to finish)",
            default="",
            show_default=False,
        ).strip()
        if not kv:
            break
        if "=" not in kv:
            click.echo(
                click.style(
                    "  Expected Name=Value format. Skipping.",
                    fg="yellow",
                ),
            )
            continue
        k, v = kv.split("=", 1)
        headers[k.strip()] = v.strip()
        click.echo(f"  ✓ {k.strip()} = {v.strip()}")
    return headers


def _make_client_key(name: str) -> str:
    """Derive a config-key from a human name (lowercase, underscore)."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _build_client_data(
    key: str,
    name: str,
    transport: str,
    command: str = "",
    args: list[str] | None = None,
    url: str = "",
    description: str = "",
    env: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    enabled: bool = True,
) -> MCPClientConfig:
    """Build and validate an ``MCPClientConfig`` from component parts."""
    data: dict = {
        "name": name,
        "description": description,
        "enabled": enabled,
        "transport": transport,
        "command": command,
        "args": args or [],
        "url": url,
        "env": env or {},
        "headers": headers or {},
    }
    return MCPClientConfig.model_validate(data)


def _add_client_to_config(
    config: Config,
    key: str,
    client: MCPClientConfig,
) -> None:
    """Add/overwrite an MCP client in config, warning on overwrite."""
    if key in config.mcp.clients:
        click.echo(
            click.style(
                f"⚠ Key '{key}' already exists — overwriting.",
                fg="yellow",
            ),
        )
    config.mcp.clients[key] = client


# ------------------------------------------------------------------
# configure_mcp_interactive — reusable by init_cmd
# ------------------------------------------------------------------


def configure_mcp_interactive(config: Config) -> None:
    """Interactively add MCP clients to *config* (in place).

    Called by ``openspider init`` after channels configuration.
    The caller is responsible for saving the config afterwards.
    """
    click.echo("\n=== MCP Server Configuration ===")
    click.echo(
        "MCP servers provide additional tools to agents "
        "(web search, filesystem, databases, etc.).",
    )

    while True:
        key = click.prompt(
            "  Config key (identifier, e.g. 'tavily_search')",
            default="",
            show_default=False,
        ).strip()
        if not key:
            break

        name = click.prompt(
            "  Display name",
            default=key,
            show_default=True,
        ).strip()

        transport = prompt_choice(
            "  Transport type:",
            options=["stdio", "streamable_http", "sse"],
            default="stdio",
        )

        command = ""
        args: list[str] = []
        env: dict[str, str] = {}
        url = ""
        headers: dict[str, str] = {}

        if transport == "stdio":
            command = click.prompt(
                "  Command (e.g. 'npx', 'uvx', 'python')",
                default="npx",
            ).strip()
            args_str = click.prompt(
                "  Arguments (comma-separated, e.g. '-y,tavily-mcp@latest')",
                default="-y,tavily-mcp@latest",
            ).strip()
            if args_str:
                args = [a.strip() for a in args_str.split(",") if a.strip()]
            env = _collect_env_vars_interactive()
        else:
            url = click.prompt(
                "  URL (e.g. 'http://localhost:8080/mcp')",
                default="http://localhost:8080/mcp",
            ).strip()
            headers = _collect_headers_interactive()

        description = click.prompt(
            "  Description (optional)",
            default="",
            show_default=False,
        ).strip()

        enabled = not prompt_confirm(
            "  Create as disabled?",
            default=False,
        )

        try:
            client = _build_client_data(
                key=key,
                name=name,
                transport=transport,
                command=command,
                args=args,
                url=url,
                description=description,
                env=env,
                headers=headers,
                enabled=enabled,
            )
        except Exception as exc:
            click.echo(
                click.style(
                    f"  ✗ Validation failed: {exc}",
                    fg="red",
                ),
            )
            continue

        _add_client_to_config(config, key, client)
        click.echo(f"  ✓ MCP client '{key}' configured.")
        click.echo()
        if not prompt_confirm("Add another MCP client?", default=False):
            break

    click.echo("MCP server configuration complete.")


# ------------------------------------------------------------------
# mcp_group
# ------------------------------------------------------------------


@click.group("mcp")
def mcp_group() -> None:
    """Manage MCP (Model Context Protocol) server integrations.

    MCP servers provide additional tools to agents (e.g., web search,
    filesystem access, database queries).  Configure stdio or HTTP/SSE
    MCP servers here.
    """


# ---------------------------------------------------------------
# list
# ---------------------------------------------------------------


@mcp_group.command("list")
def mcp_list() -> None:
    """List configured MCP clients."""
    cfg = load_config(get_config_path())
    clients = cfg.mcp.clients

    if not clients:
        click.echo("No MCP clients configured.")
        return

    click.echo()
    # Header
    click.echo(
        f"  {'Key':<24s} {'Name':<20s} {'Transport':<18s} "
        f"{'Status':<10s} {'Endpoint'}",
    )
    click.echo(f"  {'─' * 96}")
    for key, client in clients.items():
        status = (
            click.style("Enabled", fg="green")
            if client.enabled
            else click.style("Disabled", fg="yellow")
        )
        endpoint = (
            client.command if client.transport == "stdio" else client.url
        )
        if len(endpoint) > 32:
            endpoint = endpoint[:29] + "..."
        click.echo(
            f"  {key:<24s} {client.name:<20s} {client.transport:<18s} "
            f"{status:<16s} {endpoint}",
        )
    click.echo()


# ---------------------------------------------------------------
# add
# ---------------------------------------------------------------


@mcp_group.command("add")
@click.option(
    "--key", "-k",
    default=None,
    help="Config key (identifier, e.g. 'tavily_search')",
)
@click.option(
    "--name", "-n",
    default=None,
    help="Human-readable display name",
)
@click.option(
    "--transport", "-t",
    type=click.Choice(["stdio", "streamable_http", "sse"]),
    default=None,
    help="Transport type",
)
@click.option(
    "--command", "-c",
    default=None,
    help="Executable command (for stdio transport)",
)
@click.option(
    "--args", "-a",
    multiple=True,
    default=None,
    help="Command arguments (repeatable, for stdio transport)",
)
@click.option(
    "--url", "-u",
    default=None,
    help="Server URL (for HTTP/SSE transport)",
)
@click.option(
    "--description", "-d",
    default=None,
    help="Optional description",
)
@click.option(
    "--env", "-e",
    multiple=True,
    default=None,
    help="Env vars KEY=VALUE (repeatable, mainly for stdio)",
)
@click.option(
    "--header",
    "headers",
    multiple=True,
    default=None,
    help="HTTP headers Name=Value (repeatable, for HTTP/SSE)",
)
@click.option(
    "--disabled",
    is_flag=True,
    default=False,
    help="Create as disabled",
)
# pylint: disable=too-many-arguments,too-many-locals
def mcp_add(
    key: str | None,
    name: str | None,
    transport: str | None,
    command: str | None,
    args: tuple[str, ...] | None,
    url: str | None,
    description: str | None,
    env: tuple[str, ...] | None,
    headers: tuple[str, ...] | None,
    disabled: bool,
) -> None:
    """Add a new MCP client.

    If no options are provided, enters interactive mode.
    """
    cfg = load_config(get_config_path())

    has_cli_options = any(
        x is not None and x not in ((), "")
        for x in (key, name, transport, command, args, url, description)
    ) or disabled or bool(env or headers)

    if has_cli_options:
        _add_from_options(
            cfg,
            key=key,
            name=name,
            transport=transport,
            command=command,
            args=list(args) if args else [],
            url=url,
            description=description or "",
            env_tuple=env or (),
            headers_tuple=headers or (),
            disabled=disabled,
        )
    else:
        configure_mcp_interactive(cfg)

    save_config(cfg, get_config_path())
    click.echo("✓ MCP client configuration saved.")


def _add_from_options(
    cfg: Config,
    *,
    key: str | None,
    name: str | None,
    transport: str | None,
    command: str | None,
    args: list[str] | None,
    url: str | None,
    description: str,
    env_tuple: tuple[str, ...],
    headers_tuple: tuple[str, ...],
    disabled: bool,
) -> None:
    """Add MCP client from explicit CLI options."""
    # Transport: default to stdio if command given, else streamable_http
    if transport is None:
        transport = "stdio" if command and not url else "streamable_http"

    if name is None:
        name = key or "mcp_client"

    if key is None:
        key = _make_client_key(name)

    # Parse env vars from KEY=VALUE tuples
    env_dict: dict[str, str] = {}
    for ev in env_tuple:
        if "=" in ev:
            k, v = ev.split("=", 1)
            env_dict[k.strip()] = v.strip()

    # Parse headers from Name=Value tuples
    headers_dict: dict[str, str] = {}
    for hv in headers_tuple:
        if "=" in hv:
            k, v = hv.split("=", 1)
            headers_dict[k.strip()] = v.strip()

    try:
        client = _build_client_data(
            key=key,
            name=name,
            transport=transport,
            command=command or "",
            args=args or [],
            url=url or "",
            description=description,
            env=env_dict,
            headers=headers_dict,
            enabled=not disabled,
        )
    except Exception as exc:
        raise click.ClickException(
            f"Invalid MCP client configuration: {exc}",
        ) from exc

    _add_client_to_config(cfg, key, client)
    click.echo(f"✓ Added MCP client: {key}")


# ---------------------------------------------------------------
# edit
# ---------------------------------------------------------------


@mcp_group.command("edit")
@click.argument("key")
@click.option(
    "--name", "-n",
    default=None,
    help="New display name",
)
@click.option(
    "--transport", "-t",
    type=click.Choice(["stdio", "streamable_http", "sse"]),
    default=None,
    help="New transport type",
)
@click.option(
    "--command", "-c",
    default=None,
    help="New command (for stdio transport)",
)
@click.option(
    "--args", "-a",
    multiple=True,
    default=None,
    help="New command args (repeatable, replaces all args)",
)
@click.option(
    "--url", "-u",
    default=None,
    help="New URL (for HTTP/SSE transport)",
)
@click.option(
    "--description", "-d",
    default=None,
    help="New description",
)
@click.option(
    "--env", "-e",
    multiple=True,
    default=None,
    help="New env vars KEY=VALUE (repeatable, replaces all env)",
)
@click.option(
    "--header",
    "headers",
    multiple=True,
    default=None,
    help="New HTTP headers Name=Value (repeatable, replaces all headers)",
)
@click.option(
    "--enable/--disable",
    default=None,
    help="Enable or disable the client",
)
# pylint: disable=too-many-arguments,too-many-locals,too-many-branches
def mcp_edit(
    key: str,
    name: str | None,
    transport: str | None,
    command: str | None,
    args: tuple[str, ...] | None,
    url: str | None,
    description: str | None,
    env: tuple[str, ...] | None,
    headers: tuple[str, ...] | None,
    enable: bool | None,
) -> None:
    """Edit an existing MCP client configuration.

    KEY is the config identifier (use 'mcp list' to see keys).
    Any provided options override the current value; omitted options are
    left unchanged.
    """
    cfg = load_config(get_config_path())

    if key not in cfg.mcp.clients:
        existing_keys = ", ".join(sorted(cfg.mcp.clients.keys())) or "(none)"
        raise click.ClickException(
            f"MCP client '{key}' not found.\n"
            f"Existing keys: {existing_keys}\n"
            f"Use 'openspider mcp list' to see configured clients.",
        )

    client = cfg.mcp.clients[key]

    # Determine if interactive or CLI-option based
    has_cli_options = any(
        x is not None and x not in ((), "")
        for x in (name, transport, command, args, url, description)
    ) or enable is not None or bool(env or headers)

    if has_cli_options:
        if name is not None:
            client.name = name
        if transport is not None:
            client.transport = transport  # type: ignore[assignment]
        if command is not None:
            client.command = command
        if args is not None:
            client.args = list(args)
        if url is not None:
            client.url = url
        if description is not None:
            client.description = description
        if env is not None:
            env_dict: dict[str, str] = {}
            for ev in env:
                if "=" in ev:
                    k, v = ev.split("=", 1)
                    env_dict[k.strip()] = v.strip()
            client.env = env_dict
        if headers is not None:
            headers_dict: dict[str, str] = {}
            for hv in headers:
                if "=" in hv:
                    k, v = hv.split("=", 1)
                    headers_dict[k.strip()] = v.strip()
            client.headers = headers_dict
        if enable is not None:
            client.enabled = enable
        click.echo(f"✓ Updated MCP client: {key}")
    else:
        _edit_interactive(cfg, key, client)

    # Re-validate after changes
    try:
        # Reconstruct to trigger validators
        MCPClientConfig.model_validate(client.model_dump())
    except Exception as exc:
        raise click.ClickException(
            f"Invalid MCP client configuration after edit: {exc}",
        ) from exc

    save_config(cfg, get_config_path())
    click.echo("✓ MCP client configuration saved.")


def _edit_interactive(
    cfg: Config,
    key: str,
    client: MCPClientConfig,
) -> None:
    """Edit an MCP client interactively."""
    click.echo(f"\nEditing MCP client: {key}")
    click.echo(f"  Current: name={client.name}, transport={client.transport}, "
                f"enabled={client.enabled}")

    client.name = click.prompt(
        "  Display name",
        default=client.name,
        show_default=True,
    ).strip()

    client.transport = prompt_choice(  # type: ignore[assignment]
        "  Transport type:",
        options=["stdio", "streamable_http", "sse"],
        default=client.transport,
    )

    if client.transport == "stdio":
        client.command = click.prompt(
            "  Command",
            default=client.command,
            show_default=True,
        ).strip()
        args_str = click.prompt(
            "  Arguments (comma-separated)",
            default=",".join(client.args),
            show_default=True,
        ).strip()
        client.args = (
            [a.strip() for a in args_str.split(",") if a.strip()]
            if args_str else []
        )
        if prompt_confirm("Edit environment variables?", default=False):
            client.env = _collect_env_vars_interactive()
    else:
        client.url = click.prompt(
            "  URL",
            default=client.url,
            show_default=True,
        ).strip()
        if prompt_confirm("Edit HTTP headers?", default=False):
            client.headers = _collect_headers_interactive()

    client.description = click.prompt(
        "  Description",
        default=client.description,
        show_default=True,
    ).strip()

    client.enabled = not prompt_confirm(
        "  Disable this client?",
        default=not client.enabled,
    )

    click.echo(f"✓ Updated MCP client: {key}")


# ---------------------------------------------------------------
# delete
# ---------------------------------------------------------------


@mcp_group.command("delete")
@click.argument("key")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def mcp_delete(key: str, yes: bool) -> None:
    """Delete an MCP client configuration.

    KEY is the config identifier (use 'mcp list' to see keys).
    """
    cfg = load_config(get_config_path())

    if key not in cfg.mcp.clients:
        existing_keys = ", ".join(sorted(cfg.mcp.clients.keys())) or "(none)"
        raise click.ClickException(
            f"MCP client '{key}' not found.\n"
            f"Existing keys: {existing_keys}\n"
            f"Use 'openspider mcp list' to see configured clients.",
        )

    client = cfg.mcp.clients[key]
    if not yes:
        click.echo(f"\n  Key:         {key}")
        click.echo(f"  Name:        {client.name}")
        click.echo(f"  Transport:   {client.transport}")
        click.echo(f"  Status:      "
                    f"{'Enabled' if client.enabled else 'Disabled'}")
        if not prompt_confirm(
            f"\nDelete MCP client '{key}'?",
            default=False,
        ):
            click.echo("Cancelled.")
            return

    del cfg.mcp.clients[key]
    save_config(cfg, get_config_path())
    click.echo(f"✓ Deleted MCP client: {key}")


# ---------------------------------------------------------------
# check
# ---------------------------------------------------------------


@mcp_group.command("check")
def mcp_check() -> None:
    """Validate MCP client configurations (no live connections).

    Checks: command exists on PATH (stdio), URL format (HTTP/SSE),
    transport-specific required fields.
    """
    cfg = load_config(get_config_path())
    clients = cfg.mcp.clients

    if not clients:
        click.echo("No MCP clients configured.")
        return

    problems = _mcp_check_clients(clients)
    if not problems:
        click.echo(
            click.style(
                f"✓ All {len(clients)} MCP client(s) pass config checks.",
                fg="green",
            ),
        )
    else:
        click.echo()
        for problem in problems:
            click.echo(f"  ⚠ {problem}")

        ok_count = len(clients) - len(
            {p.split(" ")[0].split(":")[0] for p in problems},
        )
        click.echo(
            click.style(
                f"\n{len(problems)} warning(s). "
                f"Run 'openspider mcp test <key>' to test live connections.",
                fg="yellow",
            ),
        )


def _mcp_check_clients(clients: dict[str, MCPClientConfig]) -> list[str]:
    """Return a list of warning strings for invalid MCP client configs."""
    problems: list[str] = []
    for cid, client in clients.items():
        if not client.enabled:
            continue
        if client.transport == "stdio":
            cmd0 = (client.command or "").strip().split()
            if not cmd0:
                problems.append(
                    f"{cid}: stdio command is empty",
                )
                continue
            exe = cmd0[0]
            if not shutil.which(exe):
                problems.append(
                    f"{cid}: stdio executable '{exe}' not found on PATH",
                )
        elif client.transport in ("streamable_http", "sse"):
            u = (client.url or "").strip()
            if not u:
                problems.append(
                    f"{cid}: {client.transport} URL is empty",
                )
            elif not (u.startswith("http://") or u.startswith("https://")):
                problems.append(
                    f"{cid}: URL does not look like http(s)://...",
                )
    return problems


# ---------------------------------------------------------------
# test
# ---------------------------------------------------------------


@mcp_group.command("test")
@click.argument("key")
@click.option(
    "--timeout",
    default=30.0,
    type=float,
    help="Connection timeout in seconds (default: 30)",
)
def mcp_test(key: str, timeout: float) -> None:
    """Test a live connection to an MCP server and list available tools.

    KEY is the config identifier (use 'mcp list' to see keys).
    """
    cfg = load_config(get_config_path())

    if key not in cfg.mcp.clients:
        existing_keys = ", ".join(sorted(cfg.mcp.clients.keys())) or "(none)"
        raise click.ClickException(
            f"MCP client '{key}' not found.\n"
            f"Existing keys: {existing_keys}\n"
            f"Use 'openspider mcp list' to see configured clients.",
        )

    client_config = cfg.mcp.clients[key]
    if not client_config.enabled:
        click.echo(
            click.style(
                f"⚠ MCP client '{key}' is disabled. Enable it first "
                f"('openspider mcp edit {key} --enable').",
                fg="yellow",
            ),
        )
        return

    click.echo(f"\nTesting MCP client: {key}")
    click.echo(f"  Name:      {client_config.name}")
    click.echo(f"  Transport: {client_config.transport}")
    click.echo(f"  Endpoint:  "
                f"{client_config.command if client_config.transport == 'stdio' else client_config.url}")

    try:
        result = asyncio.run(
            _test_mcp_connection(client_config, timeout),
        )
        tools = result.get("tools", [])
        if not tools:
            click.echo(
                click.style(
                    "\n✓ Connection successful, but no tools returned.",
                    fg="green",
                ),
            )
        else:
            click.echo(
                click.style(
                    f"\n✓ Connection successful! {len(tools)} tool(s) available:\n",
                    fg="green",
                ),
            )
            for tool in tools:
                desc = getattr(tool, "description", "") or ""
                click.echo(f"  • {tool.name}")
                if desc:
                    click.echo(f"    {desc}")
            click.echo()
    except asyncio.TimeoutError:
        raise click.ClickException(
            f"Connection timed out after {timeout:.0f}s.\n"
            f"Check that the MCP server is running and reachable.",
        )
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(
            f"Connection failed: {exc}\n"
            f"Run 'openspider mcp check' to validate the configuration.",
        ) from exc


async def _test_mcp_connection(
    client_config: MCPClientConfig,
    timeout: float,
) -> dict:
    """Build, connect, list tools, and disconnect from an MCP server.

    Args:
        client_config: Validated MCP client configuration.
        timeout: Connection timeout in seconds.

    Returns:
        ``{"tools": [...]}`` on success.

    Raises:
        RuntimeError, asyncio.TimeoutError, or transport errors on failure.
    """
    client = MCPClientManager._build_client(client_config)  # pylint: disable=protected-access

    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
    except BaseException:
        # Ensure cleanup on failed connect
        try:
            await client.close(ignore_errors=True)
        except Exception:
            pass
        raise

    try:
        tools = await client.list_tools()
        return {"tools": list(tools)}
    finally:
        await client.close(ignore_errors=True)
