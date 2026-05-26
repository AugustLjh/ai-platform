"""Tests for ai_runtime.tools.base — ToolContext, ContextVar, AiPlatformTool."""
from __future__ import annotations

import asyncio
import pytest
from typing import Any, Type

from pydantic import BaseModel, Field

from ai_runtime.tools.base import (
    AiPlatformTool,
    ToolContext,
    _TOOL_CONTEXT_VAR,
    current_tool_context,
    current_tool_context_optional,
)


class SimpleArgs(BaseModel):
    query: str = Field(description="A query string")


class SimpleTool(AiPlatformTool):
    name: str = "simple_tool"
    description: str = "A simple test tool"
    args_schema: Type[BaseModel] = SimpleArgs

    async def _arun(self, query: str) -> dict[str, Any]:
        ctx = current_tool_context()
        return {"query": query, "run_id": ctx.run_id, "tenant_id": ctx.tenant_id}


class TestToolContext:
    def test_create_minimal(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        assert ctx.run_id == "r1"
        assert ctx.tenant_id == "t1"
        assert ctx.user_id is None
        assert ctx.workspace_root is None
        assert ctx.execution_mode == "autonomous"
        assert ctx.governance == {}

    def test_create_full(self):
        ctx = ToolContext(
            run_id="r1",
            tenant_id="t1",
            user_id="u1",
            request_id="req1",
            session_id="s1",
            agent_definition_id="ad1",
            step_id="step1",
            workspace_root="/tmp/ws",
            execution_mode="supervised",
            governance={"max_risk_level": "medium"},
            allowed_knowledge_base_ids=("kb1", "kb2"),
            allowed_mcp_server_ids=("mcp1",),
            allowed_mcp_tool_names=("tool1",),
        )
        assert ctx.user_id == "u1"
        assert ctx.workspace_root == "/tmp/ws"
        assert ctx.execution_mode == "supervised"
        assert ctx.governance == {"max_risk_level": "medium"}
        assert ctx.allowed_knowledge_base_ids == ("kb1", "kb2")

    def test_bind_sets_and_resets_contextvar(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        assert _TOOL_CONTEXT_VAR.get() is None
        with ctx.bind():
            assert _TOOL_CONTEXT_VAR.get() is ctx
            assert current_tool_context() is ctx
        assert _TOOL_CONTEXT_VAR.get() is None

    def test_nested_bind(self):
        ctx1 = ToolContext(run_id="r1", tenant_id="t1")
        ctx2 = ToolContext(run_id="r2", tenant_id="t2")
        with ctx1.bind():
            assert current_tool_context().run_id == "r1"
            with ctx2.bind():
                assert current_tool_context().run_id == "r2"
            assert current_tool_context().run_id == "r1"
        assert current_tool_context_optional() is None

    def test_current_tool_context_raises_when_unset(self):
        assert current_tool_context_optional() is None
        with pytest.raises(LookupError, match="No ToolContext bound"):
            current_tool_context()

    def test_to_legacy_context_returns_none_when_legacy_unavailable(self):
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        # In this test environment, legacy module may not be importable.
        # The method should return None or a valid legacy context.
        result = ctx.to_legacy_context()
        # Either None (legacy not available) or has run_id attribute.
        if result is not None:
            assert result.run_id == "r1"


class TestAiPlatformTool:
    def test_tool_has_correct_name_and_description(self):
        tool = SimpleTool()
        assert tool.name == "simple_tool"
        assert tool.description == "A simple test tool"

    def test_tool_args_schema(self):
        tool = SimpleTool()
        schema = tool.get_input_schema().model_json_schema()
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_tool_arun_with_context(self):
        tool = SimpleTool()
        ctx = ToolContext(run_id="run123", tenant_id="tenant456")
        with ctx.bind():
            result = await tool.ainvoke({"query": "hello"})
        assert result == {
            "query": "hello",
            "run_id": "run123",
            "tenant_id": "tenant456",
        }

    @pytest.mark.asyncio
    async def test_tool_arun_without_context_raises(self):
        tool = SimpleTool()
        with pytest.raises(LookupError):
            await tool.ainvoke({"query": "hello"})

    def test_sync_run_raises_not_implemented(self):
        tool = SimpleTool()
        with pytest.raises(NotImplementedError):
            tool._run(query="hello")

    def test_result_schema_default_none(self):
        assert SimpleTool.result_schema is None

    def test_response_format_default(self):
        tool = SimpleTool()
        assert tool.response_format == "content"
