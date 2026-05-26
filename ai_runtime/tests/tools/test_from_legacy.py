"""Tests for ai_runtime.tools.from_legacy — legacy_to_base_tool adapter."""
from __future__ import annotations

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict

from ai_runtime.tools.base import AiPlatformTool, ToolContext
from ai_runtime.tools.from_legacy import legacy_to_base_tool, _args_schema_from_legacy


# ---- Fake legacy types for testing ----


@dataclass
class FakeToolSpec:
    name: str = "fake_tool"
    description: str = "A fake tool for testing"
    input_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results"},
            "verbose": {"type": "boolean"},
        },
    })
    kind: str = "builtin"
    metadata: Dict[str, Any] = field(default_factory=dict)


class FakeLegacyTool:
    """Mimics the legacy BaseTool interface."""

    def __init__(self, spec: FakeToolSpec | None = None):
        self.spec = spec or FakeToolSpec()
        self.call_log: list[tuple[Any, dict]] = []

    async def execute(self, context: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.call_log.append((context, arguments))
        return {"result": f"searched: {arguments.get('query')}", "top_k": arguments.get("top_k", 5)}


class TestArgsSchemaFromLegacy:
    def test_empty_schema(self):
        model = _args_schema_from_legacy("empty", None)
        # Should accept anything via extra='allow'
        instance = model()
        assert instance is not None

    def test_empty_properties(self):
        model = _args_schema_from_legacy("empty", {"type": "object", "properties": {}})
        instance = model()
        assert instance is not None

    def test_required_field(self):
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "The name"},
            },
        }
        model = _args_schema_from_legacy("test", schema)
        # Required field should be enforced
        with pytest.raises(Exception):
            model()  # missing 'name'
        instance = model(name="hello")
        assert instance.name == "hello"

    def test_optional_field_defaults_to_none(self):
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
        }
        model = _args_schema_from_legacy("test", schema)
        instance = model()
        assert instance.limit is None

    def test_all_json_types(self):
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string"},
                "i": {"type": "integer"},
                "n": {"type": "number"},
                "b": {"type": "boolean"},
                "o": {"type": "object"},
                "a": {"type": "array"},
            },
        }
        model = _args_schema_from_legacy("types", schema)
        instance = model(s="x", i=1, n=1.5, b=True, o={}, a=[])
        assert instance.s == "x"
        assert instance.i == 1

    def test_extra_fields_allowed(self):
        schema = {
            "type": "object",
            "properties": {
                "x": {"type": "string"},
            },
        }
        model = _args_schema_from_legacy("extra", schema)
        instance = model(x="hello", unknown_field="world")
        assert instance.x == "hello"


class TestLegacyToBaseTool:
    def test_wraps_legacy_tool_instance(self):
        legacy = FakeLegacyTool()
        wrapped = legacy_to_base_tool(legacy)
        assert isinstance(wrapped, AiPlatformTool)
        assert wrapped.name == "fake_tool"
        assert wrapped.description == "A fake tool for testing"

    def test_schema_has_required_fields(self):
        legacy = FakeLegacyTool()
        wrapped = legacy_to_base_tool(legacy)
        schema = wrapped.get_input_schema().model_json_schema()
        assert "query" in schema.get("required", [])
        assert "query" in schema["properties"]

    @pytest.mark.asyncio
    async def test_invoke_forwards_to_legacy_execute(self):
        legacy = FakeLegacyTool()
        wrapped = legacy_to_base_tool(legacy)

        ctx = ToolContext(run_id="r1", tenant_id="t1")
        with ctx.bind():
            result = await wrapped.ainvoke({"query": "hello", "top_k": 3})

        assert result == {"result": "searched: hello", "top_k": 3}
        assert len(legacy.call_log) == 1
        call_ctx, call_args = legacy.call_log[0]
        # The args dict will include optional fields with default None added by
        # LangChain's args_schema validation. Just check the keys we passed.
        assert call_args["query"] == "hello"
        assert call_args["top_k"] == 3

    @pytest.mark.asyncio
    async def test_invoke_without_context_uses_fallback(self):
        legacy = FakeLegacyTool()
        wrapped = legacy_to_base_tool(legacy)

        # No context bound — should still work with a fallback context.
        result = await wrapped.ainvoke({"query": "test"})
        assert result["result"] == "searched: test"
        assert len(legacy.call_log) == 1

    def test_wraps_raw_callable_with_spec(self):
        spec = FakeToolSpec(name="raw_callable", description="A raw callable")

        async def my_callable(ctx, args):
            return {"echo": args}

        wrapped = legacy_to_base_tool(my_callable, spec)
        assert wrapped.name == "raw_callable"
        assert wrapped.description == "A raw callable"

    @pytest.mark.asyncio
    async def test_raw_callable_invocation(self):
        spec = FakeToolSpec(name="raw_fn", description="raw")

        async def my_fn(ctx, args):
            return {"got": args.get("query")}

        wrapped = legacy_to_base_tool(my_fn, spec)
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        with ctx.bind():
            result = await wrapped.ainvoke({"query": "world"})
        assert result == {"got": "world"}

    def test_raises_if_callable_without_spec(self):
        async def my_fn(ctx, args):
            return {}

        with pytest.raises(ValueError, match="spec must be provided"):
            legacy_to_base_tool(my_fn)

    def test_raises_if_spec_missing_name(self):
        spec = FakeToolSpec(name="")

        async def my_fn(ctx, args):
            return {}

        with pytest.raises(ValueError, match="missing 'name'"):
            legacy_to_base_tool(my_fn, spec)

    def test_metadata_preserved(self):
        spec = FakeToolSpec(
            name="meta_tool",
            description="test",
            metadata={"provider": "workspace", "risk_level": "high"},
        )

        async def my_fn(ctx, args):
            return {}

        wrapped = legacy_to_base_tool(my_fn, spec)
        assert wrapped.legacy_metadata["provider"] == "workspace"
        assert wrapped.legacy_metadata["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_sync_callable_also_works(self):
        """Test that a sync callable (non-async) is handled correctly."""
        spec = FakeToolSpec(name="sync_fn", description="sync")

        def my_sync_fn(ctx, args):
            return {"sync": True, "q": args.get("query")}

        wrapped = legacy_to_base_tool(my_sync_fn, spec)
        ctx = ToolContext(run_id="r1", tenant_id="t1")
        with ctx.bind():
            result = await wrapped.ainvoke({"query": "sync_test"})
        assert result == {"sync": True, "q": "sync_test"}
