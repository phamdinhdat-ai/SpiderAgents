# -*- coding: utf-8 -*-
"""Authentication API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..auth import (
    authenticate,
    create_user_admin,
    delete_user,
    get_current_admin,
    get_current_user,
    get_user_count,
    has_registered_users,
    is_auth_enabled,
    list_users,
    register_user,
    revoke_all_tokens,
    revoke_token,
    update_credentials,
    update_user_role,
    verify_token,
)
from ..users.models import (
    AdminSessionsResponse,
    AdminUserSessionsResponse,
    UserSessionInfo,
)
from ..users.tracker import UserSessionTracker

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


class LoginResponse(BaseModel):
    token: str
    username: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


class AuthStatusResponse(BaseModel):
    enabled: bool
    has_users: bool
    role: str | None = None


class AdminStatusResponse(BaseModel):
    username: str
    role: str


# AdminSessionsResponse is imported from ..users.models for the
# richer multi-user session tracking response.


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate with username and password.

    Optional `expires_in` field:
    - Positive integer: token expires in N seconds
    - 0 or -1: permanent token (100 years)
    - None/omitted: default 7 days
    """
    if not is_auth_enabled():
        return LoginResponse(token="", username="")

    token = authenticate(req.username, req.password, req.expires_in)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return LoginResponse(token=token, username=req.username)


@router.post("/register")
async def register(req: RegisterRequest):
    """Register the first user account (only allowed when no users exist).

    After the first admin is created, additional users must be created
    by an admin via ``POST /auth/admin/create-user``.

    Optional `expires_in` field:
    - Positive integer: token expires in N seconds
    - 0 or -1: permanent token (100 years)
    - None/omitted: default 7 days
    """
    if not is_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Authentication is not enabled",
        )

    if has_registered_users():
        raise HTTPException(
            status_code=403,
            detail="Initial admin already registered. Additional users must be created by an admin.",
        )

    if not req.username.strip() or not req.password.strip():
        raise HTTPException(
            status_code=400,
            detail="Username and password are required",
        )

    token = register_user(req.username.strip(), req.password, req.expires_in)
    if token is None:
        raise HTTPException(
            status_code=409,
            detail="Registration failed",
        )

    return LoginResponse(token=token, username=req.username.strip())


@router.get("/status")
async def auth_status(request: Request):
    """Check if authentication is enabled and whether a user exists."""
    role: str | None = None
    if is_auth_enabled():
        user_info = get_current_user(request)
        if user_info is not None:
            role = user_info[1]
    return AuthStatusResponse(
        enabled=is_auth_enabled(),
        has_users=has_registered_users(),
        role=role,
    )


@router.get("/verify")
async def verify(request: Request):
    """Verify that the caller's Bearer token is still valid."""
    if not is_auth_enabled():
        return {"valid": True, "username": ""}

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    result = verify_token(token)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    username, role = result
    return {"valid": True, "username": username, "role": role}


class UpdateProfileRequest(BaseModel):
    current_password: str
    new_username: str | None = None
    new_password: str | None = None
    expires_in: int | None = (
        None  # Token expiry in seconds, -1/0 for permanent
    )


@router.post("/update-profile")
async def update_profile(req: UpdateProfileRequest, request: Request):
    """Update username and/or password for the authenticated user."""
    if not is_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Authentication is not enabled",
        )

    if not has_registered_users():
        raise HTTPException(
            status_code=403,
            detail="No user registered",
        )

    # Verify caller is authenticated and get current username
    user_info = get_current_user(request)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    current_username = user_info[0]

    if not req.new_username and not req.new_password:
        raise HTTPException(
            status_code=400,
            detail="Nothing to update",
        )

    if req.new_username is not None and not req.new_username.strip():
        raise HTTPException(
            status_code=400,
            detail="Username cannot be empty",
        )

    if req.new_password is not None and not req.new_password.strip():
        raise HTTPException(
            status_code=400,
            detail="Password cannot be empty",
        )

    token = update_credentials(
        current_password=req.current_password,
        current_username=current_username,
        new_username=req.new_username,
        new_password=req.new_password,
        expiry_seconds=req.expires_in,
    )
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Current password is incorrect",
        )

    username = req.new_username.strip() if req.new_username else ""
    return LoginResponse(token=token, username=username)


class RevokeTokenRequest(BaseModel):
    token: str | None = (
        None  # Optional: revoke specific token, or current if omitted
    )


@router.post("/revoke-token")
async def revoke_single_token(req: RevokeTokenRequest, request: Request):
    """Revoke a single token by adding it to the blacklist.

    If `token` is provided in the request body, revokes that token.
    If `token` is omitted, revokes the token used for authentication
    (current token).

    This allows you to:
    - Revoke a leaked token from another device
    - Logout from the current session
    """
    if not is_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Authentication is not enabled",
        )

    # Get current token for authentication
    auth_header = request.headers.get("Authorization", "")
    caller_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    user_info = get_current_user(request)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Determine which token to revoke
    token_to_revoke = req.token if req.token else caller_token
    is_current_token = token_to_revoke == caller_token

    success = revoke_token(token_to_revoke)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke token",
        )

    message = (
        "Current token has been revoked. Please login again."
        if is_current_token
        else "Specified token has been revoked."
    )

    return {
        "message": message,
        "revoked": True,
        "revoked_current_token": is_current_token,
    }


