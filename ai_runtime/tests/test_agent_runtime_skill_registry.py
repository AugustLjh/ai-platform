import asyncio

from core.agent_runtime.skills.models import SkillDefinition
from core.agent_runtime.skills.registry import SkillRegistry


def test_compose_for_non_plan_intent_filters_implementation_planner_from_output_phase():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                system_prompt="planner prompt",
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["plan"], "activation_phases": ["planning", "synthesis", "output"]},
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}, "steps": {"type": "array"}},
                },
            ),
            SkillDefinition(
                slug="engineering",
                name="Engineering",
                system_prompt="engineering prompt",
                metadata={"activation_intents": ["implement", "plan", "review"], "activation_phases": ["planning", "execution", "synthesis"]},
            ),
        ],
        inferred_intent="answer",
        phase="output",
    )

    assert [skill.slug for skill in context.skills] == []
    assert context.output_schema == {}
    assert context.system_prompt == ""


def test_compose_for_plan_intent_keeps_implementation_planner_in_output_phase():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                system_prompt="planner prompt",
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["plan"], "activation_phases": ["planning", "synthesis", "output"]},
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}, "steps": {"type": "array"}},
                },
            ),
        ],
        inferred_intent="plan",
        phase="output",
    )

    assert [skill.slug for skill in context.skills] == ["implementation-planner"]
    assert context.output_schema["properties"]["summary"]["type"] == "string"
    assert context.system_prompt == ""


def test_compose_for_review_intent_keeps_review_and_engineering_skills_in_synthesis_phase():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                system_prompt="planner prompt",
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["plan"], "activation_phases": ["planning", "synthesis", "output"]},
            ),
            SkillDefinition(
                slug="code-review",
                name="Code Review",
                system_prompt="review prompt",
                metadata={"contract_kind": "capability_pack", "activation_intents": ["review"], "activation_phases": ["planning", "synthesis", "output"]},
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}, "findings": {"type": "array"}},
                },
            ),
            SkillDefinition(
                slug="engineering",
                name="Engineering",
                system_prompt="engineering prompt",
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["implement", "plan", "review"], "activation_phases": ["planning", "execution", "synthesis"]},
            ),
        ],
        inferred_intent="review",
        phase="synthesis",
    )

    assert [skill.slug for skill in context.skills] == ["code-review", "engineering"]
    assert context.output_schema == {}
    assert "review prompt" in context.system_prompt
    assert "engineering prompt" in context.system_prompt


def test_compose_for_research_intent_keeps_kb_research_skill_in_output_phase():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="kb-research",
                name="KB Research",
                system_prompt="research prompt",
                metadata={"contract_kind": "capability_pack", "activation_intents": ["research", "compare", "summarize"], "activation_phases": ["planning", "synthesis", "output"]},
                output_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}, "sources": {"type": "array"}},
                },
            ),
            SkillDefinition(
                slug="code-review",
                name="Code Review",
                system_prompt="review prompt",
                metadata={"contract_kind": "capability_pack", "activation_intents": ["review"], "activation_phases": ["planning", "synthesis", "output"]},
            ),
        ],
        inferred_intent="research",
        phase="output",
    )

    assert [skill.slug for skill in context.skills] == ["kb-research"]
    assert context.output_schema["properties"]["sources"]["type"] == "array"
    assert context.system_prompt == ""


def test_compose_for_execution_phase_only_uses_tool_allowlists():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="engineering",
                name="Engineering",
                system_prompt="engineering prompt",
                tool_allowlist=["project_search_context"],
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["implement"], "activation_phases": ["planning", "execution", "synthesis"]},
            ),
            SkillDefinition(
                slug="code-review",
                name="Code Review",
                system_prompt="review prompt",
                tool_allowlist=["knowledge_search"],
                metadata={"contract_kind": "capability_pack", "activation_intents": ["review"], "activation_phases": ["planning", "synthesis", "output"]},
            ),
        ],
        inferred_intent="implement",
        phase="execution",
    )

    assert [skill.slug for skill in context.skills] == ["engineering"]
    assert context.system_prompt == ""
    assert context.output_schema == {}
    assert context.tool_allowlist == ["project_search_context"]


