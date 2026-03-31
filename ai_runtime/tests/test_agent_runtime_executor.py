from core.agent_runtime.executor import AgentExecutor
from core.agent_runtime.tools.registry import ToolRegistry


def test_executor_shapes_plan_schema_into_structured_object():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor._shape_output(
        "Implement the runtime contract first.",
        {
            "type": "object",
            "required": ["answer", "task_plan", "risks"],
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

    assert shaped["answer"] == "Implement the runtime contract first."
    assert shaped["task_plan"]["summary"] == ""
    assert shaped["task_plan"]["steps"] == []
    assert shaped["risks"] == []


def test_executor_shapes_review_findings_items():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor._shape_output(
        {
            "answer": "Two concrete issues found.",
            "review_findings": [
                {
                    "title": "Missing migration",
                    "severity": "high",
                    "description": "The new columns are never added.",
                    "path": "db/alembic/versions/x.py",
                    "line": "12",
                }
            ],
        },
        {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "review_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "severity": {"type": "string"},
                            "description": {"type": "string"},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                        },
                    },
                },
            },
        },
    )

    assert shaped["review_findings"][0]["title"] == "Missing migration"
    assert shaped["review_findings"][0]["line"] == 12


def test_executor_merges_allof_schema_before_shaping():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor.shape_output(
        "Plan the rollout and keep research notes.",
        {
            "allOf": [
                {
                    "type": "object",
                    "required": ["answer", "task_plan"],
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
                    "required": ["citations"],
                    "properties": {
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "snippet": {"type": "string"},
                                },
                            },
                        }
                    },
                },
            ]
        },
    )

    assert shaped["answer"] == "Plan the rollout and keep research notes."
    assert shaped["task_plan"]["summary"] == ""
    assert shaped["task_plan"]["steps"] == []
    assert shaped["citations"] == []