@router.post("/revoke-all-tokens")
async def revoke_all_sessions(request: Request):
    """Revoke all existing tokens by rotating the JWT secret.

    This endpoint requires authentication. After calling this endpoint,
    all previously issued tokens will be invalidated, and you will need
    to login again to get a new token.

    This is more efficient than revoking tokens individually when you
    want to invalidate all sessions (e.g., password reset, security incident).
    """
    if not is_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Authentication is not enabled",
        )

    # Verify caller is authenticated
    user_info = get_current_user(request)
    if user_info is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    success = revoke_all_tokens()
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to revoke tokens",
        )

    return {
        "message": "All tokens have been revoked. Please login again.",
        "revoked": True,
    }


# ---------------------------------------------------------------------------
# Admin-only endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/status")
async def admin_status(
    admin: str = Depends(get_current_admin),
):
    """Return the current admin user's status.  Requires admin token."""
    return AdminStatusResponse(username=admin, role="admin")


@router.get("/admin/sessions")
async def admin_sessions(
    admin: str = Depends(get_current_admin),
    agent_id: str = Query("default", description="Agent ID to scope sessions to"),
):
    """List session activity across all users (admin-only).

    Returns per-user aggregate summaries with session counts, message
    counts, last-active timestamps, and active/running session counts.
    """
    tracker = UserSessionTracker()
    return await tracker.get_all_users_summary(agent_id=agent_id)


@router.get(
    "/admin/users/{username}/sessions",
    response_model=AdminUserSessionsResponse,
)
async def admin_user_sessions(
    username: str,
    admin: str = Depends(get_current_admin),
    agent_id: str = Query("default", description="Agent ID to scope sessions to"),
):
    """List all sessions for a specific user (admin-only)."""
    tracker = UserSessionTracker()
    sessions = await tracker.get_user_sessions(
        username=username,
        agent_id=agent_id,
    )
    return AdminUserSessionsResponse(
        username=username,
        sessions=sessions,
        total=len(sessions),
    )


class RevokeUserTokensResponse(BaseModel):
    message: str
    revoked: bool = True


@router.post(
    "/admin/users/{username}/revoke-tokens",
    response_model=RevokeUserTokensResponse,
)
async def admin_revoke_user_tokens(
    username: str,
    admin: str = Depends(get_current_admin),
):
    """Force-logout a user by revoking all their tokens.

    Rotates the JWT signing secret, which invalidates all existing
    tokens for **all** users, not just the target user.  This is the
    simplest approach given the current stateless token design.
    """
    if not is_auth_enabled():
        raise HTTPException(
            status_code=403,
            detail="Authentication is not enabled",
        )

    # Verify the target user exists
    users = list_users()
    if not any(u["username"] == username for u in users):
        raise HTTPException(
            status_code=404,
            detail=f"User '{username}' not found",
        )

    success = revoke_all_tokens()
    return RevokeUserTokensResponse(
        message=(
            f"All tokens revoked (including '{username}'). "
            "All users must login again."
        ),
        revoked=success,
    )


@router.delete("/admin/users/{username}/sessions/{session_id}")
async def admin_delete_user_session(
    username: str,
    session_id: str,
    admin: str = Depends(get_current_admin),
    agent_id: str = Query("default", description="Agent ID"),
):
    """Delete a specific session file for a user (admin-only)."""
    tracker = UserSessionTracker()
    deleted = await tracker.delete_user_session_file(
        username=username,
        session_id=session_id,
        agent_id=agent_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found for user '{username}'",
        )
    return {"message": f"Session '{session_id}' deleted for '{username}'"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserInfo(BaseModel):
    username: str
    role: str


class UserListResponse(BaseModel):
    users: list[UserInfo]
    total: int


@router.get("/admin/users")
async def admin_list_users(
    admin: str = Depends(get_current_admin),
):
    """List all registered users (admin-only)."""
    users = list_users()
    return UserListResponse(
        users=[UserInfo(**u) for u in users],
        total=len(users),
    )


@router.post("/admin/create-user")
async def admin_create_user(
    req: CreateUserRequest,
    admin: str = Depends(get_current_admin),
):
    """Create a new user account (admin-only)."""
    if not req.username.strip() or not req.password.strip():
        raise HTTPException(
            status_code=400,
            detail="Username and password are required",
        )
    if req.role not in ("admin", "user"):
        raise HTTPException(
            status_code=400,
            detail="Role must be 'admin' or 'user'",
        )

    token = create_user_admin(req.username.strip(), req.password, req.role)
    if token is None:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )
    return {
        "message": f"User '{req.username.strip()}' created",
        "username": req.username.strip(),
        "role": req.role,
    }


class UpdateRoleRequest(BaseModel):
    role: str


@router.put("/admin/users/{username}/role")
async def admin_update_role(
    username: str,
    req: UpdateRoleRequest,
    admin: str = Depends(get_current_admin),
):
    """Change a user's role (admin-only)."""
    if req.role not in ("admin", "user"):
        raise HTTPException(
            status_code=400,
            detail="Role must be 'admin' or 'user'",
        )

    if not update_user_role(username, req.role):
        raise HTTPException(
            status_code=404,
            detail="User not found or invalid role",
        )
    return {"message": f"Role updated for '{username}'", "username": username, "role": req.role}


@router.delete("/admin/users/{username}")
async def admin_delete_user(
    username: str,
    admin: str = Depends(get_current_admin),
):
    """Delete a user account (admin-only, cannot delete self)."""
    if not delete_user(username, admin):
        if username == admin:
            raise HTTPException(
                status_code=403,
                detail="Cannot delete your own account",
            )
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return {"message": f"User '{username}' deleted"}