def test_compose_for_output_phase_merges_multiple_skill_output_schemas():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose_for_intent_phase(
        [
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                metadata={"system_skill": True, "contract_kind": "capability_pack", "activation_intents": ["plan"], "activation_phases": ["output"]},
                output_schema={
                    "type": "object",
                    "required": ["answer", "task_plan"],
                    "properties": {
                        "answer": {"type": "string"},
                        "task_plan": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                            },
                        },
                    },
                },
            ),
            SkillDefinition(
                slug="kb-research",
                name="KB Research",
                metadata={"contract_kind": "capability_pack", "activation_intents": ["plan"], "activation_phases": ["output"]},
                output_schema={
                    "type": "object",
                    "required": ["citations"],
                    "properties": {
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            ),
        ],
        inferred_intent="plan",
        phase="output",
    )

    assert context.output_schema["type"] == "object"
    assert context.output_schema["properties"]["answer"]["type"] == "string"
    assert context.output_schema["properties"]["task_plan"]["type"] == "object"
    assert context.output_schema["properties"]["citations"]["type"] == "array"
    assert context.output_schema["required"] == ["answer", "task_plan", "citations"]


def test_resolve_for_agent_does_not_hardcode_implementation_planner():
    captured = {}

    class FakePool:
        async def fetch(self, query, *args):
            captured["query"] = query
            return []

    registry = SkillRegistry(db_pool=FakePool())
    asyncio.run(
        registry.resolve_for_agent(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        )
    )

    assert "lower(s.slug) = 'implementation-planner'" not in captured["query"]


def test_resolve_for_allowlist_keeps_fixed_bindings_and_selected_skills():
    class FakePool:
        async def fetch(self, query, *args):
            return [
                {
                    "id": "00000000-0000-0000-0000-000000000010",
                    "tenant_id": None,
                    "name": "Implementation Planner",
                    "slug": "implementation-planner",
                    "version": "1",
                    "description": "",
                    "root_path": "",
                    "system_prompt": "planner prompt",
                    "output_schema": {},
                    "tool_allowlist": [],
                    "metadata": {"system_skill": True, "contract_kind": "capability_pack", "fixed_binding": True, "activation_intents": ["plan"], "activation_phases": ["planning", "synthesis", "output"]},
                },
                {
                    "id": "00000000-0000-0000-0000-000000000011",
                    "tenant_id": None,
                    "name": "Code Review",
                    "slug": "code-review",
                    "version": "1",
                    "description": "",
                    "root_path": "",
                    "system_prompt": "review prompt",
                    "output_schema": {},
                    "tool_allowlist": [],
                    "metadata": {"contract_kind": "capability_pack", "activation_intents": ["review"], "activation_phases": ["planning", "synthesis", "output"]},
                },
                {
                    "id": "00000000-0000-0000-0000-000000000012",
                    "tenant_id": None,
                    "name": "KB Research",
                    "slug": "kb-research",
                    "version": "1",
                    "description": "",
                    "root_path": "",
                    "system_prompt": "research prompt",
                    "output_schema": {},
                    "tool_allowlist": [],
                    "metadata": {"contract_kind": "capability_pack", "activation_intents": ["research"], "activation_phases": ["planning", "synthesis", "output"]},
                },
            ]

    registry = SkillRegistry(db_pool=FakePool())
    context = asyncio.run(
        registry.resolve_for_allowlist(
            tenant_id="00000000-0000-0000-0000-000000000002",
            allowlist=["code-review"],
            include_fixed_bindings=True,
        )
    )

    assert [skill.slug for skill in context.skills] == ["implementation-planner", "code-review"]


def test_compose_filters_governance_blocked_skills_and_keeps_blocked_metadata():
    registry = SkillRegistry(db_pool=None)
    context = registry.compose(
        [
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                metadata={
                    "system_skill": True,
                    "fixed_binding": True,
                    "contract_kind": "capability_pack",
                    "activation_intents": ["plan"],
                    "activation_phases": ["planning"],
                },
                system_prompt="planner prompt",
            ),
            SkillDefinition(
                slug="custom-review",
                name="Custom Review",
                system_prompt="review prompt",
                metadata={},
            ),
        ]
    )

    assert [skill.slug for skill in context.skills] == ["implementation-planner"]
    assert context.metadata["skill_slugs"] == ["implementation-planner"]
    assert len(context.metadata["blocked_skill_contracts"]) == 1
    assert context.metadata["blocked_skill_contracts"][0]["slug"] == "custom-review"
