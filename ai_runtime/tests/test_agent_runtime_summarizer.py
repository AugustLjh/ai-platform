import asyncio

from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig
from ai_runtime.core.agent_runtime.summarizer import AgentSummarizer


def test_summarizer_system_prompt_uses_codex_style_guidance():
    summarizer = AgentSummarizer()

    prompt = summarizer._build_system_prompt(
        system_prompt="Stay grounded in evidence.",
        output_schema=None,
    )

    assert "You are the final response composer for a Codex-style autonomous engineering agent." in prompt
    assert "Use a direct, factual, pragmatic tone." in prompt
    assert "Default to short paragraphs instead of bloated bullet lists." in prompt
    assert "If verification ran, mention it briefly. If verification did not run, say so instead of implying success." in prompt
    assert "Stay grounded in evidence." in prompt


def test_summarizer_system_prompt_includes_schema_example_and_guidance():
    summarizer = AgentSummarizer()

    prompt = summarizer._build_system_prompt(
        system_prompt="",
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "task_plan": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "risks": {"type": "array", "items": {"type": "string"}},
            },
        },
    )

    assert "Use this output shape as a model for structure and field naming:" in prompt
    assert "\"answer\": \"Concise final answer grounded in the execution record.\"" in prompt
    assert "When task_plan is present, include ordered implementation steps and concrete risks." in prompt


def test_summarizer_normalizes_allof_schema_before_rendering_prompt():
    summarizer = AgentSummarizer()

    prompt = summarizer._build_system_prompt(
        system_prompt="",
        output_schema={
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "task_plan": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "steps": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
                {
                    "type": "object",
                    "properties": {
                        "citations": {"type": "array", "items": {"type": "string"}},
                    },
                },
            ]
        },
    )

    assert "\"task_plan\"" in prompt
    assert "\"citations\"" in prompt
    assert "\"allOf\"" not in prompt
    assert "When citations is present, include sources that directly support the answer." in prompt


def test_summarizer_prompt_mentions_required_fields_and_enum_guidance():
    summarizer = AgentSummarizer()

    prompt = summarizer._build_system_prompt(
        system_prompt="",
        output_schema={
            "type": "object",
            "required": ["answer", "status"],
            "properties": {
                "answer": {"type": "string"},
                "status": {"type": "string", "enum": ["done", "blocked"]},
                "task_plan": {
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "status": {"type": "string", "enum": ["completed", "pending"]},
                                },
                            },
                        }
                    },
                },
            },
        },
    )

    assert "Do not omit required fields: answer, status." in prompt
    assert "When status is present, use one of: done, blocked." in prompt
    assert "\"status\": \"done\"" in prompt


def test_summarizer_direct_short_circuit_uses_planner_note():
    summarizer = AgentSummarizer(
        optimization_config=AgentRuntimeOptimizationConfig(enable_summarizer_short_circuit=True),
    )

    text, model_info = asyncio.run(
        summarizer.summarize(
            llm_service=None,
            llm_resolution={"candidates": [{}]},
            system_prompt="",
            run_input={"message": "ignore"},
            runtime_context={},
            skill_context=None,
            planner_note="Summarize the findings.",
        )
    )

    assert text == "Summarize the findings."
    assert model_info["model_source"] == "short_circuit"


def test_summarizer_does_not_short_circuit_to_user_input_when_no_answer_exists():
    class _FailingLLMService:
        async def chat_with_candidates(self, *args, **kwargs):
            raise RuntimeError("llm required")

    summarizer = AgentSummarizer(
        optimization_config=AgentRuntimeOptimizationConfig(enable_summarizer_short_circuit=True),
    )

    try:
        asyncio.run(
            summarizer.summarize(
                llm_service=_FailingLLMService(),
                llm_resolution={"candidates": [{}]},
                system_prompt="",
                run_input={"message": "user task"},
                runtime_context={},
                skill_context=None,
                planner_note=None,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "llm required"
    else:
        raise AssertionError("expected llm fallback when no direct final text exists")
