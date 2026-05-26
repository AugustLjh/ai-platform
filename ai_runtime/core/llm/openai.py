from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from .adapters import (
    ProviderAdapterSpec,
    get_adapter_spec,
    get_adapter_spec_for_protocol,
    normalize_endpoint_protocol,
)
from .base import BaseLLM, LLMResponse
from .messages import (
    ContentPart,
    ModelCapabilityProfile,
    UnifiedMessage,
    UnifiedModelRequest,
    capability_profile_from_settings,
    endpoint_protocol_input_modalities,
)


class OpenAILLM(BaseLLM):
    """OpenAI-compatible LLM implementation with adapter-driven payload mapping."""

    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None, **kwargs):
        api_base = kwargs.pop("api_base", None)
        capabilities = kwargs.pop("capabilities", None)
        self.provider = str(kwargs.pop("provider", "openai") or "openai").strip().lower()
        super().__init__(model, **kwargs)
        self.api_key = api_key
        self.api_base = api_base
        self.capabilities = self._build_capabilities(capabilities)

    def _build_capabilities(self, override: Optional[Dict[str, Any]]) -> ModelCapabilityProfile:
        default = {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_tools": bool(self.config.get("supports_tools", False)),
            "supports_streaming": True,
        }
        declared = {
            key: self.config.get(key)
            for key in (
                "input_modalities",
                "output_modalities",
                "task_type",
                "endpoint_protocol",
                "default_output_modalities",
                "supported_response_formats",
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
                "adapter_options",
            )
            if key in self.config
        }
        return capability_profile_from_settings(default, override, declared)

    @staticmethod
    def _api_request_config(config: Dict[str, Any]) -> Dict[str, Any]:
        internal_keys = {
            "adapter_options",
            "api_base",
            "capabilities",
            "constraints",
            "context_window",
            "default_output_modalities",
            "endpoint_protocol",
            "input_modalities",
            "max_output_tokens",
            "max_tokens",
            "media_transport",
            "output_modalities",
            "provider",
            "reasoning",
            "response_format",
            "supported_response_formats",
            "supports_audio_input",
            "supports_audio_output",
            "supports_file_input",
            "supports_reasoning",
            "supports_streaming",
            "supports_tools",
            "supports_video_input",
            "supports_vision",
            "task_type",
            "temperature",
            "tool_choice",
            "tools",
            "top_p",
        }
        return {key: value for key, value in config.items() if key not in internal_keys and value is not None}

    def _config_canonical_params(self) -> dict[str, Any]:
        params = {
            "temperature": self.config.get("temperature"),
            "max_output_tokens": self.config.get("max_output_tokens", self.config.get("max_tokens")),
            "top_p": self.config.get("top_p"),
            "tools": self.config.get("tools"),
            "tool_choice": self.config.get("tool_choice"),
            "response_format": self.config.get("response_format"),
            "reasoning": self.config.get("reasoning"),
            "media_transport": self.config.get("media_transport"),
        }
        return {key: value for key, value in params.items() if value is not None}

    def _adapter_options(self) -> Dict[str, Any]:
        options = self.config.get("adapter_options")
        return dict(options) if isinstance(options, dict) else {}

    def _adapter_spec(self) -> ProviderAdapterSpec:
        protocol = normalize_endpoint_protocol(self.config.get("endpoint_protocol"))
        spec = get_adapter_spec(self.provider, protocol) or get_adapter_spec_for_protocol(protocol)
        if spec is None or spec.endpoint_family == "local":
            raise RuntimeError(f"endpoint_protocol={protocol} is not implemented by OpenAI-compatible adapter")
        return spec

    def _media_transport_priority(self, part: ContentPart, request: UnifiedModelRequest | None = None) -> list[str]:
        raw = request.media_transport if request and request.media_transport is not None else None
        options = self._adapter_options()
        if raw is None:
            raw = options.get("media_transport")
        transport_by_type = options.get("media_transport_by_type")
        if isinstance(request.media_transport, dict) if request else False:
            scoped = request.media_transport.get(part.type)  # type: ignore[union-attr]
            if scoped is not None:
                raw = scoped
        elif isinstance(transport_by_type, dict):
            scoped = transport_by_type.get(part.type)
            if scoped is not None:
                raw = scoped
        if isinstance(raw, str):
            items = [item.strip().lower() for item in raw.split(",")]
        elif isinstance(raw, Sequence):
            items = [str(item or "").strip().lower() for item in raw]
        else:
            items = []
        normalized = [item for item in items if item in {"url", "base64", "file_id", "text"}]
        return normalized or list(self._adapter_spec().default_media_transport)

    @staticmethod
    def _guess_mime_type(part: ContentPart, default: str) -> str:
        mime_type = str(part.mime_type or "").strip().lower()
        if mime_type:
            return mime_type
        source = str(part.url or part.file_name or "").strip()
        if source:
            guessed, _ = mimetypes.guess_type(source)
            if guessed:
                return guessed
        return default

    @staticmethod
    def _decode_data_uri(value: str) -> tuple[str | None, bytes | None]:
        if not value.startswith("data:") or "," not in value:
            return None, None
        meta, payload = value[5:].split(",", 1)
        mime_type = meta.split(";", 1)[0] or None
        if ";base64" in meta:
            return mime_type, base64.b64decode(payload)
        return mime_type, payload.encode("utf-8")

    @staticmethod
    def _filename_for_part(part: ContentPart, default_name: str) -> str:
        filename = str(part.file_name or part.url or default_name).strip() or default_name
        return Path(filename).name

    @staticmethod
    def _base64_encode(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    @classmethod
    def _extract_binary_payload(
        cls,
        part: ContentPart,
        *,
        default_mime_type: str,
    ) -> tuple[bytes | None, str | None]:
        source = str(part.url or "").strip()
        if source.startswith("data:"):
            decoded_mime, raw = cls._decode_data_uri(source)
            if raw is None:
                raise RuntimeError(f"openai.responses adapter could not decode data URI for {part.type} part")
            mime_type = decoded_mime or cls._guess_mime_type(part, default_mime_type)
            return raw, mime_type
        if source.startswith("file://"):
            source = source[7:]
        if source and not source.startswith(("http://", "https://")):
            path = Path(source).expanduser()
            if path.exists() and path.is_file():
                return path.read_bytes(), cls._guess_mime_type(part, default_mime_type)
        if part.base64:
            raw_source = part.base64.strip()
            decoded_mime, raw = cls._decode_data_uri(raw_source)
            if raw is None:
                try:
                    raw = base64.b64decode(raw_source, validate=True)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"openai.responses adapter could not decode base64 {part.type} part") from exc
            mime_type = decoded_mime or cls._guess_mime_type(part, default_mime_type)
            return raw, mime_type
        if part.data is not None:
            if isinstance(part.data, bytes):
                return part.data, cls._guess_mime_type(part, default_mime_type)
            if isinstance(part.data, str):
                raw = part.data.encode("utf-8")
                return raw, cls._guess_mime_type(part, default_mime_type)
            if isinstance(part.data, dict):
                encoded = part.data.get("base64") or part.data.get("data") or part.data.get("content")
                if isinstance(encoded, str):
                    try:
                        raw = base64.b64decode(encoded, validate=True)
                    except Exception as exc:  # noqa: BLE001
                        raise RuntimeError(f"openai.responses adapter could not decode {part.type} data payload") from exc
                    mime_type = (
                        str(part.data.get("mime_type") or part.data.get("mimeType") or "").strip().lower()
                        or cls._guess_mime_type(part, default_mime_type)
                    )
                    return raw, mime_type
            raise RuntimeError(f"openai.responses adapter requires raw data or base64 for {part.type} parts")
        return None, None

    @classmethod
    def _to_input_file_part(cls, part: ContentPart, *, default_name: str, default_mime_type: str) -> Dict[str, Any]:
        filename = cls._filename_for_part(part, default_name)
        mime_type = cls._guess_mime_type(part, default_mime_type)
        payload: Dict[str, Any] = {"type": "input_file"}
        if part.file_id:
            payload["file_id"] = part.file_id
        source = str(part.url or "").strip()
        if source.startswith("file://"):
            source = source[7:]
        if source.startswith(("http://", "https://")):
            payload["file_url"] = source
        else:
            raw, extracted_mime = cls._extract_binary_payload(part, default_mime_type=default_mime_type)
            if raw is not None:
                payload["file_data"] = cls._base64_encode(raw)
            elif part.file_id:
                payload["file_id"] = part.file_id
            else:
                raise RuntimeError(f"openai.responses adapter requires url, base64, file_id, or data for {part.type} parts")
            if extracted_mime:
                mime_type = extracted_mime
        if filename:
            payload["filename"] = filename
        if mime_type:
            payload["mime_type"] = mime_type
        return payload

    def _to_transport_aware_file_part(
        self,
        part: ContentPart,
        request: UnifiedModelRequest,
        *,
        default_name: str,
        default_mime_type: str,
    ) -> Dict[str, Any]:
        filename = self._filename_for_part(part, default_name)
        mime_type = self._guess_mime_type(part, default_mime_type)
        source = str(part.url or "").strip()
        url_source = source or None
        if source.startswith("file://"):
            url_source = None
        if url_source and not url_source.startswith(("http://", "https://")) and not url_source.startswith("data:"):
            url_source = None
        raw, extracted_mime = self._extract_binary_payload(part, default_mime_type=default_mime_type)
        if extracted_mime:
            mime_type = extracted_mime
        payload: Dict[str, Any] = {"type": "input_file"}
        selected_transport: str | None = None
        for transport in self._media_transport_priority(part, request):
            if transport == "file_id" and part.file_id:
                selected_transport = transport
                if part.type == "image":
                    payload = {"type": "input_image", "detail": "auto", "file_id": part.file_id}
                else:
                    payload["file_id"] = part.file_id
                break
            if transport == "url" and url_source:
                selected_transport = transport
                field_name = "file_url"
                if part.type == "image":
                    field_name = "image_url"
                    payload["type"] = "input_image"
                    payload["detail"] = "auto"
                payload[field_name] = url_source
                break
            if transport == "base64" and raw is not None:
                selected_transport = transport
                if part.type == "image":
                    payload = {
                        "type": "input_image",
                        "detail": "auto",
                        "image_url": f"data:{mime_type};base64,{self._base64_encode(raw)}",
                    }
                else:
                    payload["file_data"] = self._base64_encode(raw)
                break
            if transport == "text" and part.type == "file" and part.text:
                request.metadata.setdefault("media_transports", []).append({"type": part.type, "transport": "text"})
                return {"type": "input_text", "text": part.text}
        else:
            payload = self._to_input_file_part(
                part,
                default_name=default_name,
                default_mime_type=default_mime_type,
            )
            selected_transport = "fallback"
        if filename and payload.get("type") == "input_file":
            payload["filename"] = filename
        if mime_type and payload.get("type") == "input_file":
            payload["mime_type"] = mime_type
        request.metadata.setdefault("media_transports", []).append(
            {"type": part.type, "transport": selected_transport or "unknown"}
        )
        return payload

    @classmethod
    def _to_input_audio_part(cls, part: ContentPart) -> Dict[str, Any]:
        raw, mime_type = cls._extract_binary_payload(part, default_mime_type="audio/mpeg")
        if raw is not None:
            audio_format = cls._audio_format_for_part(part, mime_type)
            if audio_format not in {"mp3", "wav"}:
                raise RuntimeError(f"openai.responses adapter only supports mp3/wav audio, got {audio_format!r}")
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": cls._base64_encode(raw),
                    "format": audio_format,
                },
            }
        return cls._to_input_file_part(
            part,
            default_name=part.file_name or "audio.bin",
            default_mime_type="audio/mpeg",
        )

    @staticmethod
    def _audio_format_for_part(part: ContentPart, mime_type: str | None) -> str:
        normalized_mime = str(mime_type or "").strip().lower()
        filename = str(part.file_name or part.url or "").strip().lower()
        if normalized_mime in {"audio/wav", "audio/x-wav", "audio/wave"} or filename.endswith(".wav"):
            return "wav"
        if normalized_mime in {"audio/mpeg", "audio/mp3", "audio/mpeg3"} or filename.endswith(".mp3"):
            return "mp3"
        if normalized_mime:
            return normalized_mime.split("/", 1)[-1].split(";", 1)[0] or "unknown"
        suffix = Path(filename).suffix.lstrip(".")
        return suffix or "mp3"

    def _to_responses_content_part(self, part: ContentPart, request: UnifiedModelRequest) -> Dict[str, Any]:
        if part.type == "text":
            return {"type": "input_text", "text": part.text or ""}
        if part.type == "image":
            return self._to_transport_aware_file_part(
                part,
                request,
                default_name=part.file_name or "image.bin",
                default_mime_type="image/png",
            )
        if part.type == "audio":
            request.metadata.setdefault("media_transports", []).append({"type": part.type, "transport": "input_audio"})
            return self._to_input_audio_part(part)
        if part.type == "video":
            return self._to_transport_aware_file_part(
                part,
                request,
                default_name=part.file_name or "video.bin",
                default_mime_type="video/mp4",
            )
        if part.type == "file":
            if part.text and not any((part.url, part.base64, part.file_id, part.data)):
                request.metadata.setdefault("media_transports", []).append({"type": part.type, "transport": "text"})
                return {"type": "input_text", "text": part.text}
            return self._to_transport_aware_file_part(
                part,
                request,
                default_name=part.file_name or "file.bin",
                default_mime_type="application/octet-stream",
            )
        if part.type == "tool_result":
            return {"type": "input_text", "text": part.text or str(part.data or "")}
        return {"type": "input_text", "text": part.text or ""}

    def _validate_protocol_support(self, request_or_messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]]) -> ProviderAdapterSpec:
        request = (
            request_or_messages
            if isinstance(request_or_messages, UnifiedModelRequest)
            else UnifiedModelRequest.from_messages(request_or_messages)
        )
        spec = self._adapter_spec()
        supported_modalities = endpoint_protocol_input_modalities(spec.endpoint_protocol)
        if supported_modalities is None:
            raise RuntimeError(f"Unsupported endpoint protocol: {spec.endpoint_protocol}")
        required_modalities = self.required_input_modalities(request.messages)
        unsupported = sorted(set(required_modalities) - set(supported_modalities))
        if unsupported:
            raise RuntimeError(
                f"endpoint_protocol={spec.endpoint_protocol} does not support input modalities: {', '.join(unsupported)}"
            )
        return spec

    def _build_client(self):
        from openai import AsyncOpenAI

        client_kwargs = {"api_key": self.api_key}
        if self.api_base:
            client_kwargs["base_url"] = self.api_base
        return AsyncOpenAI(**client_kwargs)

    @staticmethod
    def _extract_message_content(message) -> str:
        if not message:
            return ""
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                if text:
                    parts.append(text)
            return "".join(parts)
        return str(content) if content else ""

    def _to_openai_content_part(self, part: ContentPart) -> Dict[str, Any]:
        if part.type == "text":
            return {"type": "text", "text": part.text or ""}
        if part.type == "image":
            url = part.url
            if not url and part.base64:
                mime_type = part.mime_type or "image/png"
                url = f"data:{mime_type};base64,{part.base64}"
            return {"type": "image_url", "image_url": {"url": url or ""}}
        if part.type == "audio":
            raise RuntimeError("openai.chat_completions adapter does not support audio parts")
        if part.type == "video":
            raise RuntimeError("openai.chat_completions adapter does not support video parts")
        if part.type == "file":
            raise RuntimeError("openai.chat_completions adapter does not support file parts")
        if part.type == "tool_result":
            return {"type": "text", "text": part.text or str(part.data or "")}
        return {"type": "text", "text": part.text or ""}

    def _coerce_request(
        self,
        messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]],
        **kwargs: Any,
    ) -> UnifiedModelRequest:
        if isinstance(messages, UnifiedModelRequest):
            if kwargs:
                merged = {**messages.model_dump(), **kwargs}
                merged["messages"] = messages.messages
                return UnifiedModelRequest.model_validate(merged)
            return messages
        return UnifiedModelRequest.from_messages(messages, **kwargs)

    def prepare_messages(self, messages: Sequence[UnifiedMessage | Dict[str, Any]]) -> List[Dict[str, Any]]:
        request = UnifiedModelRequest.from_messages(messages)
        self._validate_protocol_support(request)
        prepared: List[Dict[str, Any]] = []
        for message in request.messages:
            openai_parts = [self._to_openai_content_part(part) for part in message.content]
            text_only = len(openai_parts) == 1 and openai_parts[0].get("type") == "text"
            prepared.append(
                {
                    "role": message.role,
                    "content": openai_parts[0]["text"] if text_only else openai_parts,
                }
            )
        return prepared

    def prepare_responses_messages(self, messages: Sequence[UnifiedMessage | Dict[str, Any]]) -> List[Dict[str, Any]]:
        request = UnifiedModelRequest.from_messages(messages)
        self._validate_protocol_support(request)
        return self._prepare_responses_messages(request)

    def _prepare_responses_messages(self, request: UnifiedModelRequest) -> List[Dict[str, Any]]:
        prepared: List[Dict[str, Any]] = []
        for message in request.messages:
            parts = [self._to_responses_content_part(part, request) for part in message.content]
            prepared.append({"role": message.role, "content": parts if parts else [{"type": "input_text", "text": ""}]})
        return prepared

    def build_http_payload(
        self,
        request_or_messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]],
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
        request = self._coerce_request(request_or_messages, **kwargs)
        spec = self._validate_protocol_support(request)
        canonical = {
            **self._config_canonical_params(),
            **request.canonical_params(),
        }
        mapped_params, mapping_metadata = spec.map_params(canonical)
        payload = {
            "model": self.model,
            **mapped_params,
        }
        payload.update(self._api_request_config(self.config))
        payload.update(request.extra_params)
        if spec.endpoint_family == "responses":
            payload["input"] = self._prepare_responses_messages(request)
        else:
            payload["messages"] = self.prepare_messages(request.messages)
        if stream:
            payload["stream"] = True
        metadata = {
            **mapping_metadata,
            "media_transports": request.metadata.get("media_transports", []),
        }
        return spec.endpoint_family, payload, metadata

    @staticmethod
    def _extract_response_error(response) -> Optional[str]:
        error = getattr(response, "error", None)
        if not error:
            return None
        if isinstance(error, dict):
            return error.get("message") or error.get("code")
        return getattr(error, "message", None) or str(error)

    async def _stream_chat_completions(self, request: UnifiedModelRequest) -> AsyncIterator[LLMResponse]:
        try:
            client = self._build_client()
            _, params, _ = self.build_http_payload(request, stream=True)
            stream = await client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield LLMResponse(content=delta.content)
                    if chunk.choices[0].finish_reason:
                        usage = {}
                        if hasattr(chunk, "usage") and chunk.usage:
                            usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens,
                            }
                        yield LLMResponse(
                            content="",
                            finish_reason=chunk.choices[0].finish_reason,
                            usage=usage,
                        )
        except ImportError as exc:
            raise RuntimeError("OpenAI library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def _chat_completions(self, request: UnifiedModelRequest) -> str:
        try:
            client = self._build_client()
            _, params, _ = self.build_http_payload(request)
            response = await client.chat.completions.create(**params)
            error_message = self._extract_response_error(response)
            if error_message:
                raise RuntimeError(error_message)
            if not response.choices:
                return ""
            return self._extract_message_content(response.choices[0].message)
        except ImportError as exc:
            raise RuntimeError("OpenAI library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def _stream_responses(self, request: UnifiedModelRequest) -> AsyncIterator[LLMResponse]:
        try:
            client = self._build_client()
            _, params, _ = self.build_http_payload(request, stream=True)
            stream = await client.responses.create(**params)
            async for chunk in stream:
                event_type = getattr(chunk, "type", "")
                delta = getattr(chunk, "delta", None) if event_type == "response.output_text.delta" else getattr(chunk, "output_text", None)
                if delta:
                    yield LLMResponse(content=delta)
                finish_reason = getattr(chunk, "finish_reason", None)
                if not finish_reason and event_type in {"response.completed", "response.incomplete", "response.failed"}:
                    finish_reason = "stop" if event_type == "response.completed" else event_type.replace("response.", "")
                if finish_reason:
                    response = getattr(chunk, "response", None)
                    usage_source = getattr(response, "usage", None) or getattr(chunk, "usage", None)
                    usage = {}
                    if usage_source:
                        usage = {
                            "prompt_tokens": getattr(usage_source, "input_tokens", 0),
                            "completion_tokens": getattr(usage_source, "output_tokens", 0),
                            "total_tokens": getattr(usage_source, "total_tokens", 0),
                        }
                    yield LLMResponse(content="", finish_reason=finish_reason, usage=usage)
        except ImportError as exc:
            raise RuntimeError("OpenAI library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def _responses_chat(self, request: UnifiedModelRequest) -> str:
        try:
            client = self._build_client()
            _, params, _ = self.build_http_payload(request)
            response = await client.responses.create(**params)
            text = getattr(response, "output_text", None)
            if text is not None:
                return text
            output = getattr(response, "output", None) or []
            fragments: List[str] = []
            for item in output:
                content = getattr(item, "content", None) or []
                for part in content:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        fragments.append(part_text)
            return "".join(fragments)
        except ImportError as exc:
            raise RuntimeError("OpenAI library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def stream_chat(
        self,
        messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]],
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        request = self._coerce_request(messages, **kwargs)
        spec = self._validate_protocol_support(request)
        if spec.endpoint_family == "responses":
            async for chunk in self._stream_responses(request):
                yield chunk
            return
        async for chunk in self._stream_chat_completions(request):
            yield chunk

    async def chat(
        self,
        messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]],
        **kwargs,
    ) -> str:
        request = self._coerce_request(messages, **kwargs)
        spec = self._validate_protocol_support(request)
        if spec.endpoint_family == "responses":
            return await self._responses_chat(request)
        return await self._chat_completions(request)
