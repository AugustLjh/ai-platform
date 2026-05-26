"""Tests for ai_runtime.tools.caching — ToolResultCache + cached_tool wrapper."""
from __future__ import annotations

import asyncio
import pytest
from typing import Any, Type

from pydantic import BaseModel, Field

from ai_runtime.tools.base import AiPlatformTool, ToolContext
from ai_runtime.tools.caching import (
    DEFAULT_SESSION_SCOPED_TOOL_NAMES,
    ToolResultCache,
    cached_tool,
)


class _Args(BaseModel):
    q: str = Field(default="")


def _make_counting_tool(name: str = "counter"):
    """Tool that increments a counter on every call so we can detect cache hits."""

    counter = {"n": 0}

    class T(AiPlatformTool):
        args_schema: Type[BaseModel] = _Args

        async def _arun(self, q: str = "") -> dict[str, Any]:
            counter["n"] += 1
            return {"q": q, "n": counter["n"]}

    return T(name=name, description="counting tool"), counter


class TestToolResultCache:
    def test_normalize_dict_keys(self):
        cache = ToolResultCache()
        norm = cache._normalize({"b": 1, "a": 2, "c": {"y": 1, "x": 2}})
        # Sorted keys
        assert list(norm.keys()) == ["a", "b", "c"]
        assert list(norm["c"].keys()) == ["x", "y"]

    def test_normalize_strings(self):
        cache = ToolResultCache()
        assert cache._normalize("  hello   world  ") == "hello world"
        assert cache._normalize("hello") == "hello"

    def test_normalize_lists(self):
        cache = ToolResultCache()
        norm = cache._normalize([1, "  x  ", {"b": 1, "a": 2}])
        assert norm == [1, "x", {"a": 2, "b": 1}]

    def test_resolve_scope_session_for_special_names(self):
        cache = ToolResultCache()
        # Session-scoped tool names with a session_id => "session"
        assert cache.resolve_scope(tool_name="knowledge_search", session_id="s1") == "session"
        # Without session_id => "run"
        assert cache.resolve_scope(tool_name="knowledge_search", session_id=None) == "run"
        # Generic tool name => "run"
        assert cache.resolve_scope(tool_name="other_tool", session_id="s1") == "run"

    def test_build_key_session_scope(self):
        cache = ToolResultCache()
        key1 = cache.build_key(
            tool_name="knowledge_search",
            run_id="r1",
            session_id="s1",
            tenant_id="t1",
            arguments={"q": "hello"},
        )
        key2 = cache.build_key(
            tool_name="knowledge_search",
            run_id="r2",  # different run, same session
            session_id="s1",
            tenant_id="t1",
            arguments={"q": "hello"},
        )
        assert key1 == key2, "session-scoped keys should ignore run_id"

    def test_build_key_run_scope(self):
        cache = ToolResultCache()
        key1 = cache.build_key(
            tool_name="other_tool",
            run_id="r1",
            session_id="s1",
            tenant_id="t1",
            arguments={"q": "hello"},
        )
        key2 = cache.build_key(
            tool_name="other_tool",
            run_id="r2",
            session_id="s1",
            tenant_id="t1",
            arguments={"q": "hello"},
        )
        assert key1 != key2, "run-scoped keys should differ across runs"

    def test_build_key_normalizes_args(self):
        cache = ToolResultCache()
        k1 = cache.build_key(
            tool_name="t", run_id="r", arguments={"b": 1, "a": "hello   world"}
        )
        k2 = cache.build_key(
            tool_name="t", run_id="r", arguments={"a": "hello world", "b": 1}
        )
        assert k1 == k2

    @pytest.mark.asyncio
    async def test_get_or_compute_miss_then_hit(self):
        cache = ToolResultCache(max_entries=4)
        calls = {"n": 0}

        async def compute():
            calls["n"] += 1
            return {"val": calls["n"]}

        val1, hit1 = await cache.get_or_compute("k1", compute)
        assert hit1 is False
        assert val1 == {"val": 1}

        val2, hit2 = await cache.get_or_compute("k1", compute)
        assert hit2 is True
        assert val2 == {"val": 1}
        assert calls["n"] == 1, "compute should only run once"

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        cache = ToolResultCache(max_entries=2)

        async def make_compute(v):
            async def _c():
                return v
            return _c

        await cache.get_or_compute("a", await make_compute("A"))
        await cache.get_or_compute("b", await make_compute("B"))
        # Cache full at 2 entries
        assert len(cache) == 2

        # Adding third evicts oldest (a)
        await cache.get_or_compute("c", await make_compute("C"))
        assert len(cache) == 2

        # Verify "a" was evicted by recomputing
        calls = {"n": 0}

        async def recompute_a():
            calls["n"] += 1
            return "A2"

        v, hit = await cache.get_or_compute("a", recompute_a)
        assert hit is False
        assert v == "A2"
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_lru_promotes_on_access(self):
        cache = ToolResultCache(max_entries=2)

        async def make_compute(v):
            async def _c():
                return v
            return _c

        await cache.get_or_compute("a", await make_compute("A"))
        await cache.get_or_compute("b", await make_compute("B"))

        # Access "a" so it becomes most-recently-used. Order: [b, a]
        await cache.get_or_compute("a", await make_compute("ignored"))

        # Add "c" — should evict "b" (least recently used), not "a"
        await cache.get_or_compute("c", await make_compute("C"))

        # "b" was evicted -> compute again returns new value
        async def fresh_b():
            return "B2"

        val, hit = await cache.get_or_compute("b", fresh_b)
        assert hit is False
        assert val == "B2"


