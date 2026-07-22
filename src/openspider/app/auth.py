# -*- coding: utf-8 -*-
"""Authentication module: password hashing, tokens, and FastAPI middleware.

Authentication is enabled by default and can be disabled by setting
``OPENSPIDER_AUTH_ENABLED=false``.  Credentials are created through a
web-based registration flow rather than environment variables, so that
agents running inside the process cannot read plaintext passwords.

Multi-user design: the first registered user is always an admin.  Admins
can create additional users with different roles via the admin API.
Users are stored in ``auth.json`` under ``SECRET_DIR``.

Uses only Python stdlib (hashlib, hmac, secrets) to avoid adding new
dependencies.  The password is stored as a salted SHA-256 hash in
``auth.json`` under ``SECRET_DIR``.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..constant import SECRET_DIR, EnvVarLoader
from ..security.secret_store import (
    AUTH_SECRET_FIELDS,
    decrypt_dict_fields,
    encrypt_dict_fields,
    is_encrypted,
)

logger = logging.getLogger(__name__)

AUTH_FILE = SECRET_DIR / "auth.json"

# Token validity: 7 days (default)
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600

# Maximum token validity: 100 years (for "permanent" tokens)
TOKEN_EXPIRY_MAX = 100 * 365 * 24 * 3600

# Paths that do NOT require authentication
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/api/auth/login",
        "/api/auth/status",
        "/api/auth/register",
        "/api/version",
        "/api/settings/language",
        "/api/plugins",
    },
)

# Prefixes that do NOT require authentication (static assets)
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/assets/",
    "/logo.png",
    "/qwenpaw-symbol.svg",
    "/api/plugins/",  # plugin JS bundles served to unauthenticated login page
)


# ---------------------------------------------------------------------------
# Helpers (reuse SECRET_DIR patterns from envs/store.py)
# ---------------------------------------------------------------------------


def _chmod_best_effort(path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _prepare_secret_parent(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)


# ---------------------------------------------------------------------------
# Password hashing (salted SHA-256, no external deps)
# ---------------------------------------------------------------------------


def _hash_password(
    password: str,
    salt: Optional[str] = None,
) -> tuple[str, str]:
    """Hash *password* with *salt*.  Returns ``(hash_hex, salt_hex)``."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify *password* against a stored hash."""
    h, _ = _hash_password(password, salt)
    return hmac.compare_digest(h, stored_hash)


# ---------------------------------------------------------------------------
# Token generation / verification (HMAC-SHA256, no PyJWT needed)
# ---------------------------------------------------------------------------


def _get_jwt_secret() -> str:
    """Return the signing secret, creating one if absent."""
    data = _load_auth_data()
    secret = data.get("jwt_secret", "")
    if not secret:
        secret = secrets.token_hex(32)
        data["jwt_secret"] = secret
        _save_auth_data(data)
    return secret


