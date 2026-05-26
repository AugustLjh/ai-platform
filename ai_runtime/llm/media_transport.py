"""Per-provider media transport selection Runnable.

Ports ``_materialize_request_user_parts_for_candidate`` (and helpers) from
``ai_runtime.core.chat.service``. Given a list of ``ContentPart`` (possibly
attachment-only stubs) plus an upload bundle context, the runnable rewrites
each part using the candidate model's preferred media transport:

    file_id -> url -> base64 -> text

The transport priority is read from
``model_config["adapter_options"]["media_transport"]`` (with
``media_transport_by_type`` for per-modality overrides). Falling back to
the adapter spec's ``default_media_transport`` when nothing is configured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

try:
    from langchain_core.runnables import Runnable, RunnableConfig, RunnableSerializable
except ImportError:  # pragma: no cover
    Runnable = object  # type: ignore[assignment,misc]
    RunnableConfig = dict  # type: ignore[assignment,misc]
    RunnableSerializable = object  # type: ignore[assignment,misc]

from ai_runtime.llm.adapters import ProviderAdapterSpec, get_adapter_spec, get_adapter_spec_for_protocol


VALID_TRANSPORTS = ("file_id", "url", "base64", "text")


@dataclass(frozen=True)
class TransportPlan:
    """Per-modality transport priority resolved for a candidate."""

    default: tuple[str, ...]
    by_type: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def for_kind(self, kind: str) -> tuple[str, ...]:
        return self.by_type.get(str(kind or "").lower(), self.default)


def _normalize_transport(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [part.strip().lower() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [str(item or "").strip().lower() for item in value]
    else:
        items = []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        if item not in VALID_TRANSPORTS or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def resolve_transport_plan(
    *,
    model_config: dict[str, Any] | None,
    provider: str | None = None,
    endpoint_protocol: str | None = None,
) -> TransportPlan:
    """Compute the transport plan for a candidate.

    Looks at ``model_config["adapter_options"]`` first; falls back to the
    adapter spec for ``(provider, endpoint_protocol)``; ultimate default is
    ``("file_id", "url", "base64", "text")``.
    """

    options: dict[str, Any] = {}
    if isinstance(model_config, dict):
        raw = model_config.get("adapter_options")
        if isinstance(raw, dict):
            options = raw

    default = _normalize_transport(options.get("media_transport"))
    by_type_raw = options.get("media_transport_by_type")
    by_type: dict[str, tuple[str, ...]] = {}
    if isinstance(by_type_raw, dict):
        for kind, value in by_type_raw.items():
            normalized = _normalize_transport(value)
            if normalized:
                by_type[str(kind or "").strip().lower()] = normalized

    if not default:
        spec = get_adapter_spec(provider, endpoint_protocol) or get_adapter_spec_for_protocol(endpoint_protocol)
        if spec is not None:
            default = tuple(spec.default_media_transport)

    if not default:
        default = VALID_TRANSPORTS

    return TransportPlan(default=default, by_type=by_type)


def _attachment_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _materialize_part(
    part: dict[str, Any],
    *,
    sources: dict[str, dict[str, Any]],
    plan: TransportPlan,
) -> dict[str, Any]:
    if not isinstance(part, dict):
        return part
    attachment_id = str(part.get("attachment_id") or part.get("file_id") or "").strip()
    if not attachment_id:
        return part
    source = sources.get(attachment_id)
    if not source:
        return part
    media_kind = str(source.get("media_kind") or part.get("type") or "file").lower()
    transport_priority = plan.for_kind(media_kind)
    metadata = _attachment_metadata(source)
    base_data = {
        "size_bytes": source.get("size_bytes"),
        "sha256": source.get("sha256") or metadata.get("sha256"),
        "extension": source.get("extension") or metadata.get("extension"),
        "transport": dict(source.get("transport") or metadata.get("transport") or {}),
        "metadata": metadata,
    }
    chosen: dict[str, Any] | None = None
    for transport in transport_priority:
        if transport == "text" and str(
            source.get("content") or source.get("excerpt") or source.get("preview_text") or ""
        ).strip():
            chosen = {
                "type": "file",
                "attachment_id": attachment_id,
                "file_id": attachment_id,
                "file_name": source.get("name"),
                "text": source.get("content") or source.get("excerpt") or source.get("preview_text"),
                "mime_type": source.get("mime_type") or source.get("content_type"),
                "data": base_data,
            }
            break
        if transport == "file_id" and attachment_id:
            chosen = {
                "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                "attachment_id": attachment_id,
                "file_id": attachment_id,
                "file_name": source.get("name"),
                "mime_type": source.get("mime_type") or source.get("content_type"),
                "base64": source.get("base64") if media_kind == "image" else None,
                "data": base_data,
            }
            break
        if transport == "base64" and source.get("base64"):
            chosen = {
                "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                "attachment_id": attachment_id,
                "file_id": attachment_id,
                "file_name": source.get("name"),
                "mime_type": source.get("mime_type") or source.get("content_type"),
                "base64": source.get("base64"),
                "data": base_data,
            }
            break
        if transport == "url" and source.get("path"):
            chosen = {
                "type": media_kind if media_kind in {"image", "audio", "video"} else "file",
                "attachment_id": attachment_id,
                "file_id": attachment_id,
                "file_name": source.get("name"),
                "url": source.get("path"),
                "mime_type": source.get("mime_type") or source.get("content_type"),
                "data": base_data,
            }
            break
    return chosen or part


def materialize_parts(
    parts: Sequence[dict[str, Any]] | None,
    *,
    upload_context: dict[str, Any] | None,
    plan: TransportPlan,
) -> list[dict[str, Any]]:
    """Convert ``ContentPart[]`` to per-transport materialized form.

    ``upload_context`` follows the legacy ``UploadContext`` shape:
    ``{"files": [...], "media_parts": [...]}`` keyed by ``id`` /
    ``file_id`` / ``attachment_id``.
    """

    if not parts:
        return []
    if not upload_context:
        return [dict(part) if isinstance(part, dict) else part for part in parts]
    file_map = {
        str(item.get("id") or ""): item
        for item in (upload_context.get("files") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    media_map = {
        str(item.get("file_id") or item.get("attachment_id") or ""): item
        for item in (upload_context.get("media_parts") or [])
        if isinstance(item, dict)
        and str(item.get("file_id") or item.get("attachment_id") or "").strip()
    }
    sources = {**file_map, **media_map}
    return [_materialize_part(part, sources=sources, plan=plan) for part in parts]


class MediaTransportRunnable(RunnableSerializable):  # type: ignore[misc]
    """Pre-invoke transport selection for ``ContentPart`` lists.

    Acts on the Runnable input dict by rewriting ``input["request_user_parts"]``
    in-place (a fresh list returned). When ``bound`` is set, delegates to it
    after rewriting; otherwise just returns the augmented input.
    """

    plan: TransportPlan
    bound: Any = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def for_candidate(
        cls,
        *,
        model_config: dict[str, Any] | None,
        provider: str | None = None,
        endpoint_protocol: str | None = None,
        bound: Any | None = None,
    ) -> "MediaTransportRunnable":
        plan = resolve_transport_plan(
            model_config=model_config,
            provider=provider,
            endpoint_protocol=endpoint_protocol,
        )
        return cls(plan=plan, bound=bound)

    def materialize(
        self,
        parts: Sequence[dict[str, Any]] | None,
        *,
        upload_context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return materialize_parts(parts, upload_context=upload_context, plan=self.plan)

    def _rewrite_input(self, input: Any) -> Any:  # noqa: A002
        if not isinstance(input, dict):
            return input
        parts = input.get("request_user_parts")
        upload_context = input.get("upload_context")
        if parts is None:
            return input
        merged = dict(input)
        merged["request_user_parts"] = self.materialize(parts, upload_context=upload_context)
        return merged

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:  # noqa: A002
        rewritten = self._rewrite_input(input)
        if self.bound is None:
            return rewritten
        return self.bound.invoke(rewritten, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:  # noqa: A002
        rewritten = self._rewrite_input(input)
        if self.bound is None:
            return rewritten
        return await self.bound.ainvoke(rewritten, config=config, **kwargs)


__all__ = [
    "MediaTransportRunnable",
    "TransportPlan",
    "VALID_TRANSPORTS",
    "materialize_parts",
    "resolve_transport_plan",
]
