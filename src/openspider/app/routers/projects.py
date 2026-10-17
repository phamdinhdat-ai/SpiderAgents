# -*- coding: utf-8 -*-
"""Owner-scoped project management and project conversation entry points."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from ..agent_context import get_agent_for_request
from ..projects import (
    Project, ProjectChatInput, ProjectConnection, ProjectInput, ProjectUpdate,
    get_project_store, project_owner,
)
from ..runner.models import ChatSpec

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[Project])
async def list_projects(request: Request):
    return await get_project_store(request).list(project_owner(request))


@router.post("", response_model=Project, status_code=201)
async def create_project(body: ProjectInput, request: Request):
    return await get_project_store(request).save(project_owner(request), body)


@router.get("/connections", response_model=list[ProjectConnection])
async def list_project_connections(request: Request):
    store = get_project_store(request)
    rows = await store.data_store.list_mcp_servers(project_owner(request))
    return [ProjectConnection(
        id=row["id"], name=row["name"],
        transport=row.get("transport") or "stdio", enabled=bool(row.get("enabled", True)),
    ) for row in rows]


@router.get("/chat-context/{chat_id}", response_model=Project | None)
async def get_project_chat_context(chat_id: str, request: Request):
    owner = project_owner(request)
    workspace = await get_agent_for_request(request)
    chat = await workspace.chat_manager.get_chat(chat_id)
    if chat is None or chat.user_id != owner:
        raise HTTPException(404, "Conversation not found")
    project_id = chat.meta.get("project_id")
    if not project_id:
        return None
    return await get_project_store(request).get(owner, UUID(project_id))


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: UUID, request: Request):
    return await get_project_store(request).get(project_owner(request), project_id)


@router.put("/{project_id}", response_model=Project)
async def update_project(project_id: UUID, body: ProjectUpdate, request: Request):
    return await get_project_store(request).save(project_owner(request), body, project_id)


@router.get("/{project_id}/chats", response_model=list[ChatSpec])
async def list_project_chats(project_id: UUID, request: Request):
    owner = project_owner(request)
    await get_project_store(request).get(owner, project_id)
    workspace = await get_agent_for_request(request)
    chats = await workspace.chat_manager.list_chats(user_id=owner, channel="console")
    return sorted(
        [chat for chat in chats if chat.meta.get("project_id") == str(project_id)],
        key=lambda chat: chat.updated_at, reverse=True,
    )


@router.post("/{project_id}/chats", response_model=ChatSpec, status_code=201)
async def create_project_chat(project_id: UUID, body: ProjectChatInput, request: Request):
    owner = project_owner(request)
    project = await get_project_store(request).get(owner, project_id)
    if project.status == "archived":
        raise HTTPException(409, "Restore this project before starting a conversation")
    workspace = await get_agent_for_request(request)
    return await workspace.chat_manager.create_chat(ChatSpec(
        name=body.name,
        session_id=f"project:{project.id}:{uuid4()}",
        user_id=owner,
        channel="console",
        agent_id=workspace.agent_id,
        meta={"project_id": str(project.id)},
    ))
