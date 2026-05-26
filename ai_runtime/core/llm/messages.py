from __future__ import annotations

import base64
import binascii
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, Field, model_validator

from .adapters import (
    ENDPOINT_PROTOCOL_INPUT_MODALITIES,
    SUPPORTED_ENDPOINT_PROTOCOLS,
    endpoint_protocol_input_modalities,
    supports_endpoint_protocol,
)


ContentType = Literal["text", "image", "audio", "video", "file", "tool_result"]
Role = Literal["system", "user", "assistant", "tool"]


class ContentPart(BaseModel):
    type: ContentType
    text: str | None = None
    url: str | None = None
    base64: str | None = None
    mime_type: str | None = None
    file_id: str | None = None
    attachment_id: str | None = None
    file_name: str | None = None
    tool_call_id: str | None = None
    data: Any | None = None

    @model_validator(mode="after")
    def _validate_payload(self) -> "ContentPart":
        if self.type == "text" and self.text is None:
            raise ValueError("text part requires text")
        if self.type == "image" and not any((self.url, self.base64, self.file_id)):
            raise ValueError("image part requires url, base64, or file_id")
        if self.type == "audio" and not any((self.url, self.base64, self.file_id)):
            raise ValueError("audio part requires url, base64, or file_id")
        if self.type == "video" and not any((self.url, self.base64, self.file_id, self.data)):
            raise ValueError("video part requires url, base64, file_id, or data")
        if self.type == "file" and not any((self.url, self.base64, self.file_id, self.text, self.data)):
            raise ValueError("file part requires url, base64, file_id, extracted text, or data")
        return self


class UnifiedMessage(BaseModel):
    role: Role
    content: list[ContentPart] = Field(default_factory=list)


class ModelCapabilityProfile(BaseModel):
    task_type: str = "chat.completion"
    endpoint_protocol: str | None = None
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    default_output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    supported_response_formats: list[str] = Field(default_factory=lambda: ["text"])
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_video_input: bool = False
    supports_file_input: bool = False
    adapter_options: dict[str, Any] = Field(default_factory=dict)


class ModelRequestProfile(BaseModel):
    task_type: str = "chat.completion"
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    response_format: str = "text"
    endpoint_protocol: str | None = None


class UnifiedModelRequest(BaseModel):
    messages: list[UnifiedMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any | None = None
    response_format: Any | None = None
    reasoning: dict[str, Any] | None = None
    media_transport: list[str] | dict[str, list[str]] | str | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        if payload.get("max_output_tokens") is None and payload.get("max_tokens") is not None:
            payload["max_output_tokens"] = payload.pop("max_tokens")
        return payload

    @model_validator(mode="after")
    def _normalize_messages(self) -> "UnifiedModelRequest":
        self.messages = normalize_messages(self.messages)
        return self

    @classmethod
    def from_messages(
        cls,
        messages: Sequence[UnifiedMessage | dict[str, Any] | Any],
        **kwargs: Any,
    ) -> "UnifiedModelRequest":
        if "max_output_tokens" not in kwargs and "max_tokens" in kwargs:
            kwargs = dict(kwargs)
            kwargs["max_output_tokens"] = kwargs.pop("max_tokens")
        known_fields = set(cls.model_fields)
        payload = {key: value for key, value in kwargs.items() if key in known_fields}
        extra_params = dict(payload.pop("extra_params", {}) or {})
        for key, value in kwargs.items():
            if key not in known_fields:
                extra_params[key] = value
        payload["extra_params"] = extra_params
        return cls(messages=normalize_messages(messages), **payload)

    def canonical_params(self) -> dict[str, Any]:
        params = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "top_p": self.top_p,
            "tools": self.tools,
            "tool_choice": self.tool_choice,
            "response_format": self.response_format,
            "reasoning": self.reasoning,
            "media_transport": self.media_transport,
        }
        return {key: value for key, value in params.items() if value is not None}


def _normalize_modality_list(value: Any, fallback: Sequence[str]) -> list[str]:
    if value is None:
        return list(fallback)
    items: list[Any]
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        items = list(value)
    else:
        items = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized or list(fallback)


