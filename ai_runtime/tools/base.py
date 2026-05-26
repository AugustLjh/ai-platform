"""Base classes for the LangChain-native tools layer.

This module provides:

- ``ToolContext``: a Pydantic model carrying per-run authorization, governance,
  and workspace data that tool implementations can inspect.
- ``current_tool_context()`` / ``_TOOL_CONTEXT_VAR``: a ``ContextVar``-based
  lookup so that ``BaseTool`` subclasses (whose ``_run`` / ``_arun`` signatures
  are dictated by LangChain) can pull the active context without having to
  thread it through their argument schemas.
- ``AiPlatformTool``: a ``langchain_core.tools.BaseTool`` subclass that adds the
  ``result_schema`` class attribute and a thin async-by-default execution
  surface (``_arun_with_context``) so concrete tools can focus on business
  logic.

The legacy tool layer in ``ai_runtime/core/agent_runtime/tools/base.py``
preserved its own ``ToolContext`` dataclass; we intentionally keep the field
names compatible so that the ``from_legacy`` adapter can construct a legacy
``ToolContext`` from this Pydantic one without translation.
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar, Token
from typing import Any, ClassVar, Iterator, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field


__all__ = [
    "ToolContext",
    "AiPlatformTool",
    "current_tool_context",
    "current_tool_context_optional",
    "_TOOL_CONTEXT_VAR",
]


# Module-level ContextVar so that any tool implementation invoked inside the
# ``ToolContext.bind()`` block can recover the active context.
_TOOL_CONTEXT_VAR: ContextVar[Optional["ToolContext"]] = ContextVar(
    "ai_runtime_tool_context", default=None
)


class ToolContext(BaseModel):
    """Per-invocation context shared by every tool in a run.

    The fields mirror the legacy ``ai_runtime.core.agent_runtime.tools.base.ToolContext``
    dataclass so that adapters can hop between the two without translation; in
    addition we add ``execution_mode``, ``governance``, ``request_id`` to fit
    the LangGraph/LangChain rewrite.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    run_id: str
    tenant_id: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    agent_definition_id: Optional[str] = None
    step_id: Optional[str] = None

    workspace_root: Optional[str] = None
    execution_mode: str = "autonomous"
    governance: dict[str, Any] = Field(default_factory=dict)

    allowed_knowledge_base_ids: tuple[str, ...] = ()
    allowed_mcp_server_ids: tuple[str, ...] = ()
    allowed_mcp_tool_names: tuple[str, ...] = ()

    # Free-form metadata for graph nodes / cache wrappers / observability.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @contextlib.contextmanager
    def bind(self) -> Iterator["ToolContext"]:
        """Bind this context as the current ``ContextVar`` value.

        Usage::

            with tool_context.bind():
                result = await tool.ainvoke({...})

        Resets the previous value on exit so nested binds compose cleanly.
        """
        token: Token = _TOOL_CONTEXT_VAR.set(self)
        try:
            yield self
        finally:
            _TOOL_CONTEXT_VAR.reset(token)

    def to_legacy_context(self):
        """Return a legacy ``ToolContext`` dataclass equivalent if available.

        We import lazily so importing this module does not require the legacy
        ``core/agent_runtime/`` tree to be present (P3 must be runnable in
        isolation; legacy code is only consulted when the from_legacy adapter
        is actually used).
        """
        try:
            from ai_runtime.core.agent_runtime.tools.base import (  # type: ignore
                ToolContext as LegacyToolContext,
            )
        except ImportError:  # pragma: no cover - legacy may not be installed
            return None

        return LegacyToolContext(
            run_id=self.run_id,
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            user_id=self.user_id,
            agent_definition_id=self.agent_definition_id,
            step_id=self.step_id,
            allowed_knowledge_base_ids=tuple(self.allowed_knowledge_base_ids),
            allowed_mcp_server_ids=tuple(self.allowed_mcp_server_ids),
            allowed_mcp_tool_names=tuple(self.allowed_mcp_tool_names),
            workspace_root=self.workspace_root,
            tool_result_cache=self.metadata.get("tool_result_cache"),
        )


def current_tool_context() -> ToolContext:
    """Return the active :class:`ToolContext` or raise ``LookupError``."""

    ctx = _TOOL_CONTEXT_VAR.get()
    if ctx is None:
        raise LookupError(
            "No ToolContext bound; call tool inside ToolContext.bind()"
        )
    return ctx


def current_tool_context_optional() -> Optional[ToolContext]:
    """Return the active :class:`ToolContext` or ``None`` if unset."""

    return _TOOL_CONTEXT_VAR.get()


class AiPlatformTool(BaseTool):
    """Base class for all ai_runtime tools.

    Concrete subclasses define ``name``, ``description``, ``args_schema``,
    optionally ``result_schema``, and override either ``_arun`` (preferred) or
    ``_run``. The implementation can call :func:`current_tool_context` to
    access the active per-run context.
    """

    # Optional Pydantic model class describing the structured result. Useful
    # for documentation, validation, and downstream artifact builders. The
    # ContextVar is the canonical source of run scoping; this attribute is
    # purely descriptive.
    result_schema: ClassVar[Optional[Type[BaseModel]]] = None

    # ``BaseTool`` defaults to "content" (string-or-bytes). ai_runtime tools
    # typically return JSON-serialisable dicts; LangChain accepts that under
    # ``response_format='content'`` and will auto-stringify when the model
    # consumes the result. Subclasses can flip to ``'content_and_artifact'``
    # if they want to expose a raw structured payload alongside text.
    response_format: str = "content"

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        # Most ai_runtime tools are async; provide a default that bridges to
        # the async path by raising. Subclasses that want sync execution can
        # override.
        raise NotImplementedError(
            f"{type(self).__name__} does not support synchronous execution; "
            "use ainvoke()/invoke() with an async-capable runner."
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        # By convention, AiPlatformTool subclasses override ``_arun`` directly.
        raise NotImplementedError(
            f"{type(self).__name__} must override _arun()"
        )
