"""Artifact and result contracts.

Decomposed from the legacy 3364-line ``ai_runtime.core.agent_runtime.result_contract``
module. The implementation lives in private submodules:

  * ``_constants`` — detection key tables and type-priority maps
  * ``_impl``      — normalizers, type detection, artifact builders, public API

The 4 public functions are re-exported here. The legacy module is preserved
as a backwards-compatibility shim during the LangChain/LangGraph rewrite.
"""
from ._impl import (
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
