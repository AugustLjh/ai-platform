"""Backwards-compatibility shim. Canonical home is :mod:`ai_runtime.contracts`.

This module is preserved during the LangChain/LangGraph rewrite so that the
remaining legacy callers (orchestrator, runtime, subagent handoff) continue to
import from their original location. Final deletion deferred to P8.
"""
from ai_runtime.contracts import (
    build_artifacts_from_tool_result,
    build_structured_run_result,
    hydrate_legacy_result,
    merge_artifacts,
)

__all__ = [
    "build_artifacts_from_tool_result",
    "build_structured_run_result",
    "hydrate_legacy_result",
    "merge_artifacts",
]
