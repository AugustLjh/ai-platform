from ai_runtime.core.agent_runtime.tools.providers.engineering import EngineeringToolProvider


async def test_project_context_provider_exposes_policy_metadata():
    provider = EngineeringToolProvider(enabled_tool_names=["project_list_context"])

    specs = await provider.list_specs()

    assert specs[0]["kind"] == "project-context"
    assert specs[0]["metadata"]["provider"] == "project-context"
    assert specs[0]["metadata"]["legacy_provider"] == "engineering"
    assert specs[0]["metadata"]["requires_workspace"] is False
    assert specs[0]["metadata"]["requires_sandbox"] is False
    assert specs[0]["metadata"]["side_effect"] == "none"


async def test_project_context_provider_prefers_new_env_name(monkeypatch):
    monkeypatch.setenv("AGENT_PROJECT_CONTEXT_TOOLS", "project_search_context")
    monkeypatch.setenv("AGENT_ENGINEERING_TOOLS", "project_list_context")

    provider = EngineeringToolProvider.from_env()
    specs = await provider.list_specs()

    assert [spec["name"] for spec in specs] == ["project_search_context"]
