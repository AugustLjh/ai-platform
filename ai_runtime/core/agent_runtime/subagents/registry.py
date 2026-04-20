from __future__ import annotations

from typing import Any
from uuid import UUID

from ai_runtime.core.agent_runtime.models import AgentDefinition
from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


def _normalize_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    chars = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            previous_dash = False
            continue
        if previous_dash:
            continue
        chars.append("-")
        previous_dash = True
    return "".join(chars).strip("-")


def _serialize_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return str(value)


def _string_metadata_value(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_allowlist(value: Any) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for item in _json_list(value):
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


class SubagentRegistry:
    def __init__(self, db_pool, agent_repository) -> None:
        self.db_pool = db_pool
        self.agent_repository = agent_repository

    async def _resolve_authorized_targets(self, definition: AgentDefinition) -> list[SubagentTarget]:
        if self.db_pool is None:
            return []

        rows = await self.db_pool.fetch(
            """
            SELECT
                a.id AS authorization_id,
                a.priority,
                a.metadata AS authorization_metadata,
                a.budget_policy,
                p.id AS publication_id,
                p.visibility,
                p.status AS publication_status,
                p.metadata AS publication_metadata,
                v.id AS version_id,
                v.version_number,
                v.lifecycle_status,
                v.system_prompt,
                v.model,
                v.config,
                v.metadata AS version_metadata,
                v.output_schema,
                v.handoff_input_schema,
                v.tool_allowlist,
                v.skill_allowlist,
                v.mcp_allowlist,
                v.knowledge_policy,
                v.review_policy,
                v.runtime_policy,
                d.id AS subagent_definition_id,
                d.name,
                d.description,
                d.metadata AS definition_metadata
            FROM agent_subagent_authorizations a
            INNER JOIN subagent_publications p
              ON p.id = a.publication_id
            INNER JOIN subagent_definition_versions v
              ON v.id = p.version_id
            INNER JOIN subagent_definitions d
              ON d.id = p.subagent_definition_id
            WHERE a.agent_definition_id = $1
              AND a.status = 'enabled'
              AND p.status = 'active'
              AND (
                    p.visibility = 'system_global'
                    OR p.tenant_id = $2
                  )
            ORDER BY a.priority ASC, a.created_at ASC, d.name ASC
            """,
            _serialize_uuid(definition.id),
            _serialize_uuid(definition.tenant_id),
        )

        targets: list[SubagentTarget] = []
        seen_publication_ids: set[str] = set()
        for row in rows:
            row_data = dict(row)
            publication_id = str(row_data.get("publication_id") or "").strip()
            version_id = str(row_data.get("version_id") or "").strip()
            authorization_id = str(row_data.get("authorization_id") or "").strip()
            subagent_definition_id = str(row_data.get("subagent_definition_id") or "").strip()
            if not publication_id or not version_id or not authorization_id or not subagent_definition_id:
                continue
            if publication_id in seen_publication_ids:
                continue

            definition_metadata = _json_object(row_data.get("definition_metadata"))
            version_metadata = _json_object(row_data.get("version_metadata"))
            publication_metadata = _json_object(row_data.get("publication_metadata"))
            authorization_metadata = _json_object(row_data.get("authorization_metadata"))
            merged_metadata = {
                **definition_metadata,
                **version_metadata,
                **publication_metadata,
                **authorization_metadata,
                "authorization_id": authorization_id,
                "publication_id": publication_id,
                "version_id": version_id,
                "version_number": int(row_data.get("version_number") or 0),
                "publication_status": str(row_data.get("publication_status") or "").strip() or None,
                "publication_visibility": str(row_data.get("visibility") or "").strip() or None,
                "lifecycle_status": str(row_data.get("lifecycle_status") or "").strip() or None,
                "priority": int(row_data.get("priority") or 100),
                "budget_policy": _json_object(row_data.get("budget_policy")),
            }

            slug = _normalize_slug(
                _string_metadata_value(merged_metadata, "slug")
                or str(row_data.get("name") or subagent_definition_id)
            )
            handoff_prompt = (
                _string_metadata_value(merged_metadata, "handoff_prompt")
                or str(row_data.get("system_prompt") or "").strip()
                or None
            )
            targets.append(
                SubagentTarget(
                    slug=slug or publication_id,
                    name=str(row_data.get("name") or publication_id).strip(),
                    description=str(row_data.get("description") or "").strip() or None,
                    subagent_definition_id=subagent_definition_id,
                    publication_id=publication_id,
                    version_id=version_id,
                    authorization_id=authorization_id,
                    handoff_prompt=handoff_prompt,
                    system_prompt=str(row_data.get("system_prompt") or "").strip(),
                    model=str(row_data.get("model") or "").strip() or None,
                    config=_json_object(row_data.get("config")),
                    output_schema=_json_object(row_data.get("output_schema")),
                    handoff_input_schema=_json_object(row_data.get("handoff_input_schema")),
                    tool_allowlist=_normalize_allowlist(row_data.get("tool_allowlist")),
                    skill_allowlist=_normalize_allowlist(row_data.get("skill_allowlist")),
                    mcp_allowlist=_normalize_allowlist(row_data.get("mcp_allowlist")),
                    knowledge_policy=_json_object(row_data.get("knowledge_policy")),
                    review_policy=_json_object(row_data.get("review_policy")),
                    runtime_policy=_json_object(row_data.get("runtime_policy")),
                    budget_policy=_json_object(row_data.get("budget_policy")),
                    metadata=merged_metadata,
                )
            )
            seen_publication_ids.add(publication_id)

        return targets

    async def _resolve_metadata_targets(self, definition: AgentDefinition) -> list[SubagentTarget]:
        raw_items = definition.metadata.get("subagents")
        if not isinstance(raw_items, list) or not raw_items:
            return []

        targets: list[SubagentTarget] = []
        seen_definition_ids: set[str] = set()
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue

            definition_id = str(
                entry.get("host_agent_definition_id")
                or entry.get("target_agent_definition_id")
                or entry.get("agent_definition_id")
                or entry.get("id")
                or ""
            ).strip()
            if not definition_id or definition_id in seen_definition_ids or definition_id == definition.id:
                continue

            child_definition = await self.agent_repository.get_definition(definition_id, definition.tenant_id)
            if child_definition is None or str(child_definition.get("status") or "active").strip().lower() == "archived":
                continue

            child_name = str(entry.get("name") or child_definition.get("name") or definition_id).strip()
            slug = _normalize_slug(entry.get("slug") or child_name or definition_id)
            if not slug:
                slug = definition_id

            description = str(entry.get("description") or child_definition.get("description") or "").strip() or None
            handoff_prompt = str(entry.get("handoff_prompt") or "").strip() or None
            metadata = {
                key: value
                for key, value in entry.items()
                if key not in {"id", "agent_definition_id", "slug", "name", "description", "handoff_prompt"}
            }

            targets.append(
                SubagentTarget(
                    slug=slug,
                    name=child_name,
                    agent_definition_id=definition_id,
                    description=description,
                    handoff_prompt=handoff_prompt,
                    metadata=metadata,
                )
            )
            seen_definition_ids.add(definition_id)

        return targets

    async def resolve_for_definition(self, definition: AgentDefinition) -> list[SubagentTarget]:
        authorized_targets = await self._resolve_authorized_targets(definition)
        if authorized_targets:
            return authorized_targets
        return await self._resolve_metadata_targets(definition)
