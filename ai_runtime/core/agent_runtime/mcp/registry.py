from __future__ import annotations

import asyncio
import hashlib
import json
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


def _json_copy(value: Any, default: Any) -> Any:
    if value is None:
        value = default
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return default


def _masked_server_payload(server: MCPServerDefinition) -> dict[str, Any]:
    payload = server.model_dump(mode="json")
    payload["endpoint"] = _sanitize_endpoint(payload.get("endpoint"))
    for key in ("env", "headers", "metadata"):
        payload[key] = _json_copy(payload.get(key), {})
    if isinstance(payload.get("env"), dict):
        payload["env"] = {key: MASK for key in payload["env"].keys()}
    if isinstance(payload.get("metadata"), dict):
        payload["metadata"] = _mask_sensitive_object(payload["metadata"], force_mask_strings=False)
    return payload


def _mask_sensitive_object(value: Any, force_mask_strings: bool = False, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = _mask_sensitive_object(
                item,
                force_mask_strings or _is_sensitive_container_key(key_text),
                path + (key_text,),
            )
        return result
    if isinstance(value, list):
        return [_mask_sensitive_object(item, force_mask_strings, path) for item in value]
    if isinstance(value, str):
        if not value:
            return value
        if force_mask_strings or any(_is_sensitive_key(part) or _is_sensitive_container_key(part) for part in path):
            return MASK
        return _mask_sensitive_string(value)
    return value


def _mask_sensitive_string(text: str) -> str:
    sanitized = sanitize_url_string(text)
    sanitized = sanitized.replace("Bearer ", f"Bearer {MASK}")
    sanitized = sanitized.replace("Basic ", f"Basic {MASK}")
    for token in ("secret", "password", "passwd", "token", "api_key", "apikey", "access_key", "authorization", "cookie", "client_secret", "private_key", "bearer"):
        sanitized = sanitized.replace(token, MASK)
    return sanitized


def sanitize_url_string(raw: str) -> str:
    parsed = urlsplit(raw)
    if not parsed.scheme:
        return raw
    if parsed.username or parsed.password:
        parsed = parsed._replace(netloc=parsed.hostname or "")
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query_items.append((key, MASK if _is_sensitive_key(key) else value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_items), parsed.fragment))


def _is_sensitive_container_key(key: str) -> bool:
    return str(key or "").strip().lower() in SENSITIVE_CONTAINERS


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    if "fingerprint" in lowered or "hash" in lowered or "checksum" in lowered:
        return False
    return any(token in lowered for token in (
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
    ))


def _mcp_status_rank(status: str) -> int:
    order = {
        "healthy": 0,
        "ready": 0,
        "available": 0,
        "warning": 1,
        "watch": 1,
        "degraded": 2,
        "critical": 3,
        "blocked": 3,
        "disabled": 4,
        "unavailable": 4,
        "untested": 2,
        "missing": 3,
        "empty": 3,
        "stale": 2,
    }
    return order.get(str(status or "").strip().lower(), 2)


