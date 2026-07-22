# -*- coding: utf-8 -*-
"""PostgreSQL-backed authentication store.

Replaces file-based ``auth.json`` I/O with SQLAlchemy queries against
the ``users``, ``auth_meta``, and ``token_revocations`` tables.

All public functions match the signatures of the corresponding helpers
in :mod:`openspider.app.auth`, so callers can swap between backends
transparently.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from openspider.db.models import AuthMeta, TokenRevocation, User

logger = logging.getLogger(__name__)

# Token validity: 7 days (default)
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600
TOKEN_EXPIRY_MAX = 100 * 365 * 24 * 3600


# ============================================================================
# Password hashing (salted SHA-256, same algorithm as auth.py)
# ============================================================================


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hash *password* with *salt*. Returns ``(hash_hex, salt_hex)``."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h, salt


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    """Verify *password* against a stored hash using constant-time compare."""
    h, _ = _hash_password(password, stored_salt)
    return hmac.compare_digest(h, stored_hash)


# ============================================================================
# User CRUD
# ============================================================================


async def list_users(session: AsyncSession) -> list[dict]:
    """Return all registered users (no password data)."""
    result = await session.execute(select(User).order_by(User.username))
    return [
        {"username": u.username, "role": u.role}
        for u in result.scalars().all()
    ]


async def get_user(session: AsyncSession, username: str) -> Optional[User]:
    """Return a single user by username, or None."""
    result = await session.execute(
        select(User).where(User.username == username),
    )
    return result.scalar_one_or_none()


async def get_user_count(session: AsyncSession) -> int:
    """Return total number of registered users."""
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar() or 0


async def has_registered_users(session: AsyncSession) -> bool:
    """Return True if any user has been registered."""
    return await get_user_count(session) > 0


async def register_user(
    session: AsyncSession,
    username: str,
    password: str,
    role: str | None = None,
) -> Optional[str]:
    """Register a user account. Returns a token on success, None if duplicate."""
    # Check for duplicate
    existing = await get_user(session, username)
    if existing is not None:
        logger.warning("Attempt to register duplicate user '%s'", username)
        return None

    # Determine role
    if role is None:
        user_count = await get_user_count(session)
        role = "admin" if user_count == 0 else "user"

    pw_hash, salt = _hash_password(password)
    now = datetime.now(timezone.utc)

    stmt = pg_insert(User).values(
        username=username,
        password_hash=pw_hash,
        password_salt=salt,
        role=role,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_nothing()

    await session.execute(stmt)
    await session.commit()

    logger.info("User '%s' registered (role=%s)", username, role)
    return await create_token(session, username)


async def authenticate(
    session: AsyncSession,
    username: str,
    password: str,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Authenticate username/password. Returns a token if valid."""
    user = await get_user(session, username)
    if user is None:
        return None
    if verify_password(password, user.password_hash, user.password_salt):
        return await create_token(session, username, expiry_seconds)
    return None


async def update_credentials(
    session: AsyncSession,
    current_password: str,
    current_username: str,
    new_username: Optional[str] = None,
    new_password: Optional[str] = None,
    expiry_seconds: Optional[int] = None,
) -> Optional[str]:
    """Update username and/or password. Returns new token or None."""
    user = await get_user(session, current_username)
    if user is None:
        return None
    if not verify_password(current_password, user.password_hash, user.password_salt):
        return None

    if new_username and new_username.strip():
        new_uname = new_username.strip()
        if new_uname != current_username:
            dup = await get_user(session, new_uname)
            if dup is not None:
                return None  # username taken
            user.username = new_uname
            current_username = new_uname

    if new_password:
        pw_hash, salt = _hash_password(new_password)
        user.password_hash = pw_hash
        user.password_salt = salt
        # Rotate JWT secret to invalidate all existing sessions
        await _rotate_jwt_secret(session)

    user.updated_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("Credentials updated for user '%s'", current_username)
    return await create_token(session, current_username, expiry_seconds)


async def delete_user(
    session: AsyncSession,
    username: str,
) -> bool:
    """Delete a user. Returns True if removed."""
    user = await get_user(session, username)
    if user is None:
        return False
    await session.delete(user)
    await session.commit()
    logger.info("User '%s' deleted", username)
    return True


