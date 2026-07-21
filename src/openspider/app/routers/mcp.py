# -*- coding: utf-8 -*-
"""API routes for MCP (Model Context Protocol) clients management."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Body, HTTPException, Path, Request
from pydantic import BaseModel, Field

from ..utils import schedule_agent_reload
from ...config.config import MCPClientConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPClientInfo(BaseModel):
    """MCP client information for API responses."""

    key: str = Field(..., description="Unique client key identifier")
    name: str = Field(..., description="Client display name")
    description: str = Field(default="", description="Client description")
    enabled: bool = Field(..., description="Whether the client is enabled")
    transport: Literal["stdio", "streamable_http", "sse"] = Field(
        ...,
        description="MCP transport type",
    )
    url: str = Field(
        default="",
        description="Remote MCP endpoint URL (for HTTP/SSE transports)",
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers for remote transport",
    )
    command: str = Field(
        default="",
        description="Command to launch the MCP server",
    )
    args: List[str] = Field(
        default_factory=list,
        description="Command-line arguments",
    )
    env: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables",
    )
    cwd: str = Field(
        default="",
        description="Working directory for stdio MCP command",
    )


class MCPClientCreateRequest(BaseModel):
    """Request body for creating/updating an MCP client."""

    name: str = Field(..., description="Client display name")
    description: str = Field(default="", description="Client description")
    enabled: bool = Field(
        default=True,
        description="Whether to enable the client",
    )
    transport: Literal["stdio", "streamable_http", "sse"] = Field(
        default="stdio",
        description="MCP transport type",
    )
    url: str = Field(
        default="",
        description="Remote MCP endpoint URL (for HTTP/SSE transports)",
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers for remote transport",
    )
    command: str = Field(
        default="",
        description="Command to launch the MCP server",
    )
    args: List[str] = Field(
        default_factory=list,
        description="Command-line arguments",
    )
    env: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables",
    )
    cwd: str = Field(
        default="",
        description="Working directory for stdio MCP command",
    )


class MCPClientUpdateRequest(BaseModel):
    """Request body for updating an MCP client (all fields optional)."""

    name: Optional[str] = Field(None, description="Client display name")
    description: Optional[str] = Field(None, description="Client description")
    enabled: Optional[bool] = Field(
        None,
        description="Whether to enable the client",
    )
    transport: Optional[Literal["stdio", "streamable_http", "sse"]] = Field(
        None,
        description="MCP transport type",
    )
    url: Optional[str] = Field(
        None,
        description="Remote MCP endpoint URL (for HTTP/SSE transports)",
    )
    headers: Optional[Dict[str, str]] = Field(
        None,
        description="HTTP headers for remote transport",
    )
    command: Optional[str] = Field(
        None,
        description="Command to launch the MCP server",
    )
    args: Optional[List[str]] = Field(
        None,
        description="Command-line arguments",
    )
    env: Optional[Dict[str, str]] = Field(
        None,
        description="Environment variables",
    )
    cwd: Optional[str] = Field(
        None,
        description="Working directory for stdio MCP command",
    )


def _restore_original_values(
    incoming: Dict[str, str],
    existing: Dict[str, str],
) -> Dict[str, str]:
    """Preserve original values when incoming matches their masked form."""
    restored: Dict[str, str] = {}
    for k, v in incoming.items():
        if k in existing and v == _mask_env_value(existing[k]):
            restored[k] = existing[k]
        else:
            restored[k] = v
    return restored


def _mask_env_value(value: str) -> str:
    """
    Mask environment variable value showing first 2-3 chars and last 4 chars.

    Examples:
        sk-proj-1234567890abcdefghij1234 -> sk-****************************1234
        abc123456789xyz -> ab***********xyz (if no dash)
        my-api-key-value -> my-************lue
        short123 -> ******** (8 chars or less, fully masked)
    """
    if not value:
        return value

    length = len(value)
    if length <= 8:
        # For short values, just mask everything
        return "*" * length

    # Show first 2-3 characters (3 if there's a dash at position 2)
    prefix_len = 3 if length > 2 and value[2] == "-" else 2
    prefix = value[:prefix_len]

    # Show last 4 characters
    suffix = value[-4:]

    # Calculate masked section length (at least 4 asterisks)
    masked_len = max(length - prefix_len - 4, 4)

    return f"{prefix}{'*' * masked_len}{suffix}"


def _build_client_info(key: str, client: MCPClientConfig) -> MCPClientInfo:
    """Build MCPClientInfo from config with masked env values."""
    # Mask environment variable values for security
    masked_env = (
        {k: _mask_env_value(v) for k, v in client.env.items()}
        if client.env
        else {}
    )
    masked_headers = (
        {k: _mask_env_value(v) for k, v in client.headers.items()}
        if client.headers
        else {}
    )

    return MCPClientInfo(
        key=key,
        name=client.name,
        description=client.description,
        enabled=client.enabled,
        transport=client.transport,
        url=client.url,
        headers=masked_headers,
        command=client.command,
        args=client.args,
        env=masked_env,
        cwd=client.cwd,
    )


def _safe_json_field(row: dict, field: str) -> Any:
    """Safely extract a JSON field from a DB row, returning the parsed
    value or an empty dict/list as appropriate."""
    raw = row.get(field)
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {} if field in ("headers", "env") else []


def _mask_env_dict(env: dict) -> dict:
    """Mask all values in an environment dict for API responses."""
    if not env:
        return {}
    return {k: _mask_env_value(v) for k, v in env.items()}


class MCPToolInfo(BaseModel):
    """MCP tool information returned from a connected server."""

    name: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Tool description")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the tool's input parameters",
    )


@router.get(
    "/{client_key}/tools",
    response_model=List[MCPToolInfo],
    summary="List tools from a connected MCP server",
)
async def list_mcp_tools(
    request: Request,
    client_key: str = Path(...),
) -> List[MCPToolInfo]:
    """Query a running MCP server for its available tools.

    Returns 503 if the client is not yet connected, empty list if
    disabled, or 502 if the MCP server query fails.
    """
    from ..agent_context import get_agent_for_request

    # Check user-scoped store first, then fall back to agent config
    store = _get_user_data_store(request)
    username = _resolve_username(request)
    user_mcp = await store.get_mcp_server(username, client_key)

    agent = await get_agent_for_request(request)

    # Determine if client is enabled: check UserDataStore first
    if user_mcp is not None:
        if not user_mcp.get("enabled", True):
            return []
    else:
        # Fallback: check agent config
        mcp_config = agent.config.mcp
        if mcp_config is None or client_key not in (mcp_config.clients or {}):
            raise HTTPException(404, detail=f"MCP client '{client_key}' not found")
        if not mcp_config.clients[client_key].enabled:
            return []

    mcp_manager = agent.mcp_manager
    if mcp_manager is None:
        raise HTTPException(
            503,
            detail="MCP manager is not ready yet, please try again later",
        )

    client = await mcp_manager.get_client(client_key)
    if client is None or not getattr(client, "is_connected", False):
        raise HTTPException(
            503,
            detail="MCP server is still connecting, please try again later",
        )

    try:
        tools = await client.list_tools()
    except Exception as e:
        logger.warning(
            f"Failed to list tools for MCP client '{client_key}': {e}",
        )
        raise HTTPException(
            502,
            detail=f"Failed to query tools from MCP server: {e}",
        ) from e

    return [
        MCPToolInfo(
            name=t.name,
            description=getattr(t, "description", "") or "",
            input_schema=getattr(t, "inputSchema", {}) or {},
        )
        for t in tools
    ]


def _get_user_data_store(request: Request):
    """Get UserDataStore from app state."""
    store = getattr(request.app.state, "user_data_store", None)
    if store is None:
        raise HTTPException(
            503,
            detail="User data store is not available yet, please try again later",
        )
    return store


def _resolve_username(request: Request) -> str:
    """Resolve the authenticated username, falling back to 'default'."""
    from ..agent_context import get_current_auth_user_id

    user_id = get_current_auth_user_id()
    return user_id or "default"


@router.get(
    "",
    response_model=List[MCPClientInfo],
    summary="List all MCP clients",
)
async def list_mcp_clients(request: Request) -> List[MCPClientInfo]:
    """Get list of all configured MCP clients for the current user."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)
    rows = await store.list_mcp_servers(username)

    return [
        MCPClientInfo(
            key=row["id"],
            name=row["name"],
            description=row.get("description", ""),
            enabled=bool(row.get("enabled", True)),
            transport=row.get("transport", "stdio"),
            url=row.get("url", ""),
            headers=_safe_json_field(row, "headers"),
            command=row.get("command", ""),
            args=_safe_json_field(row, "args"),
            env=_mask_env_dict(_safe_json_field(row, "env")),
            cwd=row.get("cwd", ""),
        )
        for row in rows
    ]


