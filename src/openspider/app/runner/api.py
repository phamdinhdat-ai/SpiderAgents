# -*- coding: utf-8 -*-
"""Chat management API."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from agentscope.memory import InMemoryMemory

logger = logging.getLogger(__name__)

from .session import SafeJSONSession
from .manager import ChatManager
from .models import (
    ChatSpec,
    ChatUpdate,
    ChatHistory,
)
from .utils import agentscope_msg_to_message


router = APIRouter(prefix="/chats", tags=["chats"])


async def _authorize_chat(
    request: Request,
    mgr: ChatManager,
    chat_id: str,
) -> ChatSpec:
    """Return the ChatSpec if the caller may access it, else raise 404.

    - Auth disabled → allow any chat.
    - Admin → allow any chat (consistent with list_chats admin access).
    - Non-admin → only own chats; 404 is returned (not 403) so chat
      existence is not leaked to unauthorized callers.
    """
    from ..auth import is_auth_enabled, get_current_user

    chat_spec = await mgr.get_chat(chat_id)
    if not chat_spec:
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")

    if is_auth_enabled():
        caller = get_current_user(request)
        if caller is not None:
            username, role = caller
            if role != "admin" and chat_spec.user_id != username:
                logger.debug(
                    "User '%s' denied access to chat '%s' owned by '%s'",
                    username,
                    chat_id[:12],
                    chat_spec.user_id,
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Chat not found: {chat_id}",
                )

    return chat_spec


def _resolve_authoritative_user_id(
    request: Request,
    client_user_id: str,
) -> str:
    """Return the authoritative user_id for chat creation.

    - Auth disabled → honor client-supplied value.
    - Admin → honor client-supplied value (may create for any user).
    - Non-admin → force caller's username.
    """
    from ..auth import is_auth_enabled, get_current_user

    if not is_auth_enabled():
        return client_user_id

    caller = get_current_user(request)
    if caller is None:
        return client_user_id

    username, role = caller
    if role == "admin":
        return client_user_id
    return username


async def get_workspace(request: Request):
    """Get the workspace for the active agent."""
    from ..agent_context import get_agent_for_request

    return await get_agent_for_request(request)


async def get_chat_manager(
    request: Request,
) -> ChatManager:
    """Get the chat manager for the active agent.

    Args:
        request: FastAPI request object

    Returns:
        ChatManager instance for the specified agent

    Raises:
        HTTPException: If manager is not initialized
    """
    workspace = await get_workspace(request)
    return workspace.chat_manager


async def get_session(
    request: Request,
) -> SafeJSONSession:
    """Get the session for the active agent.

    Args:
        request: FastAPI request object

    Returns:
        SafeJSONSession instance for the specified agent

    Raises:
        HTTPException: If session is not initialized
    """
    workspace = await get_workspace(request)
    return workspace.runner.session


@router.get("", response_model=list[ChatSpec])
async def list_chats(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    mgr: ChatManager = Depends(get_chat_manager),
    workspace=Depends(get_workspace),
):
    """List all chats with optional filters.

    When authentication is enabled, non-admin users are automatically
    scoped to their own chats.  Admin users see all chats.

    Args:
        request: FastAPI request for auth context.
        user_id: Optional user ID to filter chats.
        channel: Optional channel name to filter chats.
        mgr: Chat manager dependency.
    """
    from ..auth import is_auth_enabled, get_current_user

    # Auth-aware scoping: non-admin see only their own chats.
    effective_user_id = user_id
    if is_auth_enabled():
        caller = get_current_user(request)
        if caller is not None:
            caller_username, caller_role = caller
            if caller_role != "admin":
                # Non-admin users can only see their own chats.
                effective_user_id = caller_username

    chats = await mgr.list_chats(user_id=effective_user_id, channel=channel)
    tracker = workspace.task_tracker
    result = []
    for spec in chats:
        status = await tracker.get_status(spec.id)
        result.append(spec.model_copy(update={"status": status}))
    return result


@router.post("", response_model=ChatSpec)
async def create_chat(
    body: ChatSpec,
    fastapi_request: Request,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Create a new chat.

    Server generates chat_id (UUID) automatically.
    Non-admin users cannot set an arbitrary user_id — it is forced
    to the caller's username when auth is enabled.

    Args:
        body: Chat creation request payload
        fastapi_request: FastAPI request (for auth context)
        mgr: Chat manager dependency

    Returns:
        Created chat spec with UUID
    """
    # Enforce authoritative user_id (non-admin → own username)
    user_id = _resolve_authoritative_user_id(fastapi_request, body.user_id)

    chat_id = str(uuid4())
    spec = ChatSpec(
        id=chat_id,
        name=body.name,
        session_id=body.session_id,
        user_id=user_id,
        channel=body.channel,
        meta=body.meta,
    )
    return await mgr.create_chat(spec)


