"""Adapter that wraps legacy ``BaseTool`` (from
``ai_runtime.core.agent_runtime.tools.base``) instances or compatible callables
as LangChain :class:`AiPlatformTool` subclasses.

The legacy interface is::

    class LegacyBaseTool:
        spec: ToolSpec  # name, description, input_schema dict, kind, metadata
        async def execute(
            self,
            context: LegacyToolContext,
            arguments: dict[str, Any],
        ) -> dict[str, Any]: ...

This module converts that surface into a :class:`AiPlatformTool` that LangChain
agents can call directly. The adapter:

1. Generates a Pydantic ``args_schema`` from the legacy ``input_schema`` JSON
   schema dict (best-effort; complex schemas fall back to a permissive model).
2. Pulls the active :class:`ToolContext` from the ContextVar and converts it
   to a legacy ``ToolContext`` dataclass when invoking ``legacy.execute(...)``.
3. Preserves the legacy ``spec.metadata`` on the wrapped tool so the
   registry/planner sees the same provider / capability / risk-level data.

Either a legacy tool **instance** (with ``.execute`` + ``.spec``) or a raw
callable ``(ctx, args) -> Awaitable[dict]`` + explicit :class:`LegacyToolSpec`
can be passed in.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from ai_runtime.tools.base import AiPlatformTool, ToolContext, current_tool_context_optional


__all__ = [
    "legacy_to_base_tool",
    "LegacyCallable",
]


logger = logging.getLogger(__name__)


# The legacy tool's ``execute`` signature, or any callable matching it.
LegacyCallable = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]


# Map JSON-schema primitive types to Python types for Pydantic field generation.
_JSON_TYPE_TO_PY: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _python_type_from_schema(prop_schema: dict[str, Any]) -> Any:
    """Best-effort conversion of one JSON-schema property to a Python type."""
    if not isinstance(prop_schema, dict):
        return Any
    json_type = prop_schema.get("type")
    if isinstance(json_type, list):
        # union types -> pick the first non-null
        for entry in json_type:
            if entry != "null":
                json_type = entry
                break
    if isinstance(json_type, str):
        return _JSON_TYPE_TO_PY.get(json_type, Any)
    return Any


def _args_schema_from_legacy(
    name: str, input_schema: Optional[dict[str, Any]]
) -> Type[BaseModel]:
    """Synthesise a Pydantic ``BaseModel`` describing the legacy input schema.

    For any non-trivial schema we keep the model permissive (extra='allow')
    so the legacy tool retains full control over argument validation.
    """
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in (name or "Tool"))
    model_name = f"LegacyArgs_{safe_name}"

    properties: dict[str, Any] = {}
    required: list[str] = []
    if isinstance(input_schema, dict):
        raw_props = input_schema.get("properties") or {}
        if isinstance(raw_props, dict):
            properties = raw_props
        raw_required = input_schema.get("required") or []
        if isinstance(raw_required, (list, tuple)):
            required = [str(item) for item in raw_required]

    fields: dict[str, tuple[Any, Any]] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _python_type_from_schema(prop_schema if isinstance(prop_schema, dict) else {})
        description = ""
        if isinstance(prop_schema, dict):
            description = str(prop_schema.get("description") or "")
        # Optional fields default to None unless required.
        if prop_name in required:
            default = ...  # required
            annotation = py_type
        else:
            default = None
            annotation = Optional[py_type]  # type: ignore[valid-type]
        fields[str(prop_name)] = (
            annotation,
            Field(default=default, description=description),
        )

    if not fields:
        # Permissive empty model — accepts anything via ``extra='allow'``.
        return create_model(
            model_name,
            __config__=ConfigDict(extra="allow", arbitrary_types_allowed=True),
        )

    return create_model(
        model_name,
        __config__=ConfigDict(extra="allow", arbitrary_types_allowed=True),
        **fields,
    )


class _LegacyAdapterTool(AiPlatformTool):
    """Concrete adapter class. Each call constructs and dispatches to the
    underlying legacy tool's ``execute`` method.
    """

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    # ``BaseTool.args_schema`` is declared as a class attribute on subclasses;
    # we attach the synthesized model at instance construction.
    legacy_executor: LegacyCallable
    legacy_metadata: dict[str, Any]

    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_schema: Type[BaseModel],
        legacy_executor: LegacyCallable,
        legacy_metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            args_schema=args_schema,
            response_format="content",
            tags=list(tags or []),
            legacy_executor=legacy_executor,
            legacy_metadata=dict(legacy_metadata or {}),
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        # LangChain may pass a single dict positional or kwargs; coerce both.
        payload: dict[str, Any] = {}
        if args:
            if len(args) == 1 and isinstance(args[0], dict):
                payload.update(args[0])
            else:
                payload["_positional"] = list(args)
        payload.update(kwargs)

        ctx_pydantic = current_tool_context_optional()
        if ctx_pydantic is None:
            # No bound context — manufacture a minimal one so the legacy tool
            # at least sees a defined object. Most legacy tools tolerate this
            # because the dataclass has default-None fields.
            ctx_pydantic = ToolContext(run_id="_no_run", tenant_id="_no_tenant")

        legacy_ctx = ctx_pydantic.to_legacy_context()
        if legacy_ctx is None:
            # Legacy module unavailable; pass the pydantic context directly —
            # the executor must handle both shapes if it wants this support.
            legacy_ctx = ctx_pydantic

        result = self.legacy_executor(legacy_ctx, payload)
        if inspect.isawaitable(result):
            result = await result
        return result


def legacy_to_base_tool(
    legacy_callable_or_tool: Union[Any, LegacyCallable],
    spec: Any = None,
    *,
    kind: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AiPlatformTool:
    """Wrap a legacy tool or callable as a LangChain :class:`AiPlatformTool`.

    Args:
        legacy_callable_or_tool: Either a legacy tool **instance** with both
            ``.spec`` and ``.execute`` attributes, or a raw async callable.
        spec: When passing a raw callable, this must be supplied — anything
            exposing ``.name``, ``.description``, ``.input_schema``, optional
            ``.kind`` / ``.metadata``. When passing a legacy tool instance,
            this argument is ignored (the tool's own ``.spec`` is used).
        kind: Optional override for the resulting tool's kind metadata.
        metadata: Optional extra metadata to merge into ``legacy_metadata``.

    Returns:
        A new :class:`AiPlatformTool` that, when invoked, forwards to the
        legacy executor with the active :class:`ToolContext` translated into
        the legacy dataclass.
    """
    # Discover spec & executor from either form.
    if hasattr(legacy_callable_or_tool, "execute") and hasattr(legacy_callable_or_tool, "spec"):
        legacy_tool = legacy_callable_or_tool
        legacy_spec = legacy_tool.spec
        executor: LegacyCallable = legacy_tool.execute  # bound method
    else:
        if spec is None:
            raise ValueError(
                "legacy_to_base_tool: spec must be provided when wrapping a raw callable"
            )
        legacy_spec = spec
        executor = legacy_callable_or_tool

    name = str(getattr(legacy_spec, "name", "") or "").strip()
    description = str(getattr(legacy_spec, "description", "") or "").strip()
    input_schema = getattr(legacy_spec, "input_schema", None) or {}
    spec_metadata: dict[str, Any] = dict(getattr(legacy_spec, "metadata", None) or {})
    spec_kind = str(getattr(legacy_spec, "kind", "builtin") or "builtin")

    if not name:
        raise ValueError("legacy_to_base_tool: legacy spec missing 'name'")
    if not description:
        description = name

    merged_metadata = {
        "legacy_kind": spec_kind,
        "legacy_input_schema": dict(input_schema) if isinstance(input_schema, dict) else {},
        **spec_metadata,
        **(metadata or {}),
    }
    if kind is not None:
        merged_metadata["kind"] = kind

    args_schema = _args_schema_from_legacy(
        name=name,
        input_schema=input_schema if isinstance(input_schema, dict) else None,
    )

    return _LegacyAdapterTool(
        name=name,
        description=description,
        args_schema=args_schema,
        legacy_executor=executor,
        legacy_metadata=merged_metadata,
    )
