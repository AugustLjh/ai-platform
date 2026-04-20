from ai_runtime.core.agent_runtime.orchestrator import apply_skill_tool_policy
from ai_runtime.core.agent_runtime.skills.models import SkillDefinition, SkillRuntimeContext


def test_empty_skill_allowlist_keeps_available_tools():
    available_tools = [
        {"name": "calculator", "kind": "builtin"},
        {"name": "echo_json", "kind": "builtin"},
    ]
    skill_context = SkillRuntimeContext(
        skills=[
            SkillDefinition(
                slug="implementation-planner",
                name="Implementation Planner",
                tool_allowlist=[],
            )
        ],
        tool_allowlist=[],
    )

    filtered_tools, runtime_policy, effective_allowlist = apply_skill_tool_policy(
        available_tools,
        skill_context,
    )

    assert filtered_tools == available_tools
    assert effective_allowlist is None
    assert runtime_policy.is_tool_allowed("calculator")
    assert runtime_policy.is_tool_allowed("echo_json")


def test_non_empty_skill_allowlist_filters_available_tools():
    available_tools = [
        {"name": "calculator", "kind": "builtin"},
        {"name": "echo_json", "kind": "builtin"},
    ]
    skill_context = SkillRuntimeContext(
        skills=[
            SkillDefinition(
                slug="calc-only",
                name="Calculator Only",
                tool_allowlist=["calculator"],
            )
        ],
        tool_allowlist=["calculator"],
    )

    filtered_tools, runtime_policy, effective_allowlist = apply_skill_tool_policy(
        available_tools,
        skill_context,
    )

    assert filtered_tools == [{"name": "calculator", "kind": "builtin"}]
    assert effective_allowlist == ["calculator"]
    assert runtime_policy.is_tool_allowed("calculator")
    assert not runtime_policy.is_tool_allowed("echo_json")
