import json
import asyncio

from ai_runtime.core.agent_runtime.models import AgentDefinition
from ai_runtime.core.agent_runtime.planner import AgentPlanner
from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


def test_planner_parses_fenced_json_response():
    planner = AgentPlanner()
    result = planner._parse_planner_response(
        """```json
        {
          "reasoning": "Need to search first",
          "steps": [
            {"title": "Search docs", "kind": "tool", "status": "in_progress"},
            {"title": "Write final answer", "kind": "final", "status": "pending"}
          ],
          "action": {
            "type": "tool_call",
            "title": "Search knowledge base",
            "tool_name": "knowledge_search",
            "tool_arguments": {"query": "agent runtime"}
          }
        }
        ```""",
        available_tools=[
            {
                "name": "knowledge_search",
                "description": "Search knowledge",
                "input_schema": {},
                "kind": "knowledge",
            }
        ],
        iteration=2,
        model_info={"resolved_model_name": "Planner Model"},
    )

    assert result.iteration == 2
    assert result.reasoning == "Need to search first"
    assert result.action.type == "tool_call"
    assert result.action.tool_name == "knowledge_search"
    assert result.steps[0].title == "Search docs"
    assert result.metadata["resolved_model_name"] == "Planner Model"


def test_planner_rejects_unavailable_tool():
    planner = AgentPlanner()

    try:
        planner._parse_planner_response(
            """
            {
              "reasoning": "Call a tool",
              "action": {
                "type": "tool_call",
                "title": "Use shell",
                "tool_name": "shell_exec",
                "tool_arguments": {}
              }
            }
            """,
            available_tools=[
                {
                    "name": "calculator",
                    "description": "Evaluate arithmetic",
                    "input_schema": {},
                    "kind": "builtin",
                }
            ],
            iteration=1,
            model_info={},
        )
    except ValueError as exc:
        assert "unavailable tool" in str(exc)
    else:
        raise AssertionError("expected planner to reject unavailable tool")


def test_planner_system_prompt_requires_tool_attempts_before_asking_user():
    planner = AgentPlanner()
    prompt = planner._build_system_prompt(
        definition=AgentDefinition.model_validate(
            {
                "id": "agent-1",
                "tenant_id": "tenant-1",
                "name": "Test Agent",
                "system_prompt": "",
                "created_at": "2026-03-27T00:00:00Z",
                "updated_at": "2026-03-27T00:00:00Z",
            }
        ),
        available_tools=[
            {
                "name": "knowledge_search",
                "description": "Search knowledge",
                "input_schema": {},
                "kind": "knowledge",
            }
        ],
    )

    assert "You are Codex-style planning brain for an autonomous engineering agent." in prompt
    assert "Operate with a direct, execution-first mindset" in prompt
    assert "Assume the user wants action, not discussion" in prompt
    assert "Persist until the task is actually complete within the current run whenever the available tools make that possible." in prompt
    assert "Prefer making progress with the existing tools before asking the user." in prompt
    assert "attempt exactly one self-recovery iteration before ask_user." in prompt
    assert "Choose ask_user only when the missing information is still required" in prompt
    assert "Choose the action that most directly reduces uncertainty or advances the main task right now" in prompt
    assert "Keep reasoning compact, explicit, and evidence-backed." in prompt


def test_planner_user_prompt_includes_tool_failure_state():
    planner = AgentPlanner()
    prompt = planner._build_user_prompt(
        run_input={"message": "find docs"},
        runtime_context={
            "conversation": [{"role": "user", "content": "find docs"}],
            "step_history": [{"status": "failed", "tool_name": "knowledge_search"}],
            "tool_failures": 1,
            "execution_count": 2,
            "mounted_knowledge_base_ids": ["kb-1"],
            "pending_question": None,
        },
        iteration=2,
    )

    assert "Work in a Codex-style execution loop" in prompt
    payload = json.loads(prompt.split("\n\n", 1)[1])
    assert payload["tool_failures"] == 1
    assert payload["step_history"][0]["status"] == "failed"
    assert payload["recent_observations"][0]["tool_name"] == "knowledge_search"
    assert payload["latest_observation"]["status"] == "failed"
    assert payload["context_state"]["execution_count"] == 2
    assert payload["context_state"]["mounted_knowledge_base_ids"] == ["kb-1"]


def test_planner_retries_once_when_initial_json_is_invalid():
    class FakeLLMService:
        def __init__(self):
            self.calls = 0

        async def chat_with_candidates(self, resolution, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return """```json
                {
                  "reasoning": "Need to answer",
                  "steps": [
                    {"title": "Analyze", "kind": "analysis", "status": "completed"}
                  ]
                """, {"resolved_model_name": "Planner Model"}

            return json.dumps(
                {
                    "reasoning": "Need to answer",
                    "steps": [
                        {"title": "Analyze", "kind": "analysis", "status": "completed"},
                        {"title": "Return answer", "kind": "final", "status": "in_progress"},
                    ],
                    "action": {
                        "type": "final_answer",
                        "title": "Return final answer",
                        "content": "Provide the answer directly",
                    },
                },
                ensure_ascii=False,
            ), {"resolved_model_name": "Planner Model"}

    planner = AgentPlanner()
    definition = AgentDefinition.model_validate(
        {
            "id": "agent-1",
            "tenant_id": "tenant-1",
            "name": "Test Agent",
            "system_prompt": "",
            "created_at": "2026-03-27T00:00:00Z",
            "updated_at": "2026-03-27T00:00:00Z",
        }
    )

    result = asyncio.run(
        planner.plan(
            definition,
            {"message": "用python写一个简单的计算器代码"},
            [],
            runtime_context={"conversation": [], "step_history": []},
            iteration=1,
            llm_service=FakeLLMService(),
            llm_resolution={"candidates": [{}]},
        )
    )

    assert result.action.type == "final_answer"
    assert result.metadata["repair_attempted"] is True
    assert "initial_raw_response" in result.metadata


def test_planner_parses_delegate_action_against_available_subagents():
    planner = AgentPlanner()
    result = planner._parse_planner_response(
        """
        {
          "reasoning": "The review specialist can inspect this faster.",
          "steps": [
            {"title": "Delegate targeted review", "kind": "analysis", "status": "in_progress"}
          ],
          "action": {
            "type": "delegate",
            "title": "Ask review specialist",
            "delegate_target": "review-specialist",
            "delegate_task": "Review the patch for migration risks",
            "delegate_input": {
              "focus_paths": ["db/alembic/versions/example.py"]
            },
            "content": "Use the specialized reviewer for a bounded code review pass."
          }
        }
        """,
        available_tools=[],
        available_subagents=[
            SubagentTarget(
                slug="review-specialist",
                name="Review Specialist",
                agent_definition_id="agent-reviewer",
                description="Focused code review agent",
            )
        ],
        iteration=3,
        model_info={"resolved_model_name": "Planner Model"},
    )

    assert result.action.type == "delegate"
    assert result.action.delegate_target == "review-specialist"
    assert result.action.delegate_task == "Review the patch for migration risks"
    assert result.action.delegate_input["focus_paths"] == ["db/alembic/versions/example.py"]