def _first_non_empty(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tool_runtime_name(server_id: str, tool_name: str) -> str:
    prefix = str(server_id or "").replace("-", "")[:12]
    return f"mcp__{prefix}__{str(tool_name or '').strip()}"


def _contains_unmasked_sensitive_value(value: Any, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text) or _is_sensitive_container_key(key_text):
                if _value_is_unmasked_secret(item):
                    return True
            if _contains_unmasked_sensitive_value(item, path + (key_text,)):
                return True
    elif isinstance(value, list):
        return any(_contains_unmasked_sensitive_value(item, path) for item in value)
    return False


def _value_is_unmasked_secret(value: Any) -> bool:
    if isinstance(value, str):
        trimmed = value.strip()
        return bool(trimmed) and trimmed != MASK
    if isinstance(value, dict):
        return any(_value_is_unmasked_secret(item) for item in value.values())
    if isinstance(value, list):
        return any(_value_is_unmasked_secret(item) for item in value)
    return False


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

    async def list_servers(self, *, tenant_id: str) -> list[MCPServerDefinition]:
        rows = await self.db_pool.fetch(
            """
            SELECT *
            FROM mcp_servers
            WHERE tenant_id = $1
            ORDER BY name ASC
            """,
            _serialize_uuid(tenant_id),
        )
        return [self._server_from_row(row) for row in rows]

    async def get_governance_snapshot(self, *, tenant_id: str) -> dict[str, Any]:
        servers = await self.list_servers(tenant_id=tenant_id)
        hydrated = []
        for server in servers:
            try:
                hydrated.append(await self._hydrate_server(server))
            except Exception as exc:
                hydrated.append(
                    {
                        "server": _masked_server_payload(server),
                        "error": _sanitize_error_message(server, exc),
                    }
                )

        return self._build_governance_snapshot(tenant_id=tenant_id, servers=hydrated)

    async def get_audit_report(self, *, tenant_id: str, limit: int = 12) -> dict[str, Any]:
        servers = await self.list_servers(tenant_id=tenant_id)
        hydrated = []
        for server in servers:
            try:
                hydrated.append(await self._hydrate_server(server))
            except Exception:
                continue
        recent_events = await self._fetch_recent_events(tenant_id=tenant_id, limit=limit)
        return self._build_audit_report(tenant_id=tenant_id, servers=hydrated, recent_events=recent_events, limit=limit)

    async def test_server_summary(self, *, tenant_id: str, server_id: str) -> dict[str, Any]:
        result = await self.test_server(tenant_id=tenant_id, server_id=server_id)
        server = await self.get_server(tenant_id=tenant_id, server_id=server_id)
        hydrated = await self._hydrate_server(server) if server is not None else None
        return {
            "result": result.model_dump(mode="json"),
            "server": hydrated["server"] if isinstance(hydrated, dict) else _masked_server_payload(server) if server is not None else None,
            "connection": hydrated.get("connection") if isinstance(hydrated, dict) else None,
            "catalog": hydrated.get("catalog") if isinstance(hydrated, dict) else None,
            "availability": hydrated.get("availability") if isinstance(hydrated, dict) else None,
            "recovery": hydrated.get("recovery") if isinstance(hydrated, dict) else None,
            "security_score": hydrated.get("security_score") if isinstance(hydrated, dict) else None,
        }

    async def refresh_server_tools_summary(self, *, tenant_id: str, server_id: str) -> dict[str, Any]:
        tools = await self.refresh_server_tools(tenant_id=tenant_id, server_id=server_id)
        server = await self.get_server(tenant_id=tenant_id, server_id=server_id)
        hydrated = await self._hydrate_server(server) if server is not None else None
        return {
            "tools": [tool.model_dump(mode="json") for tool in tools],
            "total": len(tools),
            "server": hydrated["server"] if isinstance(hydrated, dict) else _masked_server_payload(server) if server is not None else None,
            "connection": hydrated.get("connection") if isinstance(hydrated, dict) else None,
            "catalog": hydrated.get("catalog") if isinstance(hydrated, dict) else None,
            "availability": hydrated.get("availability") if isinstance(hydrated, dict) else None,
            "recovery": hydrated.get("recovery") if isinstance(hydrated, dict) else None,
            "security_score": hydrated.get("security_score") if isinstance(hydrated, dict) else None,
        }

    async def get_recovery_plan(self, *, tenant_id: str, server_id: str) -> dict[str, Any]:
        server = await self.get_server(tenant_id=tenant_id, server_id=server_id)
        if server is None:
            raise ValueError(f"MCP server {server_id} not found")
        hydrated = await self._hydrate_server(server)
        recovery = hydrated["recovery"]
        actions = recovery.get("actions") if isinstance(recovery, dict) else []
        return {
            "server_id": server.id,
            "server_name": server.name,
            "status": recovery.get("status"),
            "severity": recovery.get("severity"),
            "summary": recovery.get("summary"),
            "failure_mode": recovery.get("failure_mode"),
            "recoverable": recovery.get("recoverable"),
            "impact": recovery.get("impact"),
            "actions": actions,
            "security_score": hydrated.get("security_score"),
            "connection": hydrated.get("connection"),
            "catalog": hydrated.get("catalog"),
            "availability": hydrated.get("availability"),
            "binding_usage": hydrated.get("binding_usage"),
            "server": hydrated["server"],
        }

    def normalize_tool_result(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            payload = _mask_sensitive_object(value, force_mask_strings=False)
        else:
            payload = {"text": _mask_sensitive_string(str(value or ""))}
        text = payload.get("text") if isinstance(payload, dict) else None
        if isinstance(text, str) and text.strip():
            result_text = text.strip()
        else:
            result_text = json.dumps(payload, ensure_ascii=False, indent=2) if payload else ""
        checksum_source = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        checksum = hashlib.sha256(checksum_source.encode("utf-8")).hexdigest()
        return {
            "status": "normalized",
            "checksum": checksum,
            "payload": payload,
            "summary": _first_non_empty(
                payload.get("summary") if isinstance(payload, dict) else "",
                payload.get("message") if isinstance(payload, dict) else "",
                payload.get("text") if isinstance(payload, dict) else "",
                default="MCP tool result normalized.",
            ),
            "text": result_text,
        }

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

    async def _hydrate_server(self, server: MCPServerDefinition | None) -> dict[str, Any] | None:
        if server is None:
            return None
        tools = await self.list_server_tools(server.id)
        connection = self._build_connection_summary(server)
        catalog = self._build_catalog_summary(server, tools)
        availability = self._build_availability_summary(server, connection, catalog)
        binding_usage = await self._build_binding_usage_summary(server)
        recovery = self._build_recovery_summary(server, connection, catalog, availability, binding_usage)
        events = await self._fetch_server_events(server.id, server.tenant_id, limit=12)
        security_score = self._build_security_score(server, tools, connection, catalog, availability, binding_usage, recovery, events)
        return {
            "server": _masked_server_payload(server),
            "tools": [tool.model_dump(mode="json") for tool in tools],
            "connection": connection,
            "catalog": catalog,
            "availability": availability,
            "binding_usage": binding_usage,
            "recovery": recovery,
            "security_score": security_score,
            "events": events,
        }

    async def list_server_tools(self, server_id: str) -> list[MCPToolCatalogEntry]:
        rows = await self.db_pool.fetch(
            """
            SELECT
                t.*,
                s.name AS server_name,
                s.transport AS server_transport
            FROM mcp_server_tools t
            INNER JOIN mcp_servers s ON s.id = t.server_id
            WHERE s.id = $1
            ORDER BY t.tool_name ASC
            """,
            _serialize_uuid(server_id),
        )
        return [self._tool_from_row(row) for row in rows]

    async def _fetch_server_events(self, server_id: str, tenant_id: str, limit: int = 12) -> list[dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT id, tenant_id, server_id, server_name, event_type, action_type, status, failure_mode, summary, details, actor_user_id, created_at
            FROM mcp_server_events
            WHERE server_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            _serialize_uuid(server_id),
            _serialize_uuid(tenant_id),
            max(1, min(int(limit or 12), 100)),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "id": str(row["id"]),
                    "tenant_id": str(row["tenant_id"]),
                    "server_id": str(row["server_id"]),
                    "server_name": str(row["server_name"] or ""),
                    "event_type": str(row["event_type"] or ""),
                    "action_type": str(row["action_type"] or ""),
                    "status": str(row["status"] or ""),
                    "failure_mode": str(row["failure_mode"] or ""),
                    "summary": str(row["summary"] or ""),
                    "details": parse_json_field(row["details"], {}),
                    "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
                    "created_at": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else None,
                }
            )
        return events

    async def _fetch_recent_events(self, *, tenant_id: str, limit: int = 12) -> list[dict[str, Any]]:
        rows = await self.db_pool.fetch(
            """
            SELECT id, tenant_id, server_id, server_name, event_type, action_type, status, failure_mode, summary, details, actor_user_id, created_at
            FROM mcp_server_events
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            _serialize_uuid(tenant_id),
            max(1, min(int(limit or 12), 100)),
        )
        return [
            {
                "id": str(row["id"]),
                "tenant_id": str(row["tenant_id"]),
                "server_id": str(row["server_id"]),
                "server_name": str(row["server_name"] or ""),
                "event_type": str(row["event_type"] or ""),
                "action_type": str(row["action_type"] or ""),
                "status": str(row["status"] or ""),
                "failure_mode": str(row["failure_mode"] or ""),
                "summary": str(row["summary"] or ""),
                "details": parse_json_field(row["details"], {}),
                "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
                "created_at": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else None,
            }
            for row in rows
        ]

    def _build_connection_summary(self, server: MCPServerDefinition) -> dict[str, Any]:
        status = "untested"
        summary = "尚未执行连接测试。"
        error = _first_non_empty(server.last_error, default="")
        if server.status != "active":
            status = "disabled"
            summary = "Server 已禁用，不会参与运行时调用。"
        elif server.last_tested_at is None:
            status = "untested"
            summary = "尚未执行连接测试，当前健康状态未知。"
        elif error:
            status = "degraded"
            summary = "最近一次连接测试失败，请先修复连接问题。"
        else:
            status = "healthy"
            summary = "最近一次连接测试通过。"
        return {
            "status": status,
            "summary": summary,
            "tested_at": server.last_tested_at.isoformat() if isinstance(server.last_tested_at, datetime) else None,
            "error": error,
        }

    def _build_catalog_summary(self, server: MCPServerDefinition, tools: list[MCPToolCatalogEntry]) -> dict[str, Any]:
        refreshed_at = None
        sample_tools: list[str] = []
        for tool in tools:
            if len(sample_tools) < 5 and str(tool.tool_name or "").strip():
                sample_tools.append(str(tool.tool_name).strip())
            discovered_at = tool.discovered_at
            if isinstance(discovered_at, datetime):
                refreshed_at = max(refreshed_at, discovered_at) if isinstance(refreshed_at, datetime) else discovered_at
        age_seconds = None
        is_stale = False
        if isinstance(refreshed_at, datetime):
            age_seconds = max(0, int((datetime.now(timezone.utc) - refreshed_at).total_seconds()))
            is_stale = age_seconds > int(timedelta(hours=24).total_seconds())
        if server.status != "active":
            status = "disabled"
            summary = "Server 已禁用，catalog 不会参与 agent 工具发现。"
        elif len(tools) == 0 and refreshed_at is None and server.last_tested_at is None:
            status = "missing"
            summary = "还没有缓存工具，请先执行 Refresh Tools。"
        elif len(tools) == 0:
            status = "empty"
            summary = "最近一次 catalog 刷新后没有发现可用工具。"
        elif is_stale:
            status = "stale"
            summary = "已存在缓存工具，但 catalog 已过期，建议重新刷新。"
        else:
            status = "ready"
            summary = f"当前已缓存 {len(tools)} 个工具，可供 agent 直接发现。"
        return {
            "status": status,
            "summary": summary,
            "tool_count": len(tools),
            "refreshed_at": refreshed_at.isoformat() if isinstance(refreshed_at, datetime) else None,
            "age_seconds": age_seconds,
            "stale_after_seconds": int(timedelta(hours=24).total_seconds()),
            "is_stale": is_stale,
            "sample_tools": sample_tools,
        }

    def _build_availability_summary(
        self,
        server: MCPServerDefinition,
        connection: dict[str, Any] | None,
        catalog: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if server.status != "active":
            return {
                "status": "disabled",
                "summary": "Server 已禁用，不能绑定到 agent。",
                "bindable": False,
                "reason": "disabled",
            }
        if catalog is None or int(catalog.get("tool_count") or 0) == 0:
            return {
                "status": "unavailable",
                "summary": "还没有可供 agent 使用的缓存工具，请先刷新 catalog。",
                "bindable": False,
                "reason": "catalog_empty",
            }
        if connection and connection.get("status") == "degraded":
            return {
                "status": "degraded",
                "summary": "最近一次连接测试失败，建议修复后再交给 agent 使用。",
                "bindable": False,
                "reason": "connection_failed",
            }
        if catalog and catalog.get("is_stale"):
            return {
                "status": "warning",
                "summary": "Server 可绑定，但 catalog 已过期，建议刷新后再投入生产。",
                "bindable": True,
                "reason": "catalog_stale",
            }
        if connection and connection.get("status") == "untested":
            return {
                "status": "warning",
                "summary": "Server 已有缓存工具，但还未完成连接验证。",
                "bindable": True,
                "reason": "connection_untested",
            }
        return {
            "status": "available",
            "summary": "Server 已通过基础校验，可供 agent 使用。",
            "bindable": True,
            "reason": "ready",
        }

    async def _build_binding_usage_summary(self, server: MCPServerDefinition) -> dict[str, Any] | None:
        rows = await self.db_pool.fetch(
            """
            SELECT
                bindings.agent_definition_id,
                COALESCE(a.name, bindings.agent_definition_id::text) AS name,
                COALESCE(a.status, 'active') AS status
            FROM agent_mcp_bindings bindings
            LEFT JOIN agent_definitions a ON a.id = bindings.agent_definition_id
            WHERE bindings.server_id = $1
            ORDER BY COALESCE(a.name, bindings.agent_definition_id::text) ASC
            """,
            _serialize_uuid(server.id),
        )
        agents = []
        active = 0
        inactive = 0
        for row in rows:
            status = _first_non_empty(row["status"], default="active")
            if status == "active":
                active += 1
            else:
                inactive += 1
            agents.append(
                {
                    "agent_id": str(row["agent_definition_id"]),
                    "name": str(row["name"] or ""),
                    "status": status,
                }
            )
        total = len(agents)
        summary = "当前还没有 agent 绑定这个 server。" if total == 0 else f"当前有 {total} 个 agent 正在使用这个 server。"
        return {
            "agent_count": total,
            "active_agent_count": active,
            "inactive_agent_count": inactive,
            "summary": summary,
            "more_count": max(0, total - len(agents)),
            "agents": agents[:6],
        }

    def _build_recovery_summary(
        self,
        server: MCPServerDefinition,
        connection: dict[str, Any] | None,
        catalog: dict[str, Any] | None,
        availability: dict[str, Any] | None,
        binding_usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        status = "healthy"
        severity = "info"
        summary = "当前不需要额外恢复操作。"
        failure_mode = ""
        recoverable = False

        def add_action(action_type: str, label: str, description: str, priority: str) -> None:
            actions.append(
                {
                    "type": action_type,
                    "label": label,
                    "description": description,
                    "priority": priority,
                }
            )

        connection_status = str(connection.get("status") if isinstance(connection, dict) else "").strip()
        availability_reason = str(availability.get("reason") if isinstance(availability, dict) else "").strip()
        catalog_tool_count = int(catalog.get("tool_count") or 0) if isinstance(catalog, dict) else 0
        catalog_is_stale = bool(catalog.get("is_stale")) if isinstance(catalog, dict) else False

        if server.status != "active":
            status = "disabled"
            severity = "neutral"
            summary = "Server 已禁用，恢复前需先确认是否重新启用并重新验证。"
            failure_mode = "server_disabled"
            recoverable = True
            add_action("enable", "重新启用 Server", "确认配置仍然有效后重新启用。", "high")
            add_action("test", "测试连接", "启用后先验证连接，再决定是否刷新 catalog。", "medium")
            if catalog_tool_count == 0 or catalog_is_stale:
                add_action("refresh", "刷新 Catalog", "重新发现工具并更新缓存 snapshot。", "medium")
        elif availability_reason == "connection_failed":
            status = "blocked"
            severity = "critical"
            summary = "最近一次连接测试失败，需先恢复 server 连通性，再重新验证 catalog。"
            failure_mode = "connection_failed"
            recoverable = True
            add_action("test", "重新测试连接", "修复 endpoint、命令、凭据或网络后重新测试。", "high")
            if catalog_tool_count > 0:
                add_action("refresh", "连接恢复后刷新 Catalog", "连接恢复后重新发现工具，避免继续依赖旧 snapshot。", "medium")
        elif availability_reason == "catalog_empty":
            status = "needs_catalog"
            severity = "high"
            summary = "当前没有可供 agent 使用的缓存工具，需先建立或重建 catalog。"
            failure_mode = "catalog_empty"
            recoverable = True
            if connection_status == "untested":
                add_action("test", "先测试连接", "确认 server 可达后再刷新 catalog，减少无效刷新。", "high")
            add_action("refresh", "刷新 Catalog", "执行工具发现并写回最新缓存。", "high")
        elif availability_reason == "catalog_stale":
            status = "stale"
            severity = "medium"
            summary = "当前仍能绑定，但缓存 catalog 已过期，建议尽快刷新，避免 agent 继续依赖旧工具快照。"
            failure_mode = "catalog_stale"
            recoverable = True
            add_action("refresh", "刷新 Catalog", "更新工具快照并消除 stale 状态。", "high")
            if connection_status not in {"healthy", "disabled"}:
                add_action("test", "补做连接测试", "刷新前补齐连通性验证，确认 stale 不是由失联导致。", "medium")
        elif availability_reason == "connection_untested":
            status = "verify"
            severity = "medium"
            summary = "已有缓存工具，但连接状态尚未验证，建议先补齐测试，避免把未知健康状态投入生产。"
            failure_mode = "connection_untested"
            recoverable = True
            add_action("test", "测试连接", "建立健康基线并确认当前缓存工具仍可访问。", "high")
            if catalog_is_stale:
                add_action("refresh", "必要时刷新 Catalog", "若工具已过期，再补做 refresh。", "medium")

        impact = self._build_recovery_impact(binding_usage)
        return {
            "status": status,
            "severity": severity,
            "summary": summary,
            "failure_mode": failure_mode or "none",
            "recoverable": recoverable,
            "actions": actions,
            "impact": impact,
        }

    def _build_recovery_impact(self, binding_usage: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(binding_usage, dict):
            return {"agent_count": 0, "active_agent_count": 0, "inactive_agent_count": 0, "summary": "当前没有 agent 受到影响。"}
        agent_count = _safe_int(binding_usage.get("agent_count"))
        active_agent_count = _safe_int(binding_usage.get("active_agent_count"))
        inactive_agent_count = _safe_int(binding_usage.get("inactive_agent_count"))
        if agent_count <= 0:
            summary = "当前没有 agent 受到影响。"
        elif active_agent_count > 0 and inactive_agent_count > 0:
            summary = f"当前影响 {agent_count} 个已绑定 agent，其中 {active_agent_count} 个处于 active 状态。"
        elif active_agent_count > 0:
            summary = f"当前影响 {agent_count} 个已绑定 agent，且都处于 active 状态。"
        else:
            summary = f"当前影响 {agent_count} 个已绑定 agent，但采样中没有 active agent。"
        return {
            "agent_count": agent_count,
            "active_agent_count": active_agent_count,
            "inactive_agent_count": inactive_agent_count,
            "summary": summary,
        }

    def _build_security_score(
        self,
        server: MCPServerDefinition,
        tools: list[MCPToolCatalogEntry],
        connection: dict[str, Any],
        catalog: dict[str, Any],
        availability: dict[str, Any],
        binding_usage: dict[str, Any] | None,
        recovery: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        breakdown = [
            self._build_connection_security_breakdown(server, connection),
            self._build_catalog_security_breakdown(server, catalog),
            self._build_binding_security_breakdown(binding_usage, recovery),
            self._build_configuration_security_breakdown(server, tools),
            self._build_audit_security_breakdown(events),
        ]
        score = sum(int(item.get("score") or 0) for item in breakdown)
        max_score = sum(int(item.get("max_score") or 0) for item in breakdown)
        status = "healthy"
        risk_level = "low"
        summary = "MCP server 安全基线良好。"
        if score < 40:
            status = "critical"
            risk_level = "critical"
            summary = "MCP server 存在关键治理风险，建议先阻断绑定并完成连接与 catalog 修复。"
        elif score < 65:
            status = "warning"
            risk_level = "high"
            summary = "MCP server 存在高风险项，投入生产前需要完成恢复动作。"
        elif score < 85:
            status = "watch"
            risk_level = "medium"
            summary = "MCP server 可用但需要持续治理，建议补齐验证或刷新。"
        if server.status != "active":
            status = "disabled"
            risk_level = "medium"
            summary = "MCP server 已禁用，重新启用前需要重新完成安全基线验证。"
        evaluated_at = datetime.now(timezone.utc).isoformat()
        return {
            "score": max(0, min(score, max_score)),
            "max_score": max_score,
            "status": status,
            "risk_level": risk_level,
            "summary": summary,
            "evaluated_at": evaluated_at,
            "breakdown": breakdown,
        }

    def _build_connection_security_breakdown(self, server: MCPServerDefinition, connection: dict[str, Any]) -> dict[str, Any]:
        item = {
            "key": "connection",
            "label": "连接验证",
            "max_score": 25,
            "score": 8,
            "status": "healthy",
            "summary": "最近连接验证通过。",
        }
        if server.status != "active":
            item.update({"score": 10, "status": "disabled", "summary": "Server 已禁用，连接基线需要重新确认。"})
        elif connection.get("status") == "healthy":
            item["score"] = 25
        elif connection.get("status") == "untested":
            item.update({"score": 12, "status": "warning", "summary": "尚未完成连接测试。"})
        elif connection.get("status") == "degraded":
            item.update({"score": 0, "status": "critical", "summary": "最近连接测试失败。"})
        else:
            item.update({"score": 8, "status": "warning", "summary": "连接状态未知。"})
        return item

    def _build_catalog_security_breakdown(self, server: MCPServerDefinition, catalog: dict[str, Any]) -> dict[str, Any]:
        item = {
            "key": "catalog",
            "label": "工具 Catalog",
            "max_score": 25,
            "score": 0,
            "status": "healthy",
            "summary": "工具 catalog 已刷新且可用。",
        }
        if server.status != "active":
            item.update({"score": 10, "status": "disabled", "summary": "Server 已禁用，catalog 不参与运行时发现。"})
        elif catalog.get("tool_count", 0) > 0 and not catalog.get("is_stale"):
            item["score"] = 25
        elif catalog.get("tool_count", 0) > 0 and catalog.get("is_stale"):
            item.update({"score": 14, "status": "warning", "summary": "已有工具缓存，但 catalog 已过期。"})
        elif catalog.get("status") == "empty":
            item.update({"score": 5, "status": "critical", "summary": "最近 catalog 刷新未发现可用工具。"})
        else:
            item.update({"score": 0, "status": "critical", "summary": "尚未建立可用工具 catalog。"})
        return item

    def _build_binding_security_breakdown(self, binding_usage: dict[str, Any] | None, recovery: dict[str, Any] | None) -> dict[str, Any]:
        item = {
            "key": "binding_impact",
            "label": "绑定影响面",
            "max_score": 20,
            "score": 20,
            "status": "healthy",
            "summary": "当前没有高影响绑定风险。",
        }
        if not isinstance(binding_usage, dict) or _safe_int(binding_usage.get("agent_count")) <= 0:
            item["summary"] = "当前未绑定 agent，影响面较低。"
            return item
        active_count = _safe_int(binding_usage.get("active_agent_count"))
        if isinstance(recovery, dict) and recovery.get("recoverable") and recovery.get("status") != "healthy":
            if active_count >= 3:
                item.update({"score": 4, "status": "critical", "summary": f"风险状态仍影响 {active_count} 个 active agent。"})
            elif active_count > 0:
                item.update({"score": 10, "status": "warning", "summary": f"风险状态仍影响 {active_count} 个 active agent。"})
            else:
                item.update({"score": 14, "status": "warning", "summary": "风险状态影响已绑定 agent，但采样中没有 active agent。"})
            return item
        if active_count >= 5:
            item.update({"score": 16, "status": "watch", "summary": f"已绑定 {active_count} 个 active agent，需保持审计关注。"})
            return item
        item["summary"] = _first_non_empty(binding_usage.get("summary"), default=item["summary"])
        return item

    def _build_configuration_security_breakdown(self, server: MCPServerDefinition, tools: list[MCPToolCatalogEntry]) -> dict[str, Any]:
        item = {
            "key": "configuration",
            "label": "配置暴露面",
            "max_score": 15,
            "score": 15,
            "status": "healthy",
            "summary": "配置未发现明显高风险暴露面。",
        }
        penalty = 0
        reasons: list[str] = []
        if str(server.transport or "").strip() == "stdio":
            penalty += 3
            reasons.append("stdio transport 需要运行本地命令")
        if _contains_unmasked_sensitive_value(server.env) or _contains_unmasked_sensitive_value(server.metadata):
            penalty += 6
            reasons.append("配置中仍包含未脱敏敏感字段")
        if str(server.endpoint or "").strip().startswith("http://"):
            penalty += 4
            reasons.append("endpoint 使用明文 HTTP")
        if len(tools) > 30:
            penalty += 2
            reasons.append(f"暴露工具数量较多（{len(tools)} 个）")
        item["score"] = max(0, item["score"] - penalty)
        if item["score"] < 8:
            item["status"] = "critical"
        elif item["score"] < item["max_score"]:
            item["status"] = "warning"
        if reasons:
            item["summary"] = "；".join(reasons) + "。"
        return item

    def _build_audit_security_breakdown(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        item = {
            "key": "audit_trail",
            "label": "调用审计",
            "max_score": 15,
            "score": 15,
            "status": "healthy",
            "summary": "最近治理审计未发现失败趋势。",
        }
        failed = 0
        total = 0
        for event in events or []:
            if not isinstance(event, dict):
                continue
            total += 1
            if str(event.get("status") or "").strip() == "failed":
                failed += 1
        if total == 0:
            item.update({"score": 8, "status": "warning", "summary": "尚未形成治理审计历史。"})
            return item
        if failed >= 3:
            item.update({"score": 2, "status": "critical", "summary": f"最近 {total} 条治理事件中有 {failed} 条失败。"})
            return item
        if failed > 0:
            item.update({"score": 10, "status": "warning", "summary": f"最近 {total} 条治理事件中有 {failed} 条失败。"})
        return item

    def _build_governance_snapshot(self, *, tenant_id: str, servers: list[dict[str, Any]]) -> dict[str, Any]:
        summary = {
            "total_servers": len(servers),
            "recovering_servers": 0,
            "blocked_servers": 0,
            "stale_servers": 0,
            "untested_servers": 0,
            "impacted_agents": 0,
            "active_impacted_agents": 0,
            "recent_event_count": 0,
            "long_stale_servers": [],
            "recoverable_servers": [],
            "recent_events": [],
            "failure_mode_counts": {},
            "action_type_counts": {},
            "event_status_counts": {},
            "event_filters": {"server_id": "", "action_type": "", "status": "", "failure_mode": "", "limit": 40},
        }
        for item in servers:
            recovery = item.get("recovery") or {}
            catalog = item.get("catalog") or {}
            connection = item.get("connection") or {}
            binding = item.get("binding_usage") or {}
            if isinstance(recovery, dict):
                failure_mode = _first_non_empty(recovery.get("failure_mode"), default="")
                if failure_mode and failure_mode != "none":
                    summary["failure_mode_counts"][failure_mode] = summary["failure_mode_counts"].get(failure_mode, 0) + 1
                if recovery.get("recoverable") and recovery.get("status") != "healthy":
                    summary["recovering_servers"] += 1
                    summary["recoverable_servers"].append(item.get("server"))
                if recovery.get("status") == "blocked":
                    summary["blocked_servers"] += 1
            if isinstance(catalog, dict) and catalog.get("is_stale"):
                summary["stale_servers"] += 1
                if _safe_int(catalog.get("age_seconds")) > int(timedelta(hours=72).total_seconds()):
                    summary["long_stale_servers"].append(item.get("server"))
            if isinstance(connection, dict) and connection.get("status") == "untested":
                summary["untested_servers"] += 1
            if isinstance(binding, dict):
                summary["impacted_agents"] += _safe_int(binding.get("agent_count"))
                summary["active_impacted_agents"] += _safe_int(binding.get("active_agent_count"))
            for event in item.get("events") or []:
                summary["recent_events"].append(event)
                summary["recent_event_count"] += 1
                action_type = _first_non_empty(event.get("action_type"), default="")
                status = _first_non_empty(event.get("status"), default="")
                failure_mode = _first_non_empty(event.get("failure_mode"), default="")
                if action_type:
                    summary["action_type_counts"][action_type] = summary["action_type_counts"].get(action_type, 0) + 1
                if status:
                    summary["event_status_counts"][status] = summary["event_status_counts"].get(status, 0) + 1
                if failure_mode and failure_mode != "none":
                    summary["failure_mode_counts"][failure_mode] = summary["failure_mode_counts"].get(failure_mode, 0) + 1
        return {
            "tenant_id": tenant_id,
            "summary": summary,
            "servers": servers,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_audit_report(
        self,
        *,
        tenant_id: str,
        servers: list[dict[str, Any]],
        recent_events: list[dict[str, Any]],
        limit: int,
    ) -> dict[str, Any]:
        score_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        top_risk: list[dict[str, Any]] = []
        scores: list[int] = []
        overview = {
            "total_servers": 0,
            "average_score": 0.0,
            "median_score": 0,
            "low_risk_count": 0,
            "medium_risk_count": 0,
            "high_risk_count": 0,
            "critical_risk_count": 0,
            "blocked_count": 0,
            "recovering_count": 0,
            "stale_count": 0,
            "untested_count": 0,
        }
        failure_mode_counts: dict[str, int] = {}
        action_type_counts: dict[str, int] = {}
        for server in servers:
            security_score = server.get("security_score") or {}
            recovery = server.get("recovery") or {}
            catalog = server.get("catalog") or {}
            connection = server.get("connection") or {}
            if not isinstance(security_score, dict):
                continue
            score = _safe_int(security_score.get("score"))
            scores.append(score)
            overview["total_servers"] += 1
            risk_level = _first_non_empty(security_score.get("risk_level"), default="low")
            if risk_level in score_distribution:
                score_distribution[risk_level] += 1
            if risk_level == "low":
                overview["low_risk_count"] += 1
            elif risk_level == "medium":
                overview["medium_risk_count"] += 1
            elif risk_level == "high":
                overview["high_risk_count"] += 1
            elif risk_level == "critical":
                overview["critical_risk_count"] += 1
            if isinstance(recovery, dict):
                if recovery.get("status") == "blocked":
                    overview["blocked_count"] += 1
                if recovery.get("recoverable") and recovery.get("status") != "healthy":
                    overview["recovering_count"] += 1
            if isinstance(catalog, dict) and catalog.get("is_stale"):
                overview["stale_count"] += 1
            if isinstance(connection, dict) and connection.get("status") == "untested":
                overview["untested_count"] += 1
            top_risk.append(
                {
                    "server_id": _first_non_empty(server.get("server", {}).get("id"), default=""),
                    "server_name": _first_non_empty(server.get("server", {}).get("name"), default=""),
                    "transport": _first_non_empty(server.get("server", {}).get("transport"), default=""),
                    "status": _first_non_empty(server.get("server", {}).get("status"), default=""),
                    "score": score,
                    "risk_level": risk_level,
                    "summary": _first_non_empty(security_score.get("summary"), default=""),
                    "failure_mode": _first_non_empty(recovery.get("failure_mode"), default=""),
                    "recoverable": bool(recovery.get("recoverable")),
                    "binding_count": _safe_int((server.get("binding_usage") or {}).get("agent_count")),
                    "active_count": _safe_int((server.get("binding_usage") or {}).get("active_agent_count")),
                    "event_count": len(server.get("events") or []),
                    "last_tested_at": (server.get("connection") or {}).get("tested_at"),
                    "evaluated_at": security_score.get("evaluated_at"),
                    "breakdown": security_score.get("breakdown") or [],
                }
            )
        if scores:
            scores_sorted = sorted(scores)
            overview["average_score"] = sum(scores) / len(scores)
            overview["median_score"] = scores_sorted[len(scores_sorted) // 2]
        for event in recent_events:
            action_type = _first_non_empty(event.get("action_type"), default="")
            failure_mode = _first_non_empty(event.get("failure_mode"), default="")
            if action_type:
                action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
            if failure_mode and failure_mode != "none":
                failure_mode_counts[failure_mode] = failure_mode_counts.get(failure_mode, 0) + 1
        top_risk.sort(key=lambda item: (item.get("score", 0), item.get("server_name", "")))
        top_risk = top_risk[: max(1, min(limit or 12, 100))]
        recommended_actions = ["继续按连接测试、catalog 刷新和审计轮转保持稳定。"]
        if overview["critical_risk_count"] > 0 or overview["blocked_count"] > 0:
            recommended_actions = ["先处理 critical/blocked server，再处理 stale 和 untested 项。"]
        elif overview["high_risk_count"] > 0:
            recommended_actions = ["优先修复高风险 server 的连接和 catalog，再恢复绑定。"]
        if overview["stale_count"] > 0:
            recommended_actions.append("对 stale catalog server 重新执行 refresh，压缩旧工具快照。")
        if overview["untested_count"] > 0:
            recommended_actions.append("补齐 untested server 的连接验证，建立新基线。")
        return {
            "tenant_id": tenant_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overview": overview,
            "top_risk_servers": top_risk,
            "score_distribution": score_distribution,
            "recent_events": recent_events[: max(1, min(limit or 12, 100))],
            "failure_mode_counts": failure_mode_counts,
            "action_type_counts": action_type_counts,
            "recommended_actions": recommended_actions,
        }
