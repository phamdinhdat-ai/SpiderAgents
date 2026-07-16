# -*- coding: utf-8 -*-
"""``openspider repl`` — Interactive REPL chat with agents.

Provides a persistent read-eval-print loop that connects to the running
OpenSpider FastAPI server and streams agent responses in real time.
Built-in tools and MCP tools are invoked automatically by the agent as
needed — no extra CLI configuration required.

Usage::

    openspider repl                       # default agent
    openspider repl --agent-id research   # specific agent
    openspider repl --user-id alice       # named user identity
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from typing import Any, Optional

import click

from ..agents.tools.agent_management import (
    build_agent_chat_request,
    create_agent_api_client,
    parse_agent_sse_line,
)
from .http import resolve_base_url

# ── ANSI colour / style helpers ─────────────────────────────────────────


def _style(text: str, fg: str = "") -> str:
    """Apply ANSI colour if stdout supports it, otherwise return plain."""
    if not sys.stdout.isatty():
        return text
    codes = {
        "green": "\x1b[32m",
        "cyan": "\x1b[36m",
        "yellow": "\x1b[33m",
        "red": "\x1b[31m",
        "bold": "\x1b[1m",
        "dim": "\x1b[2m",
        "reset": "\x1b[0m",
    }
    prefix = codes.get(fg, "")
    if not prefix:
        return text
    return f"{prefix}{text}{codes['reset']}"


def _agent_label(agent_id: str) -> str:
    """Formatted agent prompt label."""
    return _style(f"({agent_id})", fg="cyan")


def _user_label(user_id: str) -> str:
    """Formatted user prompt label."""
    return _style(f"({user_id})", fg="green")


def _timestamp() -> str:
    """Compact timestamp string."""
    return datetime.now().strftime("%H:%M:%S")


def _print_separator() -> None:
    """Print a horizontal rule across the terminal."""
    cols = shutil.get_terminal_size((80, 20)).columns
    click.echo(_style("─" * cols, fg="dim"))


# ── Helpers ─────────────────────────────────────────────────────────────


def _show_help() -> None:
    """Print in-session help text."""
    click.echo()
    click.echo("  Interactive Agent Chat — Commands")
    click.echo("  " + "─" * 40)
    click.echo(f"  {_style('/exit', fg='bold')}    or {_style('Ctrl+C', fg='bold')}  Exit the REPL")
    click.echo(f"  {_style('/clear', fg='bold')}   Clear the screen")
    click.echo(f"  {_style('/help', fg='bold')}    Show this help message")
    click.echo(f"  {_style('/new', fg='bold')}     Start a fresh conversation (new session)")
    click.echo(f"  {_style('/tools', fg='bold')}   List available tools (built-in + MCP)")
    click.echo()
    click.echo("  Any other input is sent to the agent and the response")
    click.echo("  is streamed back in real time. The agent can invoke")
    click.echo("  built-in tools and MCP tools automatically.")
    click.echo()


def _clear_screen() -> None:
    """Clear the terminal."""
    click.clear()


def _is_special_command(text: str) -> bool:
    """Return True if *text* is a built-in REPL command."""
    return text.strip().startswith("/")


def _handle_special_command(
    text: str,
    agent_id: str,
    session_id: list[str],
    base_url: str = "",
) -> bool:
    """Handle a special command.  Return True to continue, False to exit."""
    cmd = text.strip().lower()
    if cmd in ("/exit", "/quit"):
        return False
    if cmd == "/clear":
        _clear_screen()
        return True
    if cmd == "/help":
        _show_help()
        return True
    if cmd == "/new":
        session_id[0] = ""
        click.echo(_style("✦ New conversation started.", fg="cyan"))
        return True
    if cmd.startswith("/tools"):
        _show_available_tools(base_url, agent_id)
        return True
    return True  # unknown command, just continue


def _show_available_tools(base_url: str, agent_id: str) -> None:
    """Fetch and display tools available to the agent (built-in + MCP)."""
    click.echo()
    click.echo(_style(f"  Available Tools for agent '{agent_id}'", fg="bold"))
    click.echo("  " + "─" * 40)

    try:
        with create_agent_api_client(base_url) as client:
            r = client.get(f"/agents/{agent_id}/tools", timeout=10.0)
            r.raise_for_status()
            tools = r.json()
    except Exception as exc:
        click.echo(_style(f"  ⚠ Could not fetch tools: {exc}", fg="red"))
        return

    if not tools or not isinstance(tools, list):
        click.echo("  (no tools available)")
        return

    # Separate tools by source
    builtin: list[dict] = []
    mcp_tools: list[dict] = []
    other: list[dict] = []

    for t in tools:
        if not isinstance(t, dict):
            continue
        src = str(t.get("source", "")).lower()
        if src == "builtin":
            builtin.append(t)
        elif src in ("mcp", "mcp_client"):
            mcp_tools.append(t)
        else:
            other.append(t)

    def _print_tool_group(label: str, group: list[dict]) -> None:
        if not group:
            return
        click.echo(f"\n  {_style(label, fg='bold')}:")
        for t in sorted(group, key=lambda x: x.get("name", "")):
            name = t.get("name", "?")
            desc = t.get("description", "") or ""
            icon = t.get("icon", "🔧")
            enabled = t.get("enabled", True)
            status = "" if enabled else _style(" [DISABLED]", fg="red")
            line = f"    {icon} {_style(name, fg='cyan')}{status}"
            if desc:
                line += f"  — {desc}"
            click.echo(line)

    _print_tool_group("🛠️  Built-in", builtin)
    _print_tool_group("🔌 MCP", mcp_tools)
    _print_tool_group("📦 Other", other)

    total = len(builtin) + len(mcp_tools) + len(other)
    click.echo(
        f"\n  {_style(f'{total} tool(s) total', fg='dim')}\n",
    )


# ── SSE streaming display ───────────────────────────────────────────────


def _parse_content_blocks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract content blocks from an AgentApp SSE payload.

    The /api/agent/process endpoint emits SSE with this structure::

        {"output": [{"content": [{"type": "text", "text": "..."}, ...]}, ...]}

    Returns all content blocks from all output messages.
    """
    blocks: list[dict[str, Any]] = []
    try:
        output = parsed.get("output", [])
        if not output:
            return blocks
        for msg in output:
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        blocks.append(item)
    except Exception:
        pass
    return blocks


