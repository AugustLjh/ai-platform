from __future__ import annotations

from typing import List
from uuid import UUID

from core.agent_runtime.skills.loader import load_skill_row
from core.agent_runtime.skills.models import SkillDefinition, SkillRuntimeContext


def _serialize_uuid(value: str) -> UUID:
    return UUID(str(value))


class SkillRegistry:
    def __init__(self, db_pool) -> None:
        self.db_pool = db_pool

    def compose(self, skills: List[SkillDefinition]) -> SkillRuntimeContext:
        prompts = [skill.system_prompt.strip() for skill in skills if skill.system_prompt.strip()]
        tool_allowlist: List[str] = []
        seen_tools: set[str] = set()
        schemas = [skill.output_schema for skill in skills if skill.output_schema]

        for skill in skills:
            for tool_name in skill.tool_allowlist:
                if tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    tool_allowlist.append(tool_name)

        output_schema = {}
        if len(schemas) == 1:
            output_schema = schemas[0]
        elif len(schemas) > 1:
            output_schema = {"allOf": schemas}

        return SkillRuntimeContext(
            skills=skills,
            system_prompt="\n\n".join(prompts),
            tool_allowlist=tool_allowlist,
            output_schema=output_schema,
            metadata={
                "skill_ids": [skill.id for skill in skills if skill.id],
                "skill_slugs": [skill.slug for skill in skills],
            },
        )

    async def resolve_for_agent(self, agent_definition_id: str, tenant_id: str) -> SkillRuntimeContext:
        rows = await self.db_pool.fetch(
            """
            SELECT s.*
            FROM agent_skill_bindings b
            INNER JOIN skills s ON s.id = b.skill_id
            WHERE b.agent_definition_id = $1
              AND (s.tenant_id IS NULL OR s.tenant_id = $2)
            ORDER BY b.created_at ASC
            """,
            _serialize_uuid(agent_definition_id),
            _serialize_uuid(tenant_id),
        )
        skills = [load_skill_row(row) for row in rows]
        return self.compose(skills)
