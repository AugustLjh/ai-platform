from core.agent_runtime.summarizer import AgentSummarizer


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