def capability_profile_from_settings(
    *sources: ModelCapabilityProfile | dict[str, Any] | None,
    fallback_input_modalities: Sequence[str] = ("text",),
    fallback_output_modalities: Sequence[str] = ("text",),
) -> ModelCapabilityProfile:
    merged = ModelCapabilityProfile(
        input_modalities=list(fallback_input_modalities),
        output_modalities=list(fallback_output_modalities),
    )
    for source in sources:
        if source is None:
            continue
        payload = source.model_dump() if isinstance(source, ModelCapabilityProfile) else dict(source)
        input_modalities = payload.get("input_modalities")
        if input_modalities is not None:
            merged.input_modalities = _normalize_modality_list(input_modalities, merged.input_modalities)
        task_type = str(payload.get("task_type") or "").strip() or None
        if task_type:
            merged.task_type = task_type
        endpoint_protocol = str(payload.get("endpoint_protocol") or "").strip() or None
        if endpoint_protocol:
            merged.endpoint_protocol = endpoint_protocol
        output_modalities = payload.get("output_modalities")
        if output_modalities is not None:
            merged.output_modalities = _normalize_modality_list(output_modalities, merged.output_modalities)
        default_output_modalities = payload.get("default_output_modalities")
        if default_output_modalities is not None:
            merged.default_output_modalities = _normalize_modality_list(
                default_output_modalities,
                merged.default_output_modalities,
            )
        supported_response_formats = payload.get("supported_response_formats")
        if supported_response_formats is not None:
            merged.supported_response_formats = _normalize_modality_list(
                supported_response_formats,
                merged.supported_response_formats,
            )

        for key in (
            "context_window",
            "max_output_tokens",
            "supports_tools",
            "supports_streaming",
            "supports_reasoning",
            "supports_vision",
            "supports_audio_input",
            "supports_audio_output",
            "supports_video_input",
            "supports_file_input",
        ):
            if key not in payload or payload[key] is None:
                continue
            setattr(merged, key, payload[key])
        adapter_options = payload.get("adapter_options")
        if isinstance(adapter_options, dict):
            merged.adapter_options = dict(adapter_options)

    if merged.supports_vision and "image" not in merged.input_modalities:
        merged.input_modalities.append("image")
    if merged.supports_audio_input and "audio" not in merged.input_modalities:
        merged.input_modalities.append("audio")
    if merged.supports_video_input and "video" not in merged.input_modalities:
        merged.input_modalities.append("video")
    if merged.supports_file_input and "file" not in merged.input_modalities:
        merged.input_modalities.append("file")

    merged.supports_vision = merged.supports_vision or ("image" in merged.input_modalities)
    merged.supports_audio_input = merged.supports_audio_input or ("audio" in merged.input_modalities)
    merged.output_modalities = ["text"]
    merged.default_output_modalities = ["text"]
    merged.supports_audio_output = bool(merged.supports_audio_output)
    merged.supports_video_input = merged.supports_video_input or ("video" in merged.input_modalities)
    merged.supports_file_input = merged.supports_file_input or ("file" in merged.input_modalities)
    return merged


def _safe_number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _part_data_dict(part: ContentPart) -> dict[str, Any]:
    return part.data if isinstance(part.data, dict) else {}


def _part_size_bytes(part: ContentPart) -> int | None:
    data = _part_data_dict(part)
    for key in (
        "size_bytes",
        "sizeBytes",
        "bytes",
        "byte_size",
        "byteSize",
        "original_size_bytes",
        "originalSizeBytes",
    ):
        number = _safe_number(data.get(key))
        if number is not None:
            return int(number)
    if not part.base64:
        return None
    encoded = part.base64.split(",", 1)[1] if part.base64.startswith("data:") and "," in part.base64 else part.base64
    try:
        return len(base64.b64decode(encoded, validate=True))
    except (binascii.Error, ValueError):
        return None


def _part_duration_seconds(part: ContentPart) -> float | None:
    data = _part_data_dict(part)
    for key in (
        "duration_seconds",
        "durationSeconds",
        "seconds",
        "duration",
        "duration_ms",
        "durationMs",
    ):
        number = _safe_number(data.get(key))
        if number is not None:
            if key in {"duration_ms", "durationMs"}:
                return number / 1000.0
            return number
    return None


