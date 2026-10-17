# -*- coding: utf-8 -*-
"""Project persistence, ownership, stale-write protection, and chat context."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from openspider.app import user_data_store as storage
from openspider.app.projects import (
    ProjectInput, ProjectStore, project_context_for_session,
)
from openspider.app.routers import projects as routes


@pytest.fixture
async def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_DIR", tmp_path)
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "projects.db")
    db = storage.UserDataStore()
    await db.start()
    app = FastAPI()
    app.state.user_data_store = db
    app.state.project_store = ProjectStore(db)
    workspace = SimpleNamespace(
        agent_id="analyst", chat_manager=SimpleNamespace(
            create_chat=AsyncMock(side_effect=lambda spec: spec),
            list_chats=AsyncMock(return_value=[]), get_chat=AsyncMock(return_value=None),
        ),
    )
    monkeypatch.setattr(routes, "get_agent_for_request", AsyncMock(return_value=workspace))

    @app.middleware("http")
    async def identity(request, call_next):
        # Trusted identity normally comes from the real AuthMiddleware.
        request.scope["auth_user"] = request.headers.get("x-test-user", "alice")
        request.scope["auth_role"] = "user"
        return await call_next(request)

    app.include_router(routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, app, db, workspace
    await db.close()


async def test_project_round_trip_and_owner_isolation(environment):
    client, _, _, _ = environment
    response = await client.post("/projects", json={"name": "Churn research", "objective": "Evaluate churn drivers"})
    assert response.status_code == 201
    project = response.json()
    assert (await client.get(f"/projects/{project['id']}")).json() == project
    assert (await client.get("/projects", headers={"x-test-user": "bob"})).json() == []
    assert (await client.get(f"/projects/{project['id']}", headers={"x-test-user": "bob"})).status_code == 404
    body = {**ProjectInput(name="Stolen").model_dump(), "version": project["version"]}
    assert (await client.put(f"/projects/{project['id']}", json=body, headers={"x-test-user": "bob"})).status_code == 404


async def test_projects_survive_store_restart_and_concurrent_creation(environment):
    _, app, db, _ = environment
    store = app.state.project_store
    await asyncio.gather(*(store.save("alice", ProjectInput(name=f"Project {i}")) for i in range(10)))
    await db.save_mcp_server("alice", {"id": "persisted-mcp", "name": "Warehouse"})
    await db.save_knowledge_document("alice", {"id": "persisted-doc", "filename": "notes.md"})
    await db.close()
    await db.start()
    restored = ProjectStore(db)
    assert len(await restored.list("alice")) == 10
    assert await restored.list("bob") == []
    assert (await db.get_mcp_server("alice", "persisted-mcp"))["name"] == "Warehouse"
    assert (await db.get_knowledge_document("alice", "persisted-doc"))["filename"] == "notes.md"


async def test_stale_updates_do_not_overwrite_another_tab(environment):
    client, _, _, _ = environment
    project = (await client.post("/projects", json={"name": "Original"})).json()
    body = {**ProjectInput(name="First edit").model_dump(), "version": project["version"]}
    assert (await client.put(f"/projects/{project['id']}", json=body)).status_code == 200
    body["name"] = "Stale edit"
    assert (await client.put(f"/projects/{project['id']}", json=body)).status_code == 409
    assert (await client.get(f"/projects/{project['id']}")).json()["name"] == "First edit"


async def test_connections_are_owned_and_never_return_secrets(environment):
    client, _, db, _ = environment
    await db.save_mcp_server("alice", {"id": "warehouse", "name": "Warehouse", "headers": '{"Authorization":"private-value"}', "env": '{"KEY":"private-value"}'})
    connections = await client.get("/projects/connections")
    assert connections.status_code == 200
    assert "private-value" not in connections.text
    assert "headers" not in connections.text
    assert (await client.get("/projects/connections", headers={"x-test-user": "bob"})).json() == []
    body = {"name": "EDA", "connection_ids": ["warehouse"]}
    assert (await client.post("/projects", json=body)).status_code == 201
    assert (await client.post("/projects", json=body, headers={"x-test-user": "bob"})).status_code == 422


async def test_project_chat_and_context_use_authorized_project(environment):
    client, app, _, workspace = environment
    project = (await client.post("/projects", json={"name": "Research", "instructions": "Check data leakage", "objective": "Compare baselines"})).json()
    response = await client.post(f"/projects/{project['id']}/chats", json={})
    assert response.status_code == 201
    chat = response.json()
    assert chat["user_id"] == "alice"
    assert chat["agent_id"] == "analyst"
    assert chat["meta"]["project_id"] == project["id"]
    request = Request({"type": "http", "app": app, "headers": [], "auth_user": "alice"})
    owner, context = await project_context_for_session(request, chat["session_id"])
    assert owner == "alice"
    assert "Check data leakage" in context and "Compare baselines" in context
    request.scope["auth_user"] = "bob"
    with pytest.raises(HTTPException) as exc:
        await project_context_for_session(request, chat["session_id"])
    assert exc.value.status_code == 404
    assert (await client.post(f"/projects/{project['id']}/chats", json={}, headers={"x-test-user": "bob"})).status_code == 404
    assert workspace.chat_manager.create_chat.await_count == 1


async def test_archive_blocks_new_work_and_restore_allows_it(environment):
    client, _, _, _ = environment
    project = (await client.post("/projects", json={"name": "EDA"})).json()
    body = {**ProjectInput(name="EDA", status="archived").model_dump(), "version": 1}
    archived = (await client.put(f"/projects/{project['id']}", json=body)).json()
    assert (await client.post(f"/projects/{project['id']}/chats", json={})).status_code == 409
    body.update(status="active", version=archived["version"])
    assert (await client.put(f"/projects/{project['id']}", json=body)).status_code == 200
    assert (await client.post(f"/projects/{project['id']}/chats", json={})).status_code == 201


async def test_invalid_input_and_session_names_are_rejected(environment):
    client, app, _, _ = environment
    for body in ({"name": "   "}, {"name": "x", "owner": "bob"}, {"name": "x", "instructions": "x" * 12001}):
        assert (await client.post("/projects", json=body)).status_code == 422
    assert (await client.get("/projects/not-a-uuid")).status_code == 422
    request = Request({"type": "http", "app": app, "headers": [], "auth_user": "alice"})
    assert await project_context_for_session(request, "ordinary-session") is None
    with pytest.raises(HTTPException) as exc:
        await project_context_for_session(request, f"project:{uuid4()}:invalid")
    assert exc.value.status_code == 400


async def test_conversation_lists_exclude_other_projects_and_users(environment):
    client, _, _, workspace = environment
    project = (await client.post("/projects", json={"name": "Research"})).json()
    created = await client.post(f"/projects/{project['id']}/chats", json={})
    from openspider.app.runner.models import ChatSpec
    own = ChatSpec.model_validate(created.json())
    other = own.model_copy(update={"id": str(uuid4()), "meta": {"project_id": str(uuid4())}})
    workspace.chat_manager.list_chats.return_value = [own, other]
    response = await client.get(f"/projects/{project['id']}/chats")
    assert [chat["id"] for chat in response.json()] == [own.id]
    workspace.chat_manager.list_chats.assert_awaited_with(user_id="alice", channel="console")


async def test_chat_banner_does_not_expose_other_users_project(environment):
    client, _, _, workspace = environment
    project = (await client.post("/projects", json={"name": "Research"})).json()
    await client.post(f"/projects/{project['id']}/chats", json={})
    chat = workspace.chat_manager.create_chat.call_args.args[0]
    workspace.chat_manager.get_chat.return_value = chat
    assert (await client.get(f"/projects/chat-context/{chat.id}")).json()["id"] == project["id"]
    assert (await client.get(f"/projects/chat-context/{chat.id}", headers={"x-test-user": "bob"})).status_code == 404