async def update_user_role(
    session: AsyncSession,
    username: str,
    new_role: str,
) -> bool:
    """Change a user's role."""
    user = await get_user(session, username)
    if user is None or new_role not in ("admin", "user"):
        return False
    user.role = new_role
    user.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return True


# ============================================================================
# JWT secret management
# ============================================================================


async def _get_jwt_secret(session: AsyncSession) -> str:
    """Return the signing secret, creating one if absent."""
    result = await session.execute(
        select(AuthMeta).where(AuthMeta.key == "jwt_secret"),
    )
    row = result.scalar_one_or_none()
    if row and row.value:
        return row.value

    secret = secrets.token_hex(32)
    stmt = pg_insert(AuthMeta).values(
        key="jwt_secret",
        value=secret,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={"value": secret, "updated_at": datetime.now(timezone.utc)},
    )
    await session.execute(stmt)
    await session.commit()
    return secret


async def _rotate_jwt_secret(session: AsyncSession) -> None:
    """Replace the JWT secret with a new random value."""
    new_secret = secrets.token_hex(32)
    stmt = pg_insert(AuthMeta).values(
        key="jwt_secret",
        value=new_secret,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={"value": new_secret, "updated_at": datetime.now(timezone.utc)},
    )
    await session.execute(stmt)
    await session.commit()
    logger.info("JWT secret rotated")


# ============================================================================
# Token creation / verification (HMAC-SHA256, same format as auth.py)
# ============================================================================


async def create_token(
    session: AsyncSession,
    username: str,
    expiry_seconds: Optional[int] = None,
) -> str:
    """Create an HMAC-signed token: ``base64(payload).signature``."""
    import base64
    import json as _json

    if expiry_seconds is None:
        expiry_seconds = TOKEN_EXPIRY_SECONDS
    elif expiry_seconds <= 0:
        expiry_seconds = TOKEN_EXPIRY_MAX
    else:
        expiry_seconds = min(expiry_seconds, TOKEN_EXPIRY_MAX)

    secret = await _get_jwt_secret(session)
    token_id = secrets.token_hex(16)

    user = await get_user(session, username)
    role = user.role if user else "admin"

    payload = _json.dumps({
        "sub": username,
        "role": role,
        "exp": int(time.time()) + expiry_seconds,
        "iat": int(time.time()),
        "jti": token_id,
    })
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


async def verify_token(session: AsyncSession, token: str) -> Optional[tuple[str, str]]:
    """Verify *token*, return ``(username, role)`` if valid, ``None`` otherwise."""
    import base64
    import json as _json

    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        secret = await _get_jwt_secret(session)
        expected_sig = hmac.new(
            secret.encode(), payload_b64.encode(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None

        jti = payload.get("jti")
        if jti and await _is_token_revoked(session, jti):
            return None

        return (payload.get("sub"), payload.get("role", "admin"))
    except Exception:
        return None


# ============================================================================
# Token revocation
# ============================================================================


async def _is_token_revoked(session: AsyncSession, jti: str) -> bool:
    """Check if a token ID is in the revocation list."""
    result = await session.execute(
        select(TokenRevocation).where(TokenRevocation.jti == jti),
    )
    return result.scalar_one_or_none() is not None


async def revoke_token(session: AsyncSession, jti: str, exp: int) -> bool:
    """Add a token ID to the revocation list."""
    try:
        stmt = pg_insert(TokenRevocation).values(
            jti=jti,
            expires_at=exp,
            created_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()
        await _clean_expired_revocations(session)
        return True
    except Exception:
        logger.exception("Failed to revoke token %s", jti[:8])
        return False


async def revoke_all_tokens(session: AsyncSession) -> bool:
    """Revoke all tokens by rotating the JWT secret and clearing the list."""
    try:
        await _rotate_jwt_secret(session)
        await session.execute(delete(TokenRevocation))
        await session.commit()
        logger.info("All tokens revoked (JWT secret rotated)")
        return True
    except Exception:
        logger.exception("Failed to revoke all tokens")
        return False


async def _clean_expired_revocations(session: AsyncSession) -> None:
    """Remove expired tokens from the revocation list."""
    now = int(time.time())
    result = await session.execute(
        delete(TokenRevocation).where(TokenRevocation.expires_at <= now),
    )
    if result.rowcount:
        await session.commit()
        logger.debug("Cleaned %d expired token revocations", result.rowcount)