def validate_message_constraints(
    messages: Iterable[UnifiedMessage | dict[str, Any] | Any],
    constraints: dict[str, Any] | None,
) -> list[str]:
    if not constraints:
        return []
    normalized = normalize_messages(list(messages or []))
    media_parts = [part for message in normalized for part in message.content if part.type in {"image", "audio", "video", "file"}]
    errors: list[str] = []

    allowed_mime_types = {
        str(item or "").strip().lower()
        for item in constraints.get("allowed_mime_types", []) or []
        if str(item or "").strip()
    }
    if allowed_mime_types:
        for part in media_parts:
            mime_type = str(part.mime_type or "").strip().lower()
            if mime_type and mime_type not in allowed_mime_types:
                errors.append(f"{part.type} mime_type={mime_type} 不在 allowed_mime_types 中")

    count_limits = {
        "image": "max_images",
        "audio": "max_audio_files",
        "video": "max_videos",
        "file": "max_files",
    }
    for media_type, limit_key in count_limits.items():
        limit = _safe_number(constraints.get(limit_key))
        if limit is None:
            continue
        count = sum(1 for part in media_parts if part.type == media_type)
        if count > int(limit):
            errors.append(f"{media_type} 数量 {count} 超过 {limit_key}={int(limit)}")

    size_limits = {
        "image": "max_image_bytes",
        "audio": "max_audio_bytes",
        "video": "max_video_bytes",
        "file": "max_file_bytes",
    }
    for part in media_parts:
        limit_key = size_limits.get(part.type)
        limit = _safe_number(constraints.get(limit_key))
        size = _part_size_bytes(part)
        if limit is not None and size is not None and size > int(limit):
            errors.append(f"{part.type} 大小 {size} bytes 超过 {limit_key}={int(limit)}")

    duration_limits = {
        "audio": "max_audio_seconds",
        "video": "max_video_seconds",
    }
    for part in media_parts:
        limit_key = duration_limits.get(part.type)
        if not limit_key:
            continue
        limit = _safe_number(constraints.get(limit_key))
        duration = _part_duration_seconds(part)
        if limit is not None and duration is not None and duration > limit:
            errors.append(f"{part.type} 时长 {duration:g}s 超过 {limit_key}={limit:g}s")

    return errors


def build_text_part(text: Any) -> ContentPart:
    return ContentPart(type="text", text="" if text is None else str(text))


def _coerce_role(value: Any) -> Role:
    normalized = str(value or "").strip().lower()
    if normalized not in {"system", "user", "assistant", "tool"}:
        raise ValueError(f"unsupported message role: {value!r}")
    return normalized  # type: ignore[return-value]


def _normalize_part(raw: Any) -> ContentPart:
    if isinstance(raw, ContentPart):
        return raw
    if isinstance(raw, str):
        return build_text_part(raw)
    if isinstance(raw, dict):
        payload = dict(raw)
        part_type = str(payload.get("type") or "").strip().lower() or "text"
        if "image" in payload and "type" not in payload:
            source = payload.get("image")
            payload = {
                "type": "image",
                "url": source if isinstance(source, str) and not str(source).startswith("data:") else None,
                "base64": source if isinstance(source, str) and str(source).startswith("data:") else None,
                "data": None if isinstance(source, str) else source,
                "mime_type": payload.get("mime_type"),
            }
        elif "audio" in payload and "type" not in payload:
            source = payload.get("audio")
            payload = {
                "type": "audio",
                "url": source if isinstance(source, str) and not str(source).startswith("data:") else None,
                "base64": source if isinstance(source, str) and str(source).startswith("data:") else None,
                "data": None if isinstance(source, str) else source,
                "mime_type": payload.get("mime_type"),
            }
        elif "video" in payload and "type" not in payload:
            source = payload.get("video")
            payload = {
                "type": "video",
                "url": source if isinstance(source, str) and not str(source).startswith("data:") else None,
                "base64": source if isinstance(source, str) and str(source).startswith("data:") else None,
                "data": None if isinstance(source, str) else source,
                "mime_type": payload.get("mime_type"),
            }
        elif "text" in payload and "type" not in payload:
            payload = {"type": "text", "text": payload.get("text")}

        part_type = str(payload.get("type") or "").strip().lower() or "text"
        if part_type == "image_url":
            image_url = payload.get("image_url")
            if isinstance(image_url, dict):
                payload = {
                    "type": "image",
                    "url": image_url.get("url"),
                    "mime_type": image_url.get("mime_type"),
                }
        elif part_type == "video_url":
            video_url = payload.get("video_url")
            if isinstance(video_url, dict):
                payload = {
                    "type": "video",
                    "url": video_url.get("url"),
                    "mime_type": video_url.get("mime_type"),
                }
        elif part_type == "input_text":
            payload = {"type": "text", "text": payload.get("text")}
        elif part_type == "input_image":
            payload = {
                "type": "image",
                "url": payload.get("image_url") or payload.get("url"),
                "base64": payload.get("image_base64") or payload.get("base64"),
                "mime_type": payload.get("mime_type"),
            }
        elif part_type == "audio":
            source = payload.get("audio")
            if source is not None:
                payload = {
                    "type": "audio",
                    "url": source if isinstance(source, str) and not str(source).startswith("data:") else payload.get("url"),
                    "base64": source if isinstance(source, str) and str(source).startswith("data:") else payload.get("base64"),
                    "file_id": payload.get("file_id"),
                    "mime_type": payload.get("mime_type"),
                    "file_name": payload.get("file_name"),
                }
        elif part_type == "video":
            source = payload.get("video")
            if source is not None:
                payload = {
                    "type": "video",
                    "url": source if isinstance(source, str) and not str(source).startswith("data:") else payload.get("url"),
                    "base64": source if isinstance(source, str) and str(source).startswith("data:") else payload.get("base64"),
                    "data": None if isinstance(source, str) else source,
                    "file_id": payload.get("file_id"),
                    "mime_type": payload.get("mime_type"),
                    "file_name": payload.get("file_name"),
                }
        return ContentPart.model_validate(payload)
    raise ValueError(f"unsupported content part payload: {type(raw)!r}")