@router.get(
    "/{client_key}",
    response_model=MCPClientInfo,
    summary="Get MCP client details",
)
async def get_mcp_client(
    request: Request,
    client_key: str = Path(...),
) -> MCPClientInfo:
    """Get details of a specific MCP client."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)
    row = await store.get_mcp_server(username, client_key)
    if row is None:
        raise HTTPException(404, detail=f"MCP client '{client_key}' not found")
    return MCPClientInfo(
        key=row["id"],
        name=row["name"],
        description=row.get("description", ""),
        enabled=bool(row.get("enabled", True)),
        transport=row.get("transport", "stdio"),
        url=row.get("url", ""),
        headers=_mask_env_dict(_safe_json_field(row, "headers")),
        command=row.get("command", ""),
        args=_safe_json_field(row, "args"),
        env=_mask_env_dict(_safe_json_field(row, "env")),
        cwd=row.get("cwd", ""),
    )


@router.post(
    "",
    response_model=MCPClientInfo,
    summary="Create a new MCP client",
    status_code=201,
)
async def create_mcp_client(
    request: Request,
    client_key: str = Body(..., embed=True),
    client: MCPClientCreateRequest = Body(..., embed=True),
) -> MCPClientInfo:
    """Create a new MCP client configuration for the current user."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)

    # Check if client already exists for this user
    existing = await store.get_mcp_server(username, client_key)
    if existing is not None:
        raise HTTPException(
            400,
            detail=f"MCP client '{client_key}' already exists. Use PUT to "
            f"update.",
        )

    now = json.dumps(None)  # placeholder, save_mcp_server handles timestamps
    row = await store.save_mcp_server(
        username,
        {
            "id": client_key,
            "name": client.name,
            "description": client.description,
            "enabled": client.enabled,
            "transport": client.transport,
            "url": client.url,
            "headers": client.headers,
            "command": client.command,
            "args": client.args,
            "env": client.env,
            "cwd": client.cwd,
        },
    )

    # Also update the active agent's MCP config so the MCP manager picks
    # up the new client (backward compatibility + runtime integration)
    try:
        from ..agent_context import get_agent_for_request
        from ...config.config import save_agent_config, MCPConfig

        agent = await get_agent_for_request(request)
        if agent.config.mcp is None:
            agent.config.mcp = MCPConfig(clients={})
        agent.config.mcp.clients[client_key] = MCPClientConfig(
            name=client.name,
            description=client.description,
            enabled=client.enabled,
            transport=client.transport,
            url=client.url,
            headers=client.headers,
            command=client.command,
            args=client.args,
            env=client.env,
            cwd=client.cwd,
        )
        save_agent_config(agent.agent_id, agent.config)
        schedule_agent_reload(request, agent.agent_id)
    except Exception:
        logger.warning(
            "Failed to sync MCP client '%s' to agent config (will be "
            "available after agent restart)",
            client_key,
        )

    return MCPClientInfo(
        key=client_key,
        name=client.name,
        description=client.description,
        enabled=client.enabled,
        transport=client.transport,
        url=client.url,
        headers=_mask_env_dict(client.headers or {}),
        command=client.command,
        args=client.args,
        env=_mask_env_dict(client.env or {}),
        cwd=client.cwd,
    )


