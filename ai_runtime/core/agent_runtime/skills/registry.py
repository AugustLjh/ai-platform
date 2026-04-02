from __future__ import annotations

from collections.abc import Iterable
from typing import List
from uuid import UUID

from core.agent_runtime.schema_utils import merge_output_schema
from core.agent_runtime.skills.contract import derive_skill_contract
from core.agent_runtime.skills.loader import load_skill_row
from core.agent_runtime.skills.models import SkillDefinition, SkillRuntimeContext


def _serialize_uuid(value: str) -> UUID:
    return UUID(str(value))


class SkillRegistry:
    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    def _contract(self, skill: SkillDefinition) -> dict:
        if isinstance(skill.contract, dict) and skill.contract:
            return skill.contract
        return derive_skill_contract(
            slug=skill.slug,
            name=skill.name,
            system_prompt=skill.system_prompt,
            output_schema=skill.output_schema,
            tool_allowlist=skill.tool_allowlist,
            metadata=skill.metadata,
        ).model_dump(mode="json")

    def _is_fixed_binding(self, skill: SkillDefinition) -> bool:
        return self._contract(skill).get("binding_mode") == "fixed"

    def _normalize_allowlist(self, allowlist: Iterable[str] | None) -> tuple[set[str], set[str]]:
        ids: set[str] = set()
        slugs: set[str] = set()
        for item in allowlist or []:
            value = str(item or "").strip()
            if not value:
                continue
            slugs.add(value.lower())
            try:
                ids.add(str(_serialize_uuid(value)))
            except (TypeError, ValueError):
                continue
        return ids, slugs

    def _skill_matches_intent(self, skill: SkillDefinition, inferred_intent: str | None) -> bool:
        contract = self._contract(skill)
        if contract.get("intent_policy") != "explicit":
            return True
        activation_intents = contract.get("activation_intents")
        if not isinstance(activation_intents, list) or not activation_intents:
            return True

        normalized_intent = str(inferred_intent or "").strip().lower()
        if not normalized_intent:
            return False

        allowed_intents = {str(item).strip().lower() for item in activation_intents if str(item).strip()}
        return normalized_intent in allowed_intents

    def _skill_matches_phase(self, skill: SkillDefinition, phase: str | None) -> bool:
        contract = self._contract(skill)
        if contract.get("phase_policy") != "explicit":
            return True
        activation_phases = contract.get("activation_phases")
        if not isinstance(activation_phases, list) or not activation_phases:
            return True

        normalized_phase = str(phase or "").strip().lower()
        if not normalized_phase:
            return False

        allowed_phases = {str(item).strip().lower() for item in activation_phases if str(item).strip()}
        return normalized_phase in allowed_phases

    def _compose_context(
        self,
        skills: List[SkillDefinition],
        *,
        include_prompts: bool,
        include_tool_allowlist: bool,
        include_output_schema: bool,
        metadata: dict | None = None,
    ) -> SkillRuntimeContext:
        prompts = [skill.system_prompt.strip() for skill in skills if include_prompts and skill.system_prompt.strip()]
        tool_allowlist: List[str] = []
        seen_tools: set[str] = set()
        schemas = [skill.output_schema for skill in skills if include_output_schema and skill.output_schema]

        if include_tool_allowlist:
            for skill in skills:
                for tool_name in skill.tool_allowlist:
                    if tool_name not in seen_tools:
                        seen_tools.add(tool_name)
                        tool_allowlist.append(tool_name)

        output_schema = {}
        for schema in schemas:
            output_schema = merge_output_schema(output_schema, schema)

        capability_skill_slugs = [skill.slug for skill in skills if self._contract(skill).get("kind") == "capability_pack"]
        role_prompt_skill_slugs = [skill.slug for skill in skills if self._contract(skill).get("kind") == "role_prompt"]

        return SkillRuntimeContext(
            skills=skills,
            system_prompt="\n\n".join(prompts),
            tool_allowlist=tool_allowlist,
            output_schema=output_schema,
            metadata={
                **(metadata or {}),
                "capability_skill_slugs": capability_skill_slugs,
                "role_prompt_skill_slugs": role_prompt_skill_slugs,
                "skill_contracts": [self._contract(skill) for skill in skills],
            },
        )

    def compose(self, skills: List[SkillDefinition]) -> SkillRuntimeContext:
        return self._compose_context(
            skills,
            include_prompts=True,
            include_tool_allowlist=True,
            include_output_schema=True,
            metadata={
                "skill_ids": [skill.id for skill in skills if skill.id],
                "skill_slugs": [skill.slug for skill in skills],
            },
        )

    def compose_for_intent_phase(
        self,
        skills: List[SkillDefinition],
        *,
        inferred_intent: str | None,
        phase: str,
    ) -> SkillRuntimeContext:
        normalized_intent = str(inferred_intent or "").strip().lower()
        normalized_phase = str(phase or "").strip().lower()
        filtered_skills: List[SkillDefinition] = []

        for skill in skills:
            if not self._skill_matches_intent(skill, normalized_intent):
                continue
            if not self._skill_matches_phase(skill, normalized_phase):
                continue
            filtered_skills.append(skill)

        return self._compose_context(
            filtered_skills,
            include_prompts=normalized_phase in {"planning", "synthesis"},
            include_tool_allowlist=normalized_phase == "execution",
            include_output_schema=normalized_phase == "output",
            metadata={
                "skill_ids": [skill.id for skill in filtered_skills if skill.id],
                "skill_slugs": [skill.slug for skill in filtered_skills],
                "all_skill_slugs": [skill.slug for skill in skills],
                "filtered_for_intent": normalized_intent or None,
                "filtered_for_phase": normalized_phase,
            },
        )

    async def resolve_for_agent(self, agent_definition_id: str, tenant_id: str) -> SkillRuntimeContext:
        rows = await self.db_pool.fetch(
            """
            SELECT s.*
            FROM skills s
            LEFT JOIN agent_skill_bindings b
              ON b.skill_id = s.id
             AND b.agent_definition_id = $1
            WHERE (s.tenant_id IS NULL OR s.tenant_id = $2)
              AND (
                    b.id IS NOT NULL
                    OR COALESCE((s.metadata->>'fixed_binding')::boolean, false)
                  )
            ORDER BY
                CASE
                    WHEN COALESCE((s.metadata->>'fixed_binding')::boolean, false) THEN 0
                    ELSE 1
                END ASC,
                b.created_at ASC NULLS LAST,
                lower(s.slug) ASC
            """,
            _serialize_uuid(agent_definition_id),
            _serialize_uuid(tenant_id),
        )
        skills = [load_skill_row(row) for row in rows]
        return SkillRuntimeContext(
            skills=skills,
            metadata={
                "skill_ids": [skill.id for skill in skills if skill.id],
                "skill_slugs": [skill.slug for skill in skills],
            },
        )

    async def resolve_for_allowlist(
        self,
        *,
        tenant_id: str,
        allowlist: Iterable[str] | None,
        include_fixed_bindings: bool = True,
    ) -> SkillRuntimeContext:
        allowlist_ids, allowlist_slugs = self._normalize_allowlist(allowlist)
        rows = await self.db_pool.fetch(
            """
            SELECT s.*
            FROM skills s
            WHERE s.tenant_id IS NULL OR s.tenant_id = $1
            ORDER BY lower(s.slug) ASC
            """,
            _serialize_uuid(tenant_id),
        )
        skills: list[SkillDefinition] = []
        for row in rows:
            skill = load_skill_row(row)
            slug = str(skill.slug or "").strip().lower()
            included = False
            if skill.id and skill.id in allowlist_ids:
                included = True
            elif slug and slug in allowlist_slugs:
                included = True
            elif include_fixed_bindings and self._is_fixed_binding(skill):
                included = True

            if included:
                skills.append(skill)

        return SkillRuntimeContext(
            skills=skills,
            metadata={
                "skill_ids": [skill.id for skill in skills if skill.id],
                "skill_slugs": [skill.slug for skill in skills],
                "allowlist": list(allowlist or []),
                "include_fixed_bindings": include_fixed_bindings,
            },
        )
