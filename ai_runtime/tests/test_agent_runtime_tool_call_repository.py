from __future__ import annotations

from ai_runtime.core.agent_runtime.events import MASK
from ai_runtime.core.agent_runtime.repositories.tool_call_repository import ToolCallRepository


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def fetchrow(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "run_id": "00000000-0000-0000-0000-000000000002",
            "step_id": None,
            "tool_name": "shell_exec",
            "tool_kind": "sandbox-exec",
            "status": "running",
            "arguments": args[5] if "INSERT INTO agent_tool_calls" in args[0] else {},
            "result": args[2] if "UPDATE agent_tool_calls" in args[0] else {},
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "created_at": None,
            "updated_at": None,
        }


async def test_tool_call_repository_redacts_arguments_and_results_before_storage():
    pool = FakePool()
    repository = ToolCallRepository(pool)

    await repository.create_tool_call(
        run_id="00000000-0000-0000-0000-000000000002",
        step_id=None,
        tool_name="shell_exec",
        tool_kind="sandbox-exec",
        arguments={
            "env": {"OPENAI_API_KEY": "sk-1234567890abcdef"},
            "command": ["bash", "-lc", "echo token=super-secret-token-value"],
        },
    )
    await repository.update_tool_call(
        "00000000-0000-0000-0000-000000000001",
        status="completed",
        result={"stdout": "Authorization: Bearer abcdefghijklmnop"},
    )

    serialized_calls = str(pool.calls)
    assert "sk-1234567890abcdef" not in serialized_calls
    assert "super-secret-token-value" not in serialized_calls
    assert "abcdefghijklmnop" not in serialized_calls
    assert MASK in serialized_calls
