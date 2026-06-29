# -*- coding: utf-8 -*-
from __future__ import annotations

import secrets

import click

from ..app.auth import (
    _hash_password,
    _load_auth_data,
    _save_auth_data,
    is_auth_enabled,
)


@click.group("auth", help="Manage web authentication.")
def auth_group() -> None:
    """Manage web authentication."""


@auth_group.command("reset-password")
@click.option("--username", "-u", default=None, help="Username to reset password for.")
def reset_password_cmd(username: str | None) -> None:
    """Reset the password for a registered web user."""
    if not is_auth_enabled():
        click.echo(
            "Authentication is not enabled.\n"
            "Set OPENSPIDER_AUTH_ENABLED=true to enable it first.",
        )
        return

    data = _load_auth_data()

    if data.get("_auth_load_error"):
        raise click.ClickException(
            "Failed to read auth data. Check auth.json for corruption.",
        )

    users = data.get("users", {})
    if not users:
        click.echo("No registered users found. Nothing to reset.")
        return

    # If no username specified, use the first available user
    if username is None:
        username = next(iter(users.keys()))
        click.echo(f"No username specified. Using: {username}")

    user = users.get(username)
    if not user:
        available = ", ".join(users.keys())
        raise click.ClickException(
            f"User '{username}' not found. Available users: {available}",
        )

    click.echo(f"Resetting password for user: {username}")

    new_password = click.prompt(
        "New password",
        hide_input=True,
        confirmation_prompt=True,
    )

    if not new_password or not new_password.strip():
        raise click.ClickException("Password cannot be empty.")

    pw_hash, salt = _hash_password(new_password)
    users[username]["password_hash"] = pw_hash
    users[username]["password_salt"] = salt
    data["users"] = users

    # Invalidate existing tokens by rotating jwt_secret
    data["jwt_secret"] = secrets.token_hex(32)

    _save_auth_data(data)
    click.echo(
        "✓ Password reset successfully. "
        "All existing sessions have been invalidated.",
    )