def _normalize_content(raw: Any) -> list[ContentPart]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [_normalize_part(item) for item in raw]
    return [_normalize_part(raw)]


def normalize_message(raw: Any) -> UnifiedMessage:
    if isinstance(raw, UnifiedMessage):
        return raw
    if isinstance(raw, dict):
        content = raw.get("content")
        if not content and raw.get("content_parts") is not None:
            content = raw.get("content_parts")
        return UnifiedMessage(
            role=_coerce_role(raw.get("role")),
            content=_normalize_content(content),
        )
    role = _coerce_role(getattr(raw, "role", None))
    content = _normalize_content(getattr(raw, "content", None))
    if not content:
        legacy_content = getattr(raw, "message", None)
        if legacy_content not in (None, ""):
            content = [build_text_part(legacy_content)]
    if not content:
        content_parts = getattr(raw, "content_parts", None)
        if content_parts is not None:
            content = _normalize_content(content_parts)
    return UnifiedMessage(role=role, content=content)


def normalize_messages(messages: Sequence[Any] | None) -> list[UnifiedMessage]:
    return [normalize_message(item) for item in list(messages or [])]


def message_text_content(message: UnifiedMessage | dict[str, Any] | Any) -> str:
    normalized = normalize_message(message)
    return "".join(part.text or "" for part in normalized.content if part.type == "text")


def required_input_modalities(messages: Iterable[UnifiedMessage | dict[str, Any] | Any]) -> set[str]:
    required: set[str] = set()
    for message in messages:
        normalized = normalize_message(message)
        for part in normalized.content:
            if part.type == "file" and part.text and not any((part.url, part.base64, part.file_id)):
                required.add("text")
                continue
            required.add(part.type)
    return required or {"text"}


def merge_capability_profiles(
    *profiles: ModelCapabilityProfile | dict[str, Any] | None,
) -> ModelCapabilityProfile:
    return capability_profile_from_settings(*profiles)


def build_model_request_profile(
    messages: Iterable[UnifiedMessage | dict[str, Any] | Any],
    *,
    endpoint_protocol: str | None = None,
    response_format: str = "text",
) -> ModelRequestProfile:
    return ModelRequestProfile(
        task_type="chat.completion",
        input_modalities=sorted(required_input_modalities(messages)),
        output_modalities=["text"],
        response_format=response_format,
        endpoint_protocol=endpoint_protocol,
    )


def supports_model_request(
    capability: ModelCapabilityProfile | dict[str, Any] | None,
    request: ModelRequestProfile | dict[str, Any],
) -> bool:
    profile = merge_capability_profiles(capability)
    request_profile = request if isinstance(request, ModelRequestProfile) else ModelRequestProfile.model_validate(request)
    if profile.task_type != request_profile.task_type:
        return False
    if profile.output_modalities != ["text"]:
        return False
    if not set(request_profile.input_modalities or ["text"]).issubset(set(profile.input_modalities or ["text"])):
        return False
    if not set(request_profile.output_modalities or ["text"]).issubset(set(profile.output_modalities or ["text"])):
        return False
    if request_profile.response_format and request_profile.response_format not in set(profile.supported_response_formats or ["text"]):
        return False
    if request_profile.endpoint_protocol and profile.endpoint_protocol and request_profile.endpoint_protocol != profile.endpoint_protocol:
        return False
    profile_protocol = str(profile.endpoint_protocol or "").strip().lower() or None
    if profile_protocol:
        if not supports_endpoint_protocol(profile_protocol):
            return False
        supported_modalities = endpoint_protocol_input_modalities(profile_protocol)
        if supported_modalities is not None and not set(request_profile.input_modalities or ["text"]).issubset(supported_modalities):
            return False
    return True


def supports_modalities(
    capability: ModelCapabilityProfile | dict[str, Any] | None,
    required_modalities: set[str],
) -> bool:
    return supports_model_request(
        capability,
        ModelRequestProfile(input_modalities=sorted(required_modalities), output_modalities=["text"]),
    )