@router.post("/batch-delete", response_model=dict)
async def batch_delete_chats(
    chat_ids: list[str],
    request: Request,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete chats by chat IDs.

    Each chat is authorized before deletion — if any chat is not owned
    by the caller, the entire batch is rejected with a 404.

    Args:
        chat_ids: List of chat IDs
        request: FastAPI request (for auth context)
        mgr: Chat manager dependency
    Returns:
        True if deleted, False if failed
    """
    # Authorize all chats before deleting any (all-or-nothing)
    for cid in chat_ids:
        await _authorize_chat(request, mgr, cid)
    deleted = await mgr.delete_chats(chat_ids=chat_ids)
    return {"deleted": deleted}


@router.get("/{chat_id}", response_model=ChatHistory)
async def get_chat(
    chat_id: str,
    request: Request,
    mgr: ChatManager = Depends(get_chat_manager),
    session: SafeJSONSession = Depends(get_session),
    workspace=Depends(get_workspace),
):
    """Get detailed information about a specific chat by UUID.

    Args:
        request: FastAPI request (for auth context)
        chat_id: Chat UUID
        mgr: Chat manager dependency
        session: SafeJSONSession dependency

    Returns:
        ChatHistory with messages and status (idle/running)

    Raises:
        HTTPException: If chat not found (404) or not owned by caller
    """
    chat_spec = await _authorize_chat(request, mgr, chat_id)

    state = await session.get_session_state_dict(
        chat_spec.session_id,
        chat_spec.user_id,
        chat_spec.channel,
    )
    status = await workspace.task_tracker.get_status(chat_id)
    if not state:
        return ChatHistory(messages=[], status=status)
    memory_state = state.get("agent", {}).get("memory", {})
    memory = InMemoryMemory()
    memory.load_state_dict(memory_state, strict=False)

    memories = await memory.get_memory(prepend_summary=False)
    messages = agentscope_msg_to_message(memories)
    return ChatHistory(messages=messages, status=status)


@router.put("/{chat_id}", response_model=ChatSpec)
async def update_chat(
    chat_id: str,
    spec: ChatUpdate,
    request: Request,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Update an existing chat.

    Args:
        chat_id: Chat UUID
        spec: Partial chat update payload
        request: FastAPI request (for auth context)
        mgr: Chat manager dependency

    Returns:
        Updated chat spec

    Raises:
        HTTPException: If chat not found (404) or not owned by caller
    """
    await _authorize_chat(request, mgr, chat_id)
    updated = await mgr.patch_chat(chat_id, spec)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    return updated


@router.delete("/{chat_id}", response_model=dict)
async def delete_chat(
    chat_id: str,
    request: Request,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete a chat by UUID.

    Note: This only deletes the chat spec (UUID mapping).
    JSONSession state is NOT deleted.

    Args:
        chat_id: Chat UUID
        request: FastAPI request (for auth context)
        mgr: Chat manager dependency

    Returns:
        True if deleted, False if failed

    Raises:
        HTTPException: If chat not found (404) or not owned by caller
    """
    await _authorize_chat(request, mgr, chat_id)
    deleted = await mgr.delete_chats(chat_ids=[chat_id])
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    return {"deleted": True}


@router.get("/all", response_model=list[ChatSpec])
async def list_all_chats(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
):
    """List chats across ALL agents for the current user.

    Unlike ``GET /chats`` which is scoped to the current agent, this
    endpoint aggregates chats from every registered agent workspace.

    Query params:
    - **user_id**: Filter by user ID.
    - **channel**: Filter by channel (default: all).
    - **agent_id**: Filter to a specific agent (omit for all agents).
    """
    from ..agent_context import get_current_auth_user_id, get_current_auth_user_role
    from ..auth import is_auth_enabled, get_current_user
    from ...config.config import load_config

    # Auth-aware scoping
    effective_user_id = user_id
    if is_auth_enabled():
        caller = get_current_user(request)
        if caller is not None:
            caller_username, caller_role = caller
            if caller_role != "admin":
                effective_user_id = caller_username

    config = load_config()
    all_chats: list[ChatSpec] = []

    # Determine which agent IDs to query
    if agent_id:
        target_agents = [agent_id]
    else:
        target_agents = list(config.agents.profiles.keys())

    multi_agent_manager = getattr(request.app.state, "multi_agent_manager", None)
    if multi_agent_manager is None:
        # Fallback: only current workspace
        workspace = await get_workspace(request)
        chats = await workspace.chat_manager.list_chats(
            user_id=effective_user_id, channel=channel, agent_id=agent_id,
        )
        return chats

    for aid in target_agents:
        try:
            ws = await multi_agent_manager.get_agent(aid)
        except Exception:
            continue  # skip agents that failed to load
        if ws is None or ws.chat_manager is None:
            continue
        try:
            chats = await ws.chat_manager.list_chats(
                user_id=effective_user_id, channel=channel, agent_id=aid,
            )
            all_chats.extend(chats)
        except Exception:
            continue  # skip agents whose chat manager is unavailable

    # Sort by updated_at descending (most recent first)
    all_chats.sort(key=lambda c: c.updated_at, reverse=True)
    return all_chats
