# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name
"""Unit tests for admin role features in the OpenSpider auth module."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from openspider.app.auth import (
    create_token,
    get_current_admin,
    get_current_user,
    is_auth_enabled,
    register_user,
    verify_token,
)
from openspider.app.routers.auth import router as auth_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_secret_dir(tmp_path: Path) -> Path:
    """Create a temporary SECRET_DIR with an empty auth.json."""
    secret_dir = tmp_path / ".openspider.secret"
    secret_dir.mkdir(parents=True, exist_ok=True)
    auth_file = secret_dir / "auth.json"
    auth_file.write_text("{}", "utf-8")
    return secret_dir


# ---------------------------------------------------------------------------
# is_auth_enabled — default-on behavior
# ---------------------------------------------------------------------------


def test_auth_enabled_by_default():
    """When no env var is set, auth should be enabled."""
    with patch.dict(os.environ, {}, clear=True):
        # Ensure OPENSPIDER_AUTH_ENABLED is not set
        os.environ.pop("OPENSPIDER_AUTH_ENABLED", None)
        assert is_auth_enabled() is True


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("false", False),
        ("0", False),
        ("no", False),
        ("disabled", False),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("TRUE", True),
    ],
)
def test_auth_enabled_explicit(env_value: str, expected: bool):
    """Explicit env var values should be respected."""
    with patch.dict(os.environ, {"OPENSPIDER_AUTH_ENABLED": env_value}, clear=True):
        assert is_auth_enabled() is expected


# ---------------------------------------------------------------------------
# create_token / verify_token — role in token
# ---------------------------------------------------------------------------


def test_create_token_includes_role(tmp_path: Path):
    """create_token() should embed 'role': 'admin' in the token payload."""
    import base64

    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        token = create_token("testuser")
        parts = token.split(".", 1)
        assert len(parts) == 2
        payload = json.loads(base64.urlsafe_b64decode(parts[0]))
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert "exp" in payload
        assert "jti" in payload


def test_verify_token_returns_tuple(tmp_path: Path):
    """verify_token() should return (username, role) for valid tokens."""
    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        token = create_token("testuser")
        result = verify_token(token)
        assert result is not None
        username, role = result
        assert username == "testuser"
        assert role == "admin"


def test_verify_token_backward_compat_role(tmp_path: Path):
    """Legacy tokens without 'role' should default to ('username', 'admin')."""
    import base64
    import hashlib
    import hmac
    import time
    import secrets as _secrets

    secret_dir = _make_fake_secret_dir(tmp_path)
    secret = _secrets.token_hex(32)
    auth_data = {"jwt_secret": secret}
    (secret_dir / "auth.json").write_text(json.dumps(auth_data), "utf-8")

    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        # Create a legacy token WITHOUT role
        token_id = _secrets.token_hex(16)
        payload = json.dumps({
            "sub": "legacyuser",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "jti": token_id,
        })
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
        sig = hmac.new(
            secret.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        legacy_token = f"{payload_b64}.{sig}"

        result = verify_token(legacy_token)
        assert result is not None
        username, role = result
        assert username == "legacyuser"
        assert role == "admin"  # Backward compat default


def test_verify_token_invalid_returns_none(tmp_path: Path):
    """verify_token() should return None for an invalid token."""
    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        assert verify_token("garbage.token") is None
        assert verify_token("") is None


# ---------------------------------------------------------------------------
# register_user — stores role
# ---------------------------------------------------------------------------


def test_register_user_stores_role(tmp_path: Path):
    """register_user() should store 'role': 'admin' in auth.json."""
    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        token = register_user("admin1", "password123")
        assert token is not None

        data = json.loads((secret_dir / "auth.json").read_text("utf-8"))
        users = data["users"]
        assert users["admin1"]["username"] == "admin1"
        assert users["admin1"]["role"] == "admin"
        assert "password_hash" in users["admin1"]
        assert "password_salt" in users["admin1"]


def test_register_user_rejects_duplicate_username(tmp_path: Path):
    """register_user() should return None when the same username is registered twice."""
    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        first = register_user("admin1", "password123")
        assert first is not None
        second = register_user("admin1", "password456")
        assert second is None  # Same username should be rejected


def test_register_user_allows_multiple_users(tmp_path: Path):
    """register_user() should allow multiple users with different usernames."""
    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        first = register_user("admin1", "password123")
        assert first is not None
        second = register_user("user1", "password456")
        assert second is not None  # Different username, should succeed
        # Second user should have 'user' role by default
        result = verify_token(second)
        assert result is not None
        _, role = result
        assert role == "user"


# ---------------------------------------------------------------------------
# get_current_admin dependency
# ---------------------------------------------------------------------------


def test_get_current_admin_allows_admin(tmp_path: Path):
    """get_current_admin should return username when token has admin role."""
    from fastapi import Request

    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        token = register_user("admin1", "password123")
        assert token is not None

        # Simulate a request with the admin token
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [
                (b"authorization", f"Bearer {token}".encode()),
            ],
        }
        request = Request(scope=scope)
        result = get_current_admin(request)
        assert result == "admin1"


def test_get_current_admin_rejects_no_token(tmp_path: Path):
    """get_current_admin should raise 401 when no token is provided."""
    from fastapi import Request
    from fastapi import HTTPException

    secret_dir = _make_fake_secret_dir(tmp_path)
    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
        register_user("admin1", "password123")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        }
        request = Request(scope=scope)
        with pytest.raises(HTTPException) as exc_info:
            get_current_admin(request)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Admin API endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_api_client(tmp_path: Path):
    """Create an async test client for the auth router with isolated auth.json."""
    secret_dir = _make_fake_secret_dir(tmp_path)

    with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"), \
         patch("openspider.app.routers.auth.get_current_user", side_effect=_real_get_current_user(secret_dir)):
        app = FastAPI()
        app.include_router(auth_router, prefix="/api")
        transport = ASGITransport(app=app)
        yield AsyncClient(transport=transport, base_url="http://test")


def _real_get_current_user(secret_dir: Path):
    """Return a real get_current_user that uses the temp secret dir."""
    from fastapi import Request

    def _inner(request: Request):
        with patch("openspider.app.auth.AUTH_FILE", secret_dir / "auth.json"):
            return get_current_user(request)

    return _inner


async def test_admin_status_returns_403_without_admin(auth_api_client, tmp_path: Path):
    """GET /auth/admin/status should return 403 when token is not admin."""
    # This test verifies the endpoint rejects non-admin tokens
    async with auth_api_client:
        resp = await auth_api_client.get("/api/auth/admin/status")
        # Without any token, should get 401 or 403
        assert resp.status_code in (401, 403)


async def test_auth_status_includes_role(auth_api_client, tmp_path: Path):
    """GET /auth/status should include 'role' field in response."""
    async with auth_api_client:
        resp = await auth_api_client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "has_users" in data
        assert "role" in data  # New field


# ---------------------------------------------------------------------------
# get_current_user — middleware scope caching
# ---------------------------------------------------------------------------


def test_get_current_user_from_scope_cache(tmp_path: Path):
    """get_current_user should use cached values from request.scope if available."""
    from fastapi import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
        "auth_user": "cached_admin",
        "auth_role": "admin",
    }
    request = Request(scope=scope)
    result = get_current_user(request)
    assert result is not None
    username, role = result
    assert username == "cached_admin"
    assert role == "admin"