def create_token(username: str, expiry_seconds: Optional[int] = None) -> str:
    """Create an HMAC-signed token: ``base64(payload).signature``.

    Args:
        username: The username to encode in the token.
        expiry_seconds: Custom expiry time in seconds.
            Use -1 or 0 for permanent tokens.
            Defaults to TOKEN_EXPIRY_SECONDS (7 days).
    """
    import base64

    if expiry_seconds is None:
        expiry_seconds = TOKEN_EXPIRY_SECONDS
    elif expiry_seconds <= 0:
        # Permanent token: 100 years
        expiry_seconds = TOKEN_EXPIRY_MAX
    else:
        # Cap at maximum allowed expiry
        expiry_seconds = min(expiry_seconds, TOKEN_EXPIRY_MAX)

    secret = _get_jwt_secret()
    # Generate unique token ID (jti) for revocation support
    token_id = secrets.token_hex(16)
    # Read the user's actual role from stored data
    user_data = _get_user(username)
    role = user_data.get("role", "user") if user_data else "admin"
    payload = json.dumps(
        {
            "sub": username,
            "role": role,
            "exp": int(time.time()) + expiry_seconds,
            "iat": int(time.time()),
            "jti": token_id,  # JWT ID for individual revocation
        },
    )
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(
        secret.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> Optional[tuple[str, str]]:
    """Verify *token*, return ``(username, role)`` if valid, ``None`` otherwise.

    Also checks if the token has been revoked (appears in the revocation list).
    Legacy tokens without a ``role`` claim default to ``"admin"``.
    """
    import base64

    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        secret = _get_jwt_secret()
        expected_sig = hmac.new(
            secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None

        # Check if token is revoked
        jti = payload.get("jti")
        if jti and _is_token_revoked(jti):
            return None

        username = payload.get("sub")
        role = payload.get("role", "admin")  # Default to admin for legacy tokens
        return (username, role)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.debug("Token verification failed: %s", exc)
        return None


def get_current_user(request: Request) -> Optional[tuple[str, str]]:
    """Extract and verify the Bearer token from *request*.

    Returns ``(username, role)`` if valid, ``None`` otherwise.
    Prefers token cached in ``request.scope`` by ``AuthMiddleware``.
    """
    # Check if middleware already verified and cached
    cached_user = request.scope.get("auth_user")
    cached_role = request.scope.get("auth_role")
    if cached_user and cached_role:
        return (cached_user, cached_role)

    # Fallback: extract and verify from header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not token:
        return None
    return verify_token(token)


def get_current_admin(request: Request) -> str:
    """FastAPI dependency: returns the admin username, or raises 403.

    Usage::

        @router.get("/admin/endpoint")
        async def admin_endpoint(admin: str = Depends(get_current_admin)):
            ...
    """
    result = get_current_user(request)
    if result is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username, role = result
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return username


# Backward-compatible alias for the dependency name used in routers
require_admin = get_current_admin


# ---------------------------------------------------------------------------
# Auth data persistence (auth.json in SECRET_DIR)
# ---------------------------------------------------------------------------


def _load_auth_data() -> dict:
    """Load ``auth.json`` from ``SECRET_DIR``.

    Returns the parsed dict, or a sentinel with ``_auth_load_error``
    set to ``True`` when the file exists but cannot be read/parsed so
    that callers can fail closed instead of silently bypassing auth.

    Encrypted fields (``jwt_secret``) are transparently decrypted.
    Legacy plaintext values trigger an automatic re-encryption.
    Legacy single-user ``"user"`` key is auto-migrated to ``"users"``.
    """
    if AUTH_FILE.is_file():
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            needs_rewrite = any(
                isinstance(data.get(field), str)
                and data.get(field)
                and not is_encrypted(data[field])
                for field in AUTH_SECRET_FIELDS
            )
            data = decrypt_dict_fields(data, AUTH_SECRET_FIELDS)

            # Auto-migrate legacy single-user format to multi-user
            if "user" in data and "users" not in data:
                legacy_user = data.pop("user")
                username = legacy_user.get("username", "admin")
                data["users"] = {username: legacy_user}
                logger.info(
                    "Migrated legacy single-user auth.json to multi-user format"
                )
                needs_rewrite = True

            if needs_rewrite:
                try:
                    _save_auth_data(data)
                except Exception as enc_err:
                    logger.debug(
                        "Deferred plaintext→encrypted migration for"
                        " auth.json: %s",
                        enc_err,
                    )
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load auth file %s: %s", AUTH_FILE, exc)
            return {"_auth_load_error": True}
    return {}


def _get_users() -> dict:
    """Return the users dict from auth.json, keyed by username."""
    data = _load_auth_data()
    return data.get("users", {})


def _get_user(username: str) -> dict | None:
    """Return a single user's data by username, or None."""
    return _get_users().get(username)


def _save_auth_data(data: dict) -> None:
    """Save ``auth.json`` to ``SECRET_DIR`` with restrictive permissions.

    Sensitive fields (``jwt_secret``) are encrypted before writing.
    """
    _prepare_secret_parent(AUTH_FILE)
    encrypted_data = encrypt_dict_fields(data, AUTH_SECRET_FIELDS)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(encrypted_data, f, indent=2, ensure_ascii=False)
    _chmod_best_effort(AUTH_FILE, 0o600)


# ---------------------------------------------------------------------------
# Token revocation (blacklist management)
# ---------------------------------------------------------------------------


def _is_token_revoked(jti: str) -> bool:
    """Check if a token ID (jti) is in the revocation list.

    Uses O(1) dict lookup via revoked_tokens_meta for performance.
    """
    data = _load_auth_data()
    meta = data.get("revoked_tokens_meta", {})
    return jti in meta


def _add_to_revocation_list(jti: str, exp: int) -> None:
    """Add a token ID to the revocation list with its expiry time.

    Uses revoked_tokens_meta dict for O(1) lookups. The revoked_tokens list
    is kept for backwards compatibility but not used for membership checks.
    """
    data = _load_auth_data()
    if data.get("_auth_load_error"):
        return

    # Initialize revoked_tokens_meta if not present
    if "revoked_tokens_meta" not in data:
        data["revoked_tokens_meta"] = {}

    # O(1) check using dict
    if jti not in data["revoked_tokens_meta"]:
        data["revoked_tokens_meta"][jti] = exp

        # Also add to list for backwards compatibility
        if "revoked_tokens" not in data:
            data["revoked_tokens"] = []
        data["revoked_tokens"].append(jti)

    _save_auth_data(data)


def _clean_expired_revocations() -> None:
    """
    Remove expired tokens from the revocation list to prevent unbounded growth.
    """
    data = _load_auth_data()
    if data.get("_auth_load_error"):
        return

    revoked = data.get("revoked_tokens", [])
    meta = data.get("revoked_tokens_meta", {})
    current_time = int(time.time())

    # Remove expired tokens
    cleaned_revoked = []
    cleaned_meta = {}

    for jti in revoked:
        exp = meta.get(jti, 0)
        if exp > current_time:
            cleaned_revoked.append(jti)
            cleaned_meta[jti] = exp

    if len(cleaned_revoked) < len(revoked):
        data["revoked_tokens"] = cleaned_revoked
        data["revoked_tokens_meta"] = cleaned_meta
        _save_auth_data(data)
        logger.info(
            "Cleaned %d expired tokens from revocation list",
            len(revoked) - len(cleaned_revoked),
        )


def is_auth_enabled() -> bool:
    """Check whether authentication is enabled.

    Authentication is **enabled by default**.  It is disabled only when
    the environment variable ``OPENSPIDER_AUTH_ENABLED`` is explicitly set
    to ``"false"``, ``"0"``, ``"no"``, or ``"disabled"``.

    This ensures new deployments require authentication out of the box
    without extra configuration, while existing deployments that already
    set ``OPENSPIDER_AUTH_ENABLED=true`` are unaffected.
    """
    env_flag = EnvVarLoader.get_str("OPENSPIDER_AUTH_ENABLED", "").strip().lower()
    if env_flag == "":
        return True  # Default: enabled
    if env_flag in ("false", "0", "no", "disabled"):
        return False
    return True  # Any other value ("true", "1", "yes", etc.) → enabled


def has_registered_users() -> bool:
    """Return ``True`` if any user has been registered."""
    return len(_get_users()) > 0


def get_user_count() -> int:
    """Return the number of registered users."""
    return len(_get_users())


# ---------------------------------------------------------------------------
# Registration (single-user)
# ---------------------------------------------------------------------------


def register_user(
    username: str,
    password: str,
    expiry_seconds: Optional[int] = None,
    role: str | None = None,
) -> Optional[str]:
    """Register a user account.

    If no users exist yet, the first user is always an admin.
    Otherwise the *role* parameter determines the role (default ``"user"``).

    Returns a token on success, ``None`` if the username already exists.
    """
    data = _load_auth_data()
    users = data.get("users", {})

    # Check for duplicate username
    if username in users:
        logger.warning("Attempt to register duplicate user '%s'", username)
        return None

    # First user is always admin; subsequent users use explicit role or default
    if role is None:
        role = "admin" if not users else "user"

    pw_hash, salt = _hash_password(password)
    users[username] = {
        "username": username,
        "password_hash": pw_hash,
        "password_salt": salt,
        "role": role,
    }
    data["users"] = users

    # Ensure jwt_secret exists
    if not data.get("jwt_secret"):
        data["jwt_secret"] = secrets.token_hex(32)

    _save_auth_data(data)
    logger.info("User '%s' registered (role=%s)", username, role)
    return create_token(username, expiry_seconds)


def auto_register_from_env() -> None:
    """Auto-register admin user from environment variables.

    Called once during application startup.  If ``QWENPAW_AUTH_ENABLED``
    is truthy and both ``QWENPAW_AUTH_USERNAME`` and ``QWENPAW_AUTH_PASSWORD``
    are set, the admin account is created automatically — useful for
    Docker, Kubernetes, server-panel, and other automated deployments
    where interactive web registration is not practical.

    Skips silently when:
    - authentication is not enabled
    - a user has already been registered
    - either env var is missing or empty
    """
    if not is_auth_enabled():
        return
    if has_registered_users():
        return

    username = EnvVarLoader.get_str("OPENSPIDER_AUTH_USERNAME", "").strip()
    password = EnvVarLoader.get_str("OPENSPIDER_AUTH_PASSWORD", "").strip()
    if not username or not password:
        return

    token = register_user(username, password)
    if token:
        logger.info(
            "Auto-registered user '%s' from environment variables",
            username,
        )


def update_credentials(
    current_password: str,
    current_username: str,
    new_username: Optional[str] = None,
    new_password: Optional[str] = None,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Update a user's username and/or password.

    Requires the current password for verification.  Returns a new
    token on success (because the username may have changed), or
    ``None`` if verification fails.

    Args:
        current_password: The current password for verification.
        current_username: The username whose credentials are being updated.
        new_username: The new username (optional).
        new_password: The new password (optional).
        expiry_seconds: Custom token expiry time in seconds.
    """
    data = _load_auth_data()
    users = data.get("users", {})
    user = users.get(current_username)
    if not user:
        return None

    stored_hash = user.get("password_hash", "")
    stored_salt = user.get("password_salt", "")
    if not verify_password(current_password, stored_hash, stored_salt):
        return None

    if new_username and new_username.strip():
        new_uname = new_username.strip()
        if new_uname != current_username and new_uname in users:
            return None  # Username already taken
        del users[current_username]
        user["username"] = new_uname
        users[new_uname] = user

    if new_password:
        pw_hash, salt = _hash_password(new_password)
        user["password_hash"] = pw_hash
        user["password_salt"] = salt
        # Rotate JWT secret to invalidate all existing sessions
        data["jwt_secret"] = secrets.token_hex(32)

    data["users"] = users
    _save_auth_data(data)
    logger.info("Credentials updated for user '%s'", user["username"])
    return create_token(user["username"], expiry_seconds)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate(
    username: str,
    password: str,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Authenticate *username* / *password*.  Returns a token if valid.

    Args:
        username: The username to authenticate.
        password: The password to verify.
        expiry_seconds: Custom token expiry time in seconds.
    """
    data = _load_auth_data()
    users = data.get("users", {})
    user = users.get(username)
    if not user:
        return None
    stored_hash = user.get("password_hash", "")
    stored_salt = user.get("password_salt", "")
    if (
        stored_hash
        and stored_salt
        and verify_password(password, stored_hash, stored_salt)
    ):
        return create_token(username, expiry_seconds)
    return None


def revoke_token(token: str) -> bool:
    """Revoke a single token by adding its jti to the blacklist.

    Args:
        token: The token string to revoke.

    Returns True on success, False on failure.
    """
    import base64

    try:
        # Extract jti and exp from token
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False

        payload_b64 = parts[0]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        jti = payload.get("jti")
        exp = payload.get("exp", 0)

        if not jti:
            logger.warning("Token has no jti, cannot revoke individually")
            return False

        _add_to_revocation_list(jti, exp)
        logger.info("Token %s revoked", jti[:8])

        # Clean up expired tokens periodically
        _clean_expired_revocations()

        return True
    except Exception as exc:
        logger.error("Failed to revoke token: %s", exc)
        return False


def revoke_all_tokens() -> bool:
    """Revoke all existing tokens by rotating the JWT secret.

    This will invalidate all tokens that were issued before this call.
    Also clears the revocation list since all tokens are invalid anyway.
    Returns True on success, False on failure.
    """
    try:
        data = _load_auth_data()
        if data.get("_auth_load_error"):
            return False

        # Rotate JWT secret to invalidate all existing tokens
        data["jwt_secret"] = secrets.token_hex(32)

        # Clear revocation list since all tokens are now invalid
        data["revoked_tokens"] = []
        data["revoked_tokens_meta"] = {}

        _save_auth_data(data)
        logger.info("All tokens revoked (JWT secret rotated)")
        return True
    except Exception as exc:
        logger.error("Failed to revoke tokens: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Admin user management (multi-user CRUD)
# ---------------------------------------------------------------------------


def list_users() -> list[dict]:
    """Return a list of all registered users with their roles (no password data)."""
    users = _get_users()
    return [
        {"username": u["username"], "role": u.get("role", "user")}
        for u in users.values()
    ]


def create_user_admin(
    username: str,
    password: str,
    role: str = "user",
) -> Optional[str]:
    """Create a new user (admin-only).  Returns a token or None if duplicate."""
    valid_roles = ("admin", "user")
    if role not in valid_roles:
        logger.warning("Invalid role '%s' — must be one of %s", role, valid_roles)
        return None
    return register_user(username, password, role=role)


def update_user_role(username: str, new_role: str) -> bool:
    """Change a user's role.  Returns True on success."""
    valid_roles = ("admin", "user")
    if new_role not in valid_roles:
        logger.warning("Invalid role '%s'", new_role)
        return False

    data = _load_auth_data()
    users = data.get("users", {})
    if username not in users:
        return False

    users[username]["role"] = new_role
    data["users"] = users
    _save_auth_data(data)
    logger.info("User '%s' role changed to '%s'", username, new_role)
    return True


def delete_user(username: str, admin_username: str) -> bool:
    """Delete a user.  Admin cannot delete themselves."""
    if username == admin_username:
        logger.warning("Admin '%s' attempted to delete themselves", admin_username)
        return False

    data = _load_auth_data()
    users = data.get("users", {})
    if username not in users:
        return False

    del users[username]
    data["users"] = users
    _save_auth_data(data)

    # Rotate JWT secret to invalidate the deleted user's tokens
    data["jwt_secret"] = secrets.token_hex(32)
    _save_auth_data(data)
    logger.info("User '%s' deleted by admin '%s'", username, admin_username)
    return True


# ---------------------------------------------------------------------------
# PostgreSQL-backed async wrappers
# ---------------------------------------------------------------------------
# When OPENSPIDER_DATABASE_ENABLED is true, these dispatch to
# ``openspider.db.repos.pg_auth_store``.  Otherwise they delegate to the
# synchronous file-based functions above (via asyncio.to_thread for
# blocking I/O operations).


async def authenticate_async(
    username: str,
    password: str,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Async variant of :func:`authenticate` — uses PG when enabled."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import authenticate as _pg_auth
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_auth(sess, username, password, expiry_seconds)

    return await asyncio.to_thread(
        authenticate, username, password, expiry_seconds,
    )


async def register_user_async(
    username: str,
    password: str,
    expiry_seconds: Optional[int] = None,
    role: str | None = None,
) -> Optional[str]:
    """Async variant of :func:`register_user`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import register_user as _pg_reg
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_reg(sess, username, password, role)

    return await asyncio.to_thread(
        register_user, username, password, expiry_seconds, role,
    )


async def verify_token_async(token: str) -> Optional[tuple[str, str]]:
    """Async variant of :func:`verify_token`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import verify_token as _pg_verify
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_verify(sess, token)

    return await asyncio.to_thread(verify_token, token)


async def revoke_token_async(token: str) -> bool:
    """Async variant of :func:`revoke_token`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        import base64 as _b64
        import json as _json

        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        try:
            payload = _json.loads(_b64.urlsafe_b64decode(parts[0]))
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
        except Exception:
            return False
        if not jti:
            return False

        from ..db.repos.pg_auth_store import revoke_token as _pg_revoke
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_revoke(sess, jti, exp)

    return await asyncio.to_thread(revoke_token, token)


async def revoke_all_tokens_async() -> bool:
    """Async variant of :func:`revoke_all_tokens`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import revoke_all_tokens as _pg_revoke_all
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_revoke_all(sess)

    return await asyncio.to_thread(revoke_all_tokens)


async def list_users_async() -> list[dict]:
    """Async variant of :func:`list_users`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import list_users as _pg_list
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_list(sess)

    return await asyncio.to_thread(list_users)


async def create_user_admin_async(
    username: str,
    password: str,
    role: str = "user",
) -> Optional[str]:
    """Async variant of :func:`create_user_admin`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import register_user as _pg_reg
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_reg(sess, username, password, role)

    return await asyncio.to_thread(
        create_user_admin, username, password, role,
    )


async def delete_user_async(username: str) -> bool:
    """Async variant of :func:`delete_user`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import delete_user as _pg_del
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_del(sess, username)

    return await asyncio.to_thread(
        delete_user, username, "",
    )


async def update_user_role_async(username: str, new_role: str) -> bool:
    """Async variant of :func:`update_user_role`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import (
            update_user_role as _pg_update_role,
        )
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_update_role(sess, username, new_role)

    return await asyncio.to_thread(update_user_role, username, new_role)


async def update_credentials_async(
    current_password: str,
    current_username: str,
    new_username: Optional[str] = None,
    new_password: Optional[str] = None,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Async variant of :func:`update_credentials`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import (
            update_credentials as _pg_update_creds,
        )
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_update_creds(
                sess,
                current_password,
                current_username,
                new_username,
                new_password,
                expiry_seconds,
            )

    return await asyncio.to_thread(
        update_credentials,
        current_password,
        current_username,
        new_username,
        new_password,
        expiry_seconds,
    )


async def has_registered_users_async() -> bool:
    """Async variant of :func:`has_registered_users`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import (
            has_registered_users as _pg_has_users,
        )
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_has_users(sess)

    return await asyncio.to_thread(has_registered_users)


async def get_user_count_async() -> int:
    """Async variant of :func:`get_user_count`."""
    from ..constant import DATABASE_ENABLED as _DB_ENABLED

    if _DB_ENABLED:
        from ..db.repos.pg_auth_store import get_user_count as _pg_count
        from ..db.engine import _session_factory

        async with _session_factory() as sess:
            return await _pg_count(sess)

    return await asyncio.to_thread(get_user_count)


def get_current_user_async(request: Request) -> Optional[tuple[str, str]]:
    """Async-aware variant of :func:`get_current_user`.

    When the DB backend is enabled the middleware already caches
    ``auth_user`` / ``auth_role`` on the request scope, so this
    function can remain synchronous and just read the cached values.
    """
    return get_current_user(request)


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that checks Bearer token on protected routes."""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        """Check Bearer token on protected API routes; skip public paths."""
        if self._should_skip_auth(request):
            return await call_next(request)

        token = self._extract_token(request)
        if not token:
            return Response(
                content=json.dumps({"detail": "Not authenticated"}),
                status_code=401,
                media_type="application/json",
            )

        # Use async variant when PG backend is enabled
        from ..constant import DATABASE_ENABLED as _DB_ENABLED

        if _DB_ENABLED:
            result = await verify_token_async(token)
        else:
            result = verify_token(token)

        if result is None:
            return Response(
                content=json.dumps(
                    {"detail": "Invalid or expired token"},
                ),
                status_code=401,
                media_type="application/json",
            )

        username, role = result
        request.state.user = username
        request.scope["auth_user"] = username
        request.scope["auth_role"] = role
        return await call_next(request)

    @staticmethod
    def _should_skip_auth(request: Request) -> bool:
        """Return ``True`` when the request does not require auth."""
        if not is_auth_enabled() or not has_registered_users():
            return True

        path = request.url.path

        if request.method == "OPTIONS":
            return True

        if path in _PUBLIC_PATHS or any(
            path.startswith(p) for p in _PUBLIC_PREFIXES
        ):
            return True

        # Only protect /api/ routes
        if not path.startswith("/api/"):
            return True

        # Check if client host is in allow_no_auth_hosts whitelist
        from ..config import load_config

        client_host = request.client.host if request.client else ""
        config = load_config()
        allowed_hosts = config.security.allow_no_auth_hosts
        return client_host in allowed_hosts

    @staticmethod
    def _extract_token(request: Request) -> Optional[str]:
        """Extract Bearer token from header or WebSocket query param."""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        if "upgrade" in request.headers.get("connection", "").lower():
            return request.query_params.get("token")

        token = request.query_params.get("token")
        if token:
            return token
        return None
