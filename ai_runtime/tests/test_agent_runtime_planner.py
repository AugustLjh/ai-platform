from core.agent_runtime.planner import AgentPlanner


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
