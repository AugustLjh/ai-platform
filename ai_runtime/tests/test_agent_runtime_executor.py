from ai_runtime.core.agent_runtime.executor import AgentExecutor
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig
from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from ai_runtime.core.agent_runtime.tools.registry import ToolRegistry


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


def test_executor_projects_alias_fields_into_nested_output_schema():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor.shape_output(
        {
            "summary": "Ship it in two controlled phases.",
            "steps": ["Update the result contract", "Backfill workspace hydration tests"],
            "sources": [
                {
                    "title": "Runtime Plan",
                    "snippet": "Structured outputs reduce rework.",
                }
            ],
        },
        {
            "type": "object",
            "required": ["answer", "task_plan", "citations"],
            "properties": {
                "answer": {"type": "string"},
                "task_plan": {
                    "type": "object",
                    "required": ["steps"],
                    "properties": {
                        "summary": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["title", "status"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "status": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "snippet"],
                        "properties": {
                            "title": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
            },
        },
    )

    assert shaped["answer"] == "Ship it in two controlled phases."
    assert shaped["task_plan"]["summary"] == "Ship it in two controlled phases."
    assert shaped["task_plan"]["steps"][0]["title"] == "Update the result contract"
    assert shaped["task_plan"]["steps"][0]["status"] == ""
    assert shaped["citations"][0]["title"] == "Runtime Plan"


def test_executor_parses_json_strings_and_splits_array_strings():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor.shape_output(
        """
        {
          "answer": "Use the merged contract.",
          "citations": [{"title": "Spec", "snippet": "Return JSON only."}],
          "open_questions": "edge cases\\nrollback path"
        }
        """,
        {
            "type": "object",
            "required": ["answer", "citations", "open_questions"],
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
                "open_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    )

    assert shaped["answer"] == "Use the merged contract."
    assert shaped["citations"][0]["title"] == "Spec"
    assert shaped["open_questions"] == ["edge cases", "rollback path"]


def test_executor_projects_root_list_into_single_array_property_and_enforces_enums():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor.shape_output(
        [
            {
                "summary": "Missing migration",
                "level": "HIGH",
                "details": "The new columns are never added.",
                "file": "db/alembic/versions/x.py",
                "line": "12",
            }
        ],
        {
            "type": "object",
            "required": ["review_findings"],
            "properties": {
                "review_findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "severity", "description"],
                        "properties": {
                            "title": {"type": "string"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "description": {"type": "string"},
                            "path": {"type": "string"},
                            "line": {"type": "integer"},
                        },
                    },
                }
            },
        },
    )

    assert shaped["review_findings"][0]["title"] == "Missing migration"
    assert shaped["review_findings"][0]["severity"] == "high"
    assert shaped["review_findings"][0]["description"] == "The new columns are never added."
    assert shaped["review_findings"][0]["path"] == "db/alembic/versions/x.py"
    assert shaped["review_findings"][0]["line"] == 12


def test_executor_coerces_additional_properties_and_array_constraints():
    executor = AgentExecutor(ToolRegistry())

    shaped = executor.shape_output(
        {
            "answer": "Return the strongest signals only.",
            "metrics": {"coverage": "98", "risk": "oops"},
            "open_questions": ["rollback path", "rollback path", "owner confirmation"],
        },
        {
            "type": "object",
            "required": ["answer", "metrics", "open_questions"],
            "properties": {
                "answer": {"type": "string"},
                "metrics": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "open_questions": {
                    "type": "array",
                    "uniqueItems": True,
                    "maxItems": 2,
                    "items": {"type": "string"},
                },
            },
        },
    )

    assert shaped["metrics"]["coverage"] == 98
    assert shaped["metrics"]["risk"] == 0
    assert shaped["open_questions"] == ["rollback path", "owner confirmation"]


class _CountingTool(BaseTool):
    spec = ToolSpec(name="counting_tool", description="Counts tool invocations.")

    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[ToolContext] = []

    async def execute(self, context: ToolContext, arguments):
        self.calls += 1
        self.contexts.append(context)
        return {"value": arguments["value"]}


class _CapturingProvider:
    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool
        self.lookup_contexts: list[ToolLookupContext | None] = []

    async def get(self, name: str, context: ToolLookupContext | None = None):
        self.lookup_contexts.append(context)
        if name == self.tool.spec.name:
            return self.tool
        return None

    async def list_specs(self, context: ToolLookupContext | None = None):
        return []

    async def get_spec(self, name: str, context: ToolLookupContext | None = None):
        return None


def test_executor_passes_session_id_and_reuses_cached_tool_results():
    registry = ToolRegistry()
    tool = _CountingTool()
    provider = _CapturingProvider(tool)
    registry.register_provider(provider)
    executor = AgentExecutor(registry)

    planner_result = type(
        "_PlannerResult",
        (),
        {
            "action": type(
                "_PlannerAction",
                (),
                {
                    "type": "tool_call",
                    "tool_name": "counting_tool",
                    "tool_arguments": {"value": 7},
                },
            )(),
        },
    )()
    context = ToolContext(
        run_id="run-1",
        session_id="session-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        step_id="step-1",
    )

    first = __import__("asyncio").run(executor.execute_tool(planner_result, tool_context=context))
    second = __import__("asyncio").run(executor.execute_tool(planner_result, tool_context=context))

    assert tool.calls == 1
    assert provider.lookup_contexts[0] is not None
    assert provider.lookup_contexts[0].session_id == "session-1"
    assert tool.contexts[0].session_id == "session-1"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_executor_can_disable_tool_result_cache():
    registry = ToolRegistry()
    tool = _CountingTool()
    registry.register(tool)
    executor = AgentExecutor(
        registry,
        optimization_config=AgentRuntimeOptimizationConfig(enable_tool_result_cache=False),
    )

    planner_result = type(
        "_PlannerResult",
        (),
        {
            "action": type(
                "_PlannerAction",
                (),
                {
                    "type": "tool_call",
                    "tool_name": "counting_tool",
                    "tool_arguments": {"value": 7},
                },
            )(),
        },
    )()
    context = ToolContext(
        run_id="run-1",
        session_id="session-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
        step_id="step-1",
    )

    first = __import__("asyncio").run(executor.execute_tool(planner_result, tool_context=context))
    second = __import__("asyncio").run(executor.execute_tool(planner_result, tool_context=context))

    assert tool.calls == 2
    assert first["cache_hit"] is False
    assert second["cache_hit"] is False
