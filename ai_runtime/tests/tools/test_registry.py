"""Tests for ai_runtime.tools.registry — ToolRegistry filtering and build_for_run."""
from __future__ import annotations

import pytest
from typing import Any, Type

from pydantic import BaseModel, Field

from ai_runtime.tools.base import AiPlatformTool, ToolContext
from ai_runtime.tools.registry import ToolRegistry, ToolRegistration


class DummyArgs(BaseModel):
    x: str = Field(default="")


def _make_tool(name: str, description: str = "test") -> AiPlatformTool:
    """Create a minimal tool with the given name."""

    class T(AiPlatformTool):
        args_schema: Type[BaseModel] = DummyArgs

        async def _arun(self, x: str = "") -> dict[str, Any]:
            return {"x": x}

    return T(name=name, description=description)


class TestToolRegistry:
    def test_register_and_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(_make_tool("t1"))
        assert len(reg) == 1
        assert "t1" in reg

    def test_register_many(self):
        reg = ToolRegistry()
        reg.register_many([_make_tool("a"), _make_tool("b"), _make_tool("c")])
        assert len(reg) == 3
        assert reg.tool_names == ["a", "b", "c"]

    def test_register_overwrites_same_name(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"), kind="builtin")
        reg.register(_make_tool("t1"), kind="workspace")
        assert len(reg) == 1
        assert reg.get("t1").kind == "workspace"

    def test_iter_specs(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"), kind="builtin", provider="builtin")
        reg.register(_make_tool("t2"), kind="web", provider="web")
        specs = list(reg.iter_specs())
        assert len(specs) == 2
        assert specs[0]["name"] == "t1"
        assert specs[0]["kind"] == "builtin"
        assert specs[1]["name"] == "t2"
        assert specs[1]["provider"] == "web"

    def test_build_for_run_no_filters(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"))
        reg.register(_make_tool("t2"))
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        tools = reg.build_for_run(ctx)
        assert len(tools) == 2
        assert [t.name for t in tools] == ["t1", "t2"]

    def test_build_for_run_allowlist(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"))
        reg.register(_make_tool("t2"))
        reg.register(_make_tool("t3"))
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        tools = reg.build_for_run(ctx, allowlist=["t1", "t3"])
        assert [t.name for t in tools] == ["t1", "t3"]

    def test_build_for_run_denylist(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"))
        reg.register(_make_tool("t2"))
        reg.register(_make_tool("t3"))
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        tools = reg.build_for_run(ctx, denylist=["t2"])
        assert [t.name for t in tools] == ["t1", "t3"]

    def test_build_for_run_execution_mode_filter(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"), execution_modes=["autonomous"])
        reg.register(_make_tool("t2"), execution_modes=["supervised"])
        reg.register(_make_tool("t3"))  # no mode restriction

        ctx_auto = ToolContext(run_id="r1", tenant_id="t1", execution_mode="autonomous")
        tools = reg.build_for_run(ctx_auto)
        assert [t.name for t in tools] == ["t1", "t3"]

        ctx_sup = ToolContext(run_id="r1", tenant_id="t1", execution_mode="supervised")
        tools = reg.build_for_run(ctx_sup)
        assert [t.name for t in tools] == ["t2", "t3"]

    def test_build_for_run_workspace_requirement(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"), requires_workspace=True)
        reg.register(_make_tool("t2"), requires_workspace=False)

        ctx_no_ws = ToolContext(run_id="r1", tenant_id="t1")
        tools = reg.build_for_run(ctx_no_ws)
        assert [t.name for t in tools] == ["t2"]

        ctx_ws = ToolContext(run_id="r1", tenant_id="t1", workspace_root="/tmp/ws")
        tools = reg.build_for_run(ctx_ws)
        assert [t.name for t in tools] == ["t1", "t2"]

    def test_build_for_run_governance_risk_budget(self):
        reg = ToolRegistry()
        reg.register(_make_tool("low"), risk_level="low")
        reg.register(_make_tool("med"), risk_level="medium")
        reg.register(_make_tool("high"), risk_level="high")

        ctx = ToolContext(run_id="r1", tenant_id="t1")

        # No budget → all pass
        tools = reg.build_for_run(ctx)
        assert len(tools) == 3

        # Budget = low → only low
        tools = reg.build_for_run(ctx, governance={"max_risk_level": "low"})
        assert [t.name for t in tools] == ["low"]

        # Budget = medium → low + medium
        tools = reg.build_for_run(ctx, governance={"max_risk_level": "medium"})
        assert [t.name for t in tools] == ["low", "med"]

        # Budget = high → all
        tools = reg.build_for_run(ctx, governance={"max_risk_level": "high"})
        assert [t.name for t in tools] == ["low", "med", "high"]

    def test_build_for_run_combined_filters(self):
        reg = ToolRegistry()
        reg.register(_make_tool("t1"), requires_workspace=True, risk_level="low")
        reg.register(_make_tool("t2"), requires_workspace=False, risk_level="high")
        reg.register(_make_tool("t3"), requires_workspace=True, risk_level="high")

        ctx = ToolContext(
            run_id="r1",
            tenant_id="t1",
            workspace_root="/tmp",
        )
        tools = reg.build_for_run(ctx, governance={"max_risk_level": "low"})
        assert [t.name for t in tools] == ["t1"]

    def test_register_factory(self):
        reg = ToolRegistry()
        reg.register(_make_tool("static"))

        def factory():
            return [
                ToolRegistration(tool=_make_tool("dynamic"), kind="dynamic", provider="factory")
            ]

        reg.register_factory(factory)
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        tools = reg.build_for_run(ctx)
        assert "dynamic" in [t.name for t in tools]
        assert "static" in [t.name for t in tools]