def _format_tool_args(args: Any) -> str:
    """Format tool arguments for display, truncating long values."""
    if isinstance(args, dict):
        # Show key=value pairs, truncating long values
        parts: list[str] = []
        for k, v in args.items():
            v_str = json.dumps(v, ensure_ascii=False)
            if len(v_str) > 80:
                v_str = v_str[:77] + "..."
            parts.append(f"{k}={v_str}")
        return ", ".join(parts)
    if isinstance(args, str):
        return args[:120] + "..." if len(args) > 120 else args
    return str(args)[:120]


def _print_tool_call(tool_name: str, tool_input: Any) -> None:
    """Display a tool-invocation notice during streaming."""
    label = _style(f"🔧 {tool_name}", fg="yellow")
    args = _format_tool_args(tool_input)
    if args:
        click.echo(f"  {label} → {_style(args, fg='dim')}")
    else:
        click.echo(f"  {label}")


def _print_tool_result(tool_name: str, output: Any) -> None:
    """Display a concise tool-result summary."""
    label = _style(f"  ✓ {tool_name}", fg="dim")
    if output is None:
        click.echo(label)
        return
    if isinstance(output, str):
        preview = output[:80].replace("\n", " ")
        if len(output) > 80:
            preview += "..."
    else:
        try:
            preview = json.dumps(output, ensure_ascii=False)
            if len(preview) > 80:
                preview = preview[:77] + "..."
        except Exception:
            preview = str(output)[:80]
    click.echo(f"{label}: {_style(preview, fg='dim')}")