@router.put(
    "/{client_key}",
    response_model=MCPClientInfo,
    summary="Update an MCP client",
)
async def update_mcp_client(
    request: Request,
    client_key: str = Path(...),
    updates: MCPClientUpdateRequest = Body(...),
) -> MCPClientInfo:
    """Update an existing MCP client configuration."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)

    existing = await store.get_mcp_server(username, client_key)
    if existing is None:
        raise HTTPException(404, detail=f"MCP client '{client_key}' not found")

    # Merge updates into existing data
    merged = dict(existing)
    update_data = updates.model_dump(exclude_unset=True)

    # Restore masked env/header values to originals before replacing
    if "env" in update_data and update_data["env"] is not None:
        update_data["env"] = _restore_original_values(
            update_data["env"],
            _safe_json_field(existing, "env"),
        )

    if "headers" in update_data and update_data["headers"] is not None:
        update_data["headers"] = _restore_original_values(
            update_data["headers"],
            _safe_json_field(existing, "headers"),
        )

    for key, value in update_data.items():
        if value is not None:
            if key in ("env", "headers", "args"):
                merged[key] = json.dumps(value) if isinstance(value, (dict, list)) else value
            else:
                merged[key] = value

    row = await store.save_mcp_server(username, merged)

    # Also sync to agent config for runtime
    try:
        from ..agent_context import get_agent_for_request
        from ...config.config import save_agent_config, MCPConfig

        agent = await get_agent_for_request(request)
        if agent.config.mcp is None:
            agent.config.mcp = MCPConfig(clients={})
        agent.config.mcp.clients[client_key] = MCPClientConfig(
            name=row["name"],
            description=row.get("description", ""),
            enabled=bool(row.get("enabled", True)),
            transport=row.get("transport", "stdio"),
            url=row.get("url", ""),
            headers=_safe_json_field(row, "headers"),
            command=row.get("command", ""),
            args=_safe_json_field(row, "args"),
            env=_safe_json_field(row, "env"),
            cwd=row.get("cwd", ""),
        )
        save_agent_config(agent.agent_id, agent.config)
        schedule_agent_reload(request, agent.agent_id)
    except Exception:
        logger.warning(
            "Failed to sync updated MCP client '%s' to agent config",
            client_key,
        )

    return MCPClientInfo(
        key=client_key,
        name=row["name"],
        description=row.get("description", ""),
        enabled=bool(row.get("enabled", True)),
        transport=row.get("transport", "stdio"),
        url=row.get("url", ""),
        headers=_mask_env_dict(_safe_json_field(row, "headers")),
        command=row.get("command", ""),
        args=_safe_json_field(row, "args"),
        env=_mask_env_dict(_safe_json_field(row, "env")),
        cwd=row.get("cwd", ""),
    )


@router.patch(
    "/{client_key}/toggle",
    response_model=MCPClientInfo,
    summary="Toggle MCP client enabled status",
)
async def toggle_mcp_client(
    request: Request,
    client_key: str = Path(...),
) -> MCPClientInfo:
    """Toggle the enabled status of an MCP client."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)

    existing = await store.get_mcp_server(username, client_key)
    if existing is None:
        raise HTTPException(404, detail=f"MCP client '{client_key}' not found")

    # Toggle enabled
    merged = dict(existing)
    merged["enabled"] = 0 if existing.get("enabled") else 1
    row = await store.save_mcp_server(username, merged)

    # Sync to agent config
    try:
        from ..agent_context import get_agent_for_request
        from ...config.config import save_agent_config

        agent = await get_agent_for_request(request)
        if agent.config.mcp and client_key in agent.config.mcp.clients:
            agent.config.mcp.clients[client_key].enabled = bool(merged["enabled"])
            save_agent_config(agent.agent_id, agent.config)
            schedule_agent_reload(request, agent.agent_id)
    except Exception:
        pass

    return MCPClientInfo(
        key=client_key,
        name=row["name"],
        description=row.get("description", ""),
        enabled=bool(row.get("enabled", True)),
        transport=row.get("transport", "stdio"),
        url=row.get("url", ""),
        headers=_mask_env_dict(_safe_json_field(row, "headers")),
        command=row.get("command", ""),
        args=_safe_json_field(row, "args"),
        env=_mask_env_dict(_safe_json_field(row, "env")),
        cwd=row.get("cwd", ""),
    )


@router.delete(
    "/{client_key}",
    response_model=Dict[str, str],
    summary="Delete an MCP client",
)
async def delete_mcp_client(
    request: Request,
    client_key: str = Path(...),
) -> Dict[str, str]:
    """Delete an MCP client configuration."""
    store = _get_user_data_store(request)
    username = _resolve_username(request)

    deleted = await store.delete_mcp_server(username, client_key)
    if not deleted:
        raise HTTPException(404, detail=f"MCP client '{client_key}' not found")

    # Sync to agent config
    try:
        from ..agent_context import get_agent_for_request
        from ...config.config import save_agent_config

        agent = await get_agent_for_request(request)
        if agent.config.mcp and client_key in agent.config.mcp.clients:
            del agent.config.mcp.clients[client_key]
            save_agent_config(agent.agent_id, agent.config)
            schedule_agent_reload(request, agent.agent_id)
    except Exception:
        pass

    return {"message": f"MCP client '{client_key}' deleted successfully"}