class TestCachedToolWrapper:
    @pytest.mark.asyncio
    async def test_cache_hits_for_same_args_same_run(self):
        tool, counter = _make_counting_tool()
        cache = ToolResultCache(max_entries=10)
        wrapped = cached_tool(tool, cache)

        ctx = ToolContext(run_id="r1", tenant_id="t1")
        with ctx.bind():
            r1 = await wrapped.ainvoke({"q": "hello"})
            r2 = await wrapped.ainvoke({"q": "hello"})

        assert r1 == r2
        assert counter["n"] == 1, "inner tool should only run once"

    @pytest.mark.asyncio
    async def test_cache_misses_for_different_args(self):
        tool, counter = _make_counting_tool()
        cache = ToolResultCache(max_entries=10)
        wrapped = cached_tool(tool, cache)

        ctx = ToolContext(run_id="r1", tenant_id="t1")
        with ctx.bind():
            await wrapped.ainvoke({"q": "a"})
            await wrapped.ainvoke({"q": "b"})

        assert counter["n"] == 2

    @pytest.mark.asyncio
    async def test_per_run_scoping(self):
        tool, counter = _make_counting_tool()
        cache = ToolResultCache(max_entries=10)
        wrapped = cached_tool(tool, cache)

        ctx1 = ToolContext(run_id="r1", tenant_id="t1")
        ctx2 = ToolContext(run_id="r2", tenant_id="t1")

        with ctx1.bind():
            await wrapped.ainvoke({"q": "hello"})
        with ctx2.bind():
            await wrapped.ainvoke({"q": "hello"})

        # Different run_ids → separate cache entries
        assert counter["n"] == 2

    @pytest.mark.asyncio
    async def test_session_scoping_for_special_tool(self):
        # Use a name that triggers session scoping.
        tool, counter = _make_counting_tool(name="knowledge_search")
        cache = ToolResultCache(max_entries=10)
        wrapped = cached_tool(tool, cache)

        ctx1 = ToolContext(run_id="r1", tenant_id="t1", session_id="s1")
        ctx2 = ToolContext(run_id="r2", tenant_id="t1", session_id="s1")

        with ctx1.bind():
            await wrapped.ainvoke({"q": "hello"})
        with ctx2.bind():
            await wrapped.ainvoke({"q": "hello"})

        # Same session_id, name is session-scoped → cache hit despite different run_id
        assert counter["n"] == 1

    def test_cached_tool_returns_same_tool_if_no_cache(self):
        tool, _ = _make_counting_tool()
        assert cached_tool(tool, None) is tool

    def test_cached_tool_avoids_double_wrapping(self):
        tool, _ = _make_counting_tool()
        cache = ToolResultCache()
        once = cached_tool(tool, cache)
        twice = cached_tool(once, cache)
        assert once is twice

    def test_session_scoped_names_match_legacy(self):
        # Smoke check that the constant matches the legacy whitelist.
        assert "knowledge_search" in DEFAULT_SESSION_SCOPED_TOOL_NAMES
        assert "workspace_read_file" in DEFAULT_SESSION_SCOPED_TOOL_NAMES
        assert "git_status" in DEFAULT_SESSION_SCOPED_TOOL_NAMES
