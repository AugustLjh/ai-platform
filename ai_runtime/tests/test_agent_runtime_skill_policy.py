from ai_runtime.graphs.agent.runtime import apply_skill_tool_policy
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


def test_managed_tool_kinds_keep_provider_tools_with_legacy_provider_alias():
    available_tools = [
        {"name": "calculator", "kind": "builtin"},
        {"name": "project_list_context", "kind": "project-context", "metadata": {"legacy_provider": "engineering"}},
        {"name": "workspace_read_file", "kind": "workspace", "metadata": {"provider": "workspace"}},
    ]
    skill_context = SkillRuntimeContext(
        skills=[SkillDefinition(slug="engineering", name="Project Context")],
        tool_allowlist=["calculator"],
        metadata={
            "skill_contracts": [
                {
                    "kind": "capability_pack",
                    "managed_tool_kinds": ["engineering"],
                }
            ]
        },
    )

    filtered_tools, runtime_policy, effective_allowlist = apply_skill_tool_policy(
        available_tools,
        skill_context,
    )

    assert [tool["name"] for tool in filtered_tools] == ["calculator", "project_list_context"]
    assert effective_allowlist == ["calculator", "project_list_context"]
    assert runtime_policy.is_tool_allowed("project_list_context")
    assert not runtime_policy.is_tool_allowed("workspace_read_file")