def _stream_and_display(
    base_url: str,
    request_payload: dict[str, Any],
    to_agent: str,
    timeout: int,
) -> str:
    """Stream SSE events from the agent and display them interactively.

    Handles the real /api/agent/process SSE format::

        data: {"output":[{"content":[{"type":"text","text":"..."}]}]}

    Content block types handled:
      - ``text``      → accumulated and printed at response end
      - ``thinking``  → streamed live (dim)
      - ``tool_use``  → tool call notice (yellow)
      - ``tool_result`` → brief result summary (dim)

    Returns the accumulated plain-text response.
    """
    collected_text: list[str] = []
    seen_tool_call_ids: set[str] = set()

    with create_agent_api_client(base_url) as client:
        with client.stream(
            "POST",
            "/agent/process",
            json=request_payload,
            headers={"X-Agent-Id": to_agent},
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                parsed = parse_agent_sse_line(line)
                if not parsed:
                    continue

                # Extract content blocks from the AgentApp SSE payload
                blocks = _parse_content_blocks(parsed)
                if not blocks:
                    continue

                for block in blocks:
                    btype = block.get("type", "")

                    if btype == "text":
                        txt = block.get("text", "")
                        if isinstance(txt, str) and txt.strip():
                            collected_text.append(txt)

                    elif btype == "thinking":
                        txt = block.get("text", "") or block.get(
                            "thinking", ""
                        )
                        if isinstance(txt, str) and txt.strip():
                            click.echo(
                                _style(f"  💭 {txt.strip()}", fg="dim"),
                            )

                    elif btype == "tool_use":
                        call_id = block.get("id", "")
                        name = block.get("name", "?")
                        tool_input = block.get("input", {})
                        # Deduplicate tool calls that appear across
                        # multiple SSE events
                        dedup_key = f"{call_id}:{name}"
                        if dedup_key not in seen_tool_call_ids:
                            seen_tool_call_ids.add(dedup_key)
                            _print_tool_call(name, tool_input)

                    elif btype == "tool_result":
                        name = block.get("name", "?")
                        output = block.get("output", "")
                        _print_tool_result(name, output)

                    elif btype == "error":
                        err = block.get("text", "") or str(block)
                        click.echo(
                            _style(f"  ⚠ {err}", fg="red"),
                        )

    # Print all accumulated text at the end
    full_text = "".join(collected_text).strip()
    if full_text:
        click.echo(full_text)
    return full_text


# ── Main REPL loop ─────────────────────────────────────────────────────


def _run_repl(
    base_url: str,
    agent_id: str,
    user_id: str,
    session_id: list[str],
    timeout: int,
) -> None:
    """Core REPL loop — prompts, sends, streams, repeats."""
    welcome = (
        f"{_style('✦ Interactive Agent Chat', fg='bold')}\n"
        f"  Agent: {_style(agent_id, fg='cyan')}  "
        f"User: {_style(user_id, fg='green')}\n"
        f"  Type {_style('/help', fg='bold')} for commands, "
        f"{_style('/exit', fg='bold')} to quit."
    )
    click.echo(welcome)
    _print_separator()

    while True:
        try:
            text = click.prompt(
                _user_label(user_id),
                prompt_suffix=" ",
                default="",
                show_default=False,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C / Ctrl+D
            click.echo()
            click.echo(_style("👋 Goodbye!", fg="dim"))
            break

        if not text:
            continue

        # Special commands
        if _is_special_command(text):
            should_continue = _handle_special_command(
                text, agent_id, session_id, base_url,
            )
            if not should_continue:
                click.echo(_style("👋 Goodbye!", fg="dim"))
                break
            continue

        # Build and send the chat request
        click.echo(f"  [{_timestamp()}] {_agent_label(agent_id)} ", nl=False)

        # If session_id[0] is empty, generate a new one by passing None
        effective_session = session_id[0] or None

        try:
            _, request_payload, _ = build_agent_chat_request(
                to_agent=agent_id,
                text=text,
                session_id=effective_session,
                from_agent=user_id,
            )
        except Exception as exc:
            click.echo(
                _style(f"\n⚠ Request build failed: {exc}", fg="red"),
            )
            continue

        # Persist session_id after first request
        if not session_id[0]:
            # build_agent_chat_request generates the session_id internally;
            # we need to reconstruct it from the payload.
            sid = request_payload.get("session_id", "")
            if sid:
                session_id[0] = sid

        # Stream the response
        try:
            _stream_and_display(base_url, request_payload, agent_id, timeout)
        except Exception as exc:
            click.echo(_style(f"\n⚠ Response error: {exc}", fg="red"))

        _print_separator()


# ── Click command ───────────────────────────────────────────────────────


@click.command("repl")
@click.option(
    "--agent-id",
    default="default",
    show_default=True,
    help="Target agent ID to converse with.",
)
@click.option(
    "--user-id",
    default="cli-user",
    show_default=True,
    help="Your identity label (shown in the prompt).",
)
@click.option(
    "--base-url",
    default=None,
    help="Override API base URL (e.g. http://127.0.0.1:8088).",
)
@click.option(
    "--timeout",
    default=300,
    type=int,
    show_default=True,
    help="Per-message response timeout in seconds.",
)
@click.option(
    "--list-tools",
    is_flag=True,
    default=False,
    help="List available tools (built-in + MCP) and exit.",
)
@click.option(
    "--server/--local",
    "use_server",
    default=None,
    help=(
        "Force server mode (connect to running server) "
        "or local mode (run agent directly in CLI). "
        "Default: local if not connected, server if connected."
    ),
)
@click.pass_context
def repl_cmd(
    ctx: click.Context,
    agent_id: str,
    user_id: str,
    base_url: Optional[str],
    timeout: int,
    list_tools: bool,
    use_server: Optional[bool],
) -> None:
    """Start an interactive chat session with an agent.

    By default runs the agent locally — no server needed.  The agent
    can invoke built-in tools and MCP tools automatically.

    Use ``openspider connect to --url <url>`` to switch to server mode.

    \b
    In-session commands:
      /exit  or  Ctrl+C  Quit the REPL
      /clear              Clear the terminal
      /help               Show in-session help
      /new                Start a fresh conversation
      /tools              List available tools (built-in + MCP)

    \b
    Examples:

      \b
      # Chat with the default agent (local mode)
      openspider repl

      \b
      # Chat with a research agent as user "alice"
      openspider repl --agent-id research --user-id alice

      \b
      # Force remote mode
      openspider repl --server --base-url http://192.168.1.100:8088

      \b
      # List available tools and exit
      openspider repl --list-tools
    """
    from .connection import is_connected, get_base_url
    from .http import is_server_running

    # Resolve mode: --server, --local, --base-url, or connection state
    if use_server is True:
        mode = "server"
    elif use_server is False:
        mode = "local"
    elif base_url is not None:
        mode = "server"
    elif is_connected():
        mode = "server"
        base_url = base_url or get_base_url()
    else:
        # Auto-detect: if local server is running, suggest it
        host = (ctx.obj or {}).get("host", "127.0.0.1")
        port = int((ctx.obj or {}).get("port", 8088))
        if is_server_running(host, port) and not is_connected():
            mode = "server"
            base_url = base_url or f"http://{host}:{port}"
        else:
            mode = "local"

    resolved_base_url = resolve_base_url(ctx, base_url) if base_url else None

    # --list-tools mode: print tools and exit
    if list_tools:
        click.echo()
        if mode == "server":
            _show_available_tools(resolved_base_url or "", agent_id)
        else:
            _show_available_tools_local(agent_id)
        return

    if mode == "local":
        _repl_local(agent_id, user_id, timeout)
    else:
        _repl_server(ctx, resolved_base_url, agent_id, user_id, timeout)


# ── Local agent REPL ─────────────────────────────────────────────────


def _show_available_tools_local(agent_id: str) -> None:
    """List tools using the local agent config (no server required)."""
    from ..config.config import load_agent_config
    from ..config import load_config

    try:
        agent_config = load_agent_config(agent_id)
    except Exception as exc:
        click.echo(
            _style(f"  ⚠ Could not load agent config: {exc}", fg="red"),
        )
        return

    click.echo()
    click.echo(_style(f"  Available Tools for agent '{agent_id}'", fg="bold"))
    click.echo("  " + "─" * 40)

    # Built-in tools
    builtin = (agent_config.tools.builtin_tools
               if agent_config.tools else {})
    if builtin:
        click.echo(f"\n  {_style('🛠️  Built-in', fg='bold')}:")
        for name, cfg in builtin.items():
            enabled = getattr(cfg, "enabled", True)
            status = "" if enabled else _style(" [DISABLED]", fg="red")
            click.echo(f"    🔧 {_style(name, fg='cyan')}{status}")

    # MCP tools
    mcp_config = agent_config.mcp
    mcp_count = 0
    if mcp_config:
        click.echo(f"\n  {_style('🔌 MCP Servers', fg='bold')}:")
        for key, cfg in mcp_config.clients.items():
            status = (click.style("enabled", fg="green")
                      if cfg.enabled
                      else click.style("disabled", fg="yellow"))
            transport = cfg.transport
            click.echo(
                f"    • {_style(key, fg='cyan')} "
                f"({transport}) [{status}]"
            )

    click.echo()


def _repl_local(agent_id: str, user_id: str, timeout: int) -> None:
    """Run the REPL using a local SpiderAgent (no server).

    Uses a single persistent asyncio event loop so MCP client
    connections survive across chat turns.  The input loop runs
    synchronously for responsiveness; only agent calls go through
    the event loop.
    """
    import asyncio

    from .local_agent import LocalAgentSession

    click.echo()
    click.echo(
        _style("✦ Interactive Agent Chat [local mode]", fg="bold"),
    )
    click.echo(
        f"  Agent: {_style(agent_id, fg='cyan')}  "
        f"User: {_style(user_id, fg='green')}  "
        f"Mode: {_style('local (no server)', fg='dim')}",
    )
    click.echo(
        f"  Type {_style('/help', fg='bold')} for commands, "
        f"{_style('/exit', fg='bold')} to quit.",
    )
    click.echo(
        _style("  Starting local agent (loading MCP clients)...", fg="dim"),
        nl=False,
    )

    # ── One persistent event loop for the entire session ──────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    session = LocalAgentSession(agent_id=agent_id)
    try:
        loop.run_until_complete(session.start())
    except Exception as exc:
        click.echo(_style(f"\n✗ Failed to start: {exc}", fg="red"))
        loop.close()
        return

    click.echo(_style(" ✓", fg="green"))
    _print_separator()

    try:
        while True:
            # ── Synchronous input (no thread, no overhead) ────
            try:
                text = click.prompt(
                    _user_label(user_id),
                    prompt_suffix=" ",
                    default="",
                    show_default=False,
                ).strip()
            except (EOFError, KeyboardInterrupt):
                click.echo()
                click.echo(_style("👋 Goodbye!", fg="dim"))
                break

            if not text:
                continue

            if _is_special_command(text):
                should_continue = _handle_special_command(
                    text, agent_id, [""], "",
                )
                if not should_continue:
                    click.echo(_style("👋 Goodbye!", fg="dim"))
                    break
                continue

            click.echo(
                f"  [{_timestamp()}] {_agent_label(agent_id)} ",
                nl=False,
            )

            # ── Async agent call on the persistent loop ──────
            try:
                result = loop.run_until_complete(
                    session.chat_with_timeout(text, timeout=timeout),
                )
            except KeyboardInterrupt:
                click.echo(
                    _style(" (interrupted)", fg="yellow"),
                )
                _print_separator()
                continue
            except Exception as exc:
                click.echo()
                click.echo(
                    _style(f"⚠ Error: {exc}", fg="red"),
                )
                _print_separator()
                continue

            if result.get("status") == "success":
                response = result.get("response", "")
                click.echo()
                if response:
                    click.echo(response)
                else:
                    click.echo(_style("(no response)", fg="dim"))
                elapsed = result.get("elapsed_seconds", 0)
                click.echo(
                    _style(f"  [{elapsed:.1f}s]", fg="dim"),
                )
            elif result.get("status") == "timeout":
                click.echo()
                click.echo(
                    _style(
                        f"⚠ Timed out after {timeout}s",
                        fg="yellow",
                    ),
                )
            else:
                click.echo()
                click.echo(
                    _style(
                        f"⚠ Error: {result.get('error', 'unknown')}",
                        fg="red",
                    ),
                )

            _print_separator()
    finally:
        try:
            loop.run_until_complete(session.stop())
        except Exception:
            pass
        loop.close()


def _repl_server(
    ctx: click.Context,
    base_url: str | None,
    agent_id: str,
    user_id: str,
    timeout: int,
) -> None:
    """Run the REPL via a remote server (existing HTTP code)."""
    resolved_base_url = resolve_base_url(ctx, base_url) if base_url else None

    click.echo()
    click.echo(
        _style("Connecting...", fg="dim"),
        nl=False,
    )

    # Quick connectivity check
    try:
        from httpx import Client
        with Client(
            base_url=(resolved_base_url or "").rstrip("/api").rstrip("/"),
            timeout=5.0,
        ) as c:
            r = c.get("/api/health", timeout=5.0)
            r.raise_for_status()
    except Exception as exc:
        click.echo(
            _style(
                f"\n✗ Cannot reach server at {resolved_base_url}",
                fg="red",
            ),
        )
        click.echo(
            f"  Make sure 'openspider app' is running.\n"
            f"  Error: {exc}",
        )
        raise click.Abort() from exc

    click.echo(_style(" ✓", fg="green"))

    session_id: list[str] = [""]

    try:
        _run_repl(
            resolved_base_url or "",
            agent_id,
            user_id,
            session_id,
            timeout,
        )
    except KeyboardInterrupt:
        click.echo()
        click.echo(_style("👋 Goodbye!", fg="dim"))
