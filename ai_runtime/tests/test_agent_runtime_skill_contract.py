from core.agent_runtime.skills.contract import apply_skill_contract, derive_skill_contract
from core.agent_runtime.skills.models import SkillDefinition


def test_apply_skill_contract_normalizes_capability_pack_contract():
    skill = apply_skill_contract(
        SkillDefinition(
            slug="kb-research",
            name="KB Research",
            system_prompt="research prompt",
            tool_allowlist=["knowledge_search", "knowledge_fetch_document"],
            output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            metadata={
                "activation_intents": ["Research", "summarize", "research"],
                "activation_phases": ["planning", "output", "output"],
            },
        )
    )

    assert skill.metadata["contract_kind"] == "capability_pack"
    assert skill.contract["kind"] == "capability_pack"
    assert skill.contract["tool_policy_mode"] == "allowlist"
    assert skill.contract["intent_policy"] == "explicit"
    assert skill.contract["phase_policy"] == "explicit"
    assert skill.contract["activation_intents"] == ["research", "summarize"]
    assert skill.contract["activation_phases"] == ["planning", "output"]
    assert skill.contract["surfaces"] == ["prompt", "tools", "output"]


def test_derive_skill_contract_upgrades_invalid_role_prompt_to_capability_pack():
    contract = derive_skill_contract(
        slug="code-review",
        name="Code Review",
        system_prompt="review prompt",
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        tool_allowlist=[],
        metadata={
            "contract_kind": "role_prompt",
            "activation_phases": ["planning", "output"],
        },
    )

    assert contract.kind == "capability_pack"
    assert contract.has_output_schema is True
    assert any("role_prompt" in warning for warning in contract.governance_warnings)


def test_derive_skill_contract_blocks_non_system_skill_without_explicit_contract_governance():
    contract = derive_skill_contract(
        slug="custom-review",
        name="Custom Review",
        system_prompt="review prompt",
        output_schema=None,
        tool_allowlist=[],
        metadata={},
    )

    assert contract.governance_status == "blocked"
    assert any("contract_kind" in error for error in contract.governance_errors)
    assert any("activation_intents" in error for error in contract.governance_errors)
    assert any("activation_phases" in error for error in contract.governance_errors)
