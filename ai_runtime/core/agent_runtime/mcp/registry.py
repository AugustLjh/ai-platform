from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from ai_runtime.core.agent_runtime.mcp.client import MCPClient
from ai_runtime.core.agent_runtime.mcp.models import (
    MCPCallToolResponse,
    MCPConnectionTestResult,
    MCPServerDefinition,
    MCPToolCatalogEntry,
)
from ai_runtime.core.agent_runtime.repositories.json_utils import encode_json, parse_json_field


MASK = "********"
SENSITIVE_TOKENS = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "authorization",
    "cookie",
    "client_secret",
    "private_key",
    "bearer",
)
SENSITIVE_CONTAINERS = {"env", "headers", "credentials", "auth"}


def _serialize_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    return any(token in lowered for token in SENSITIVE_TOKENS) or lowered in SENSITIVE_CONTAINERS


def _sanitize_endpoint(endpoint: str | None) -> str:
    text = str(endpoint or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query_items.append((key, MASK if value and _is_sensitive_key(key) else value))
    netloc = parts.netloc
    if parts.username or parts.password:
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        credentials = []
        if parts.username:
            credentials.append(MASK)
        if parts.password:
            credentials.append(MASK)
        netloc = f"{':'.join(credentials)}@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query_items), parts.fragment))


def _collect_secret_values(server: MCPServerDefinition) -> list[str]:
    values: set[str] = set()
    for mapping in (server.env, server.headers):
        for key, value in mapping.items():
            text = str(value or "").strip()
            if text and (_is_sensitive_key(key) or mapping is server.env):
                values.add(text)
    endpoint = str(server.endpoint or "").strip()
    if endpoint:
        parts = urlsplit(endpoint)
        if parts.username:
            values.add(parts.username)
        if parts.password:
            values.add(parts.password)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if value and _is_sensitive_key(key):
                values.add(value)
    return sorted(values, key=len, reverse=True)


def _sanitize_error_message(server: MCPServerDefinition, exc: Exception) -> str:
    message = str(exc)
    endpoint = str(server.endpoint or "").strip()
    if endpoint:
        message = message.replace(endpoint, _sanitize_endpoint(endpoint))
    for secret in _collect_secret_values(server):
        message = message.replace(secret, MASK)
    return message


class MCPRegistry:
    def __init__(self, db_pool, session_ttl_seconds: int = 300) -> None:
        self.db_pool = db_pool
        self.client = MCPClient()
        self.session_ttl = timedelta(seconds=max(60, session_ttl_seconds))
        self._sessions: dict[str, Any] = {}
        self._session_lock = asyncio.Lock()

    async def list_catalog_tools(
        self,
        *,
        tenant_id: str,
        agent_definition_id: str | None = None,
    ) -> list[MCPToolCatalogEntry]:
        rows = await self.db_pool.fetch(
            """
            SELECT
                t.*,
                s.name AS server_name,
                s.transport AS server_transport
            FROM mcp_server_tools t
            INNER JOIN mcp_servers s ON s.id = t.server_id
            LEFT JOIN agent_mcp_bindings b
                ON b.server_id = s.id
               AND ($2::uuid IS NOT NULL AND b.agent_definition_id = $2)
            WHERE s.tenant_id = $1
              AND s.status = 'active'
              AND ($2::uuid IS NULL OR b.id IS NOT NULL)
            ORDER BY s.name ASC, t.tool_name ASC
            """,
            _serialize_uuid(tenant_id),
            _serialize_uuid(agent_definition_id),
        )
        return [self._tool_from_row(row) for row in rows]

    async def get_catalog_tool(
        self,
        *,
        tenant_id: str,
        runtime_name: str,
        agent_definition_id: str | None = None,
    ) -> MCPToolCatalogEntry | None:
        rows = await self.list_catalog_tools(
            tenant_id=tenant_id,
            agent_definition_id=agent_definition_id,
        )
        for item in rows:
            if item.runtime_name == runtime_name:
                return item
        return None

    async def test_server(self, *, tenant_id: str, server_id: str) -> MCPConnectionTestResult:
        server = await self.get_server(tenant_id=tenant_id, server_id=server_id)
        if server is None:
            raise ValueError(f"MCP server {server_id} not found")

        try:
            session = await self._get_session(server)
            result = await self.client.test_connection(session)
            await self._update_server_health(server.id, last_error=None)
            return result
        except Exception as exc:
            sanitized_error = _sanitize_error_message(server, exc)
            await self._close_session(server.id)
            await self._update_server_health(server.id, last_error=sanitized_error)
            raise RuntimeError(sanitized_error) from exc

    async def refresh_server_tools(self, *, tenant_id: str, server_id: str) -> list[MCPToolCatalogEntry]:
        server = await self.get_server(tenant_id=tenant_id, server_id=server_id)
        if server is None:
            raise ValueError(f"MCP server {server_id} not found")

        try:
            session = await self._get_session(server)
            tools = await self.client.list_tools(session)
            await self._replace_server_tools(server=server, tools=tools)
            await self._update_server_health(server.id, last_error=None)
            return tools
        except Exception as exc:
            sanitized_error = _sanitize_error_message(server, exc)
            await self._close_session(server.id)
            await self._update_server_health(server.id, last_error=sanitized_error)
            raise RuntimeError(sanitized_error) from exc

    async def call_tool(
        self,
        *,
        tenant_id: str,
        agent_definition_id: str | None,
        runtime_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPCallToolResponse:
        catalog_entry = await self.get_catalog_tool(
            tenant_id=tenant_id,
            runtime_name=runtime_name,
            agent_definition_id=agent_definition_id,
        )
        if catalog_entry is None:
            raise ValueError(f"MCP tool {runtime_name} is not available")

        server = await self.get_server(tenant_id=tenant_id, server_id=catalog_entry.server_id)
        if server is None:
            raise ValueError(f"MCP server {catalog_entry.server_id} not found")

        try:
            session = await self._get_session(server)
            return await self.client.call_tool(
                session=session,
                runtime_name=catalog_entry.runtime_name,
                tool_name=catalog_entry.tool_name,
                arguments=arguments,
            )
        except Exception as exc:
            await self._close_session(server.id)
            raise RuntimeError(_sanitize_error_message(server, exc)) from exc

    async def get_server(self, *, tenant_id: str, server_id: str) -> MCPServerDefinition | None:
        row = await self.db_pool.fetchrow(
            """
            SELECT *
            FROM mcp_servers
            WHERE tenant_id = $1
              AND id = $2
            """,
            _serialize_uuid(tenant_id),
            _serialize_uuid(server_id),
        )
        if row is None:
            return None
        return self._server_from_row(row)

    async def close(self) -> None:
        async with self._session_lock:
            server_ids = list(self._sessions.keys())
        for server_id in server_ids:
            await self._close_session(server_id)

    async def _get_session(self, server: MCPServerDefinition):
        self.client.validate_server(server)
        await self._cleanup_stale_sessions()
        async with self._session_lock:
            session = self._sessions.get(server.id)
            if session is None:
                from ai_runtime.core.agent_runtime.mcp.session import ManagedMCPSession

                session = ManagedMCPSession(server)
                self._sessions[server.id] = session
            else:
                session.server = server
        await session.ensure_ready()
        return session

    async def _close_session(self, server_id: str) -> None:
        async with self._session_lock:
            session = self._sessions.pop(server_id, None)
        if session is not None:
            await session.close()

    async def _cleanup_stale_sessions(self) -> None:
        async with self._session_lock:
            snapshot = list(self._sessions.items())
        if not snapshot:
            return

        now = datetime.now(timezone.utc)
        stale_server_ids = [
            server_id
            for server_id, session in snapshot
            if now - session.last_used_at > self.session_ttl
        ]
        for server_id in stale_server_ids:
            await self._close_session(server_id)

    async def _replace_server_tools(
        self,
        *,
        server: MCPServerDefinition,
        tools: list[MCPToolCatalogEntry],
    ) -> None:
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM mcp_server_tools WHERE server_id = $1",
                    _serialize_uuid(server.id),
                )
                for tool in tools:
                    await conn.execute(
                        """
                        INSERT INTO mcp_server_tools (
                            server_id,
                            tool_name,
                            description,
                            input_schema,
                            metadata
                        )
                        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)
                        """,
                        _serialize_uuid(server.id),
                        tool.tool_name,
                        tool.description or None,
                        encode_json(tool.input_schema, {}),
                        encode_json(tool.metadata, {}),
                    )

    async def _update_server_health(self, server_id: str, *, last_error: str | None) -> None:
        await self.db_pool.execute(
            """
            UPDATE mcp_servers
            SET
                last_tested_at = now(),
                last_error = $2
            WHERE id = $1
            """,
            _serialize_uuid(server_id),
            last_error,
        )

    def _server_from_row(self, row) -> MCPServerDefinition:
        return MCPServerDefinition(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            name=row["name"],
            transport=row["transport"],
            endpoint=row["endpoint"],
            command=row["command"],
            args=parse_json_field(row["args"], []),
            env={str(key): str(value) for key, value in parse_json_field(row["env"], {}).items()},
            status=row["status"],
            last_tested_at=row["last_tested_at"],
            last_error=row["last_error"],
            metadata=parse_json_field(row["metadata"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _tool_from_row(self, row) -> MCPToolCatalogEntry:
        metadata = parse_json_field(row["metadata"], {})
        output_schema = metadata.get("output_schema") if isinstance(metadata.get("output_schema"), dict) else {}
        runtime_name = str(metadata.get("runtime_name") or self.client.build_runtime_tool_name(str(row["server_id"]), row["tool_name"]))
        return MCPToolCatalogEntry(
            id=str(row["id"]),
            server_id=str(row["server_id"]),
            server_name=row["server_name"] or "",
            transport=row["server_transport"] or "",
            runtime_name=runtime_name,
            tool_name=row["tool_name"],
            title=metadata.get("title"),
            description=row["description"] or "",
            input_schema=parse_json_field(row["input_schema"], {}),
            output_schema=output_schema,
            metadata=metadata if isinstance(metadata, dict) else {},
            discovered_at=row["discovered_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
