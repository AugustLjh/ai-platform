from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence
from abc import ABC, abstractmethod

from .messages import (
    ModelCapabilityProfile,
    ModelRequestProfile,
    UnifiedMessage,
    UnifiedModelRequest,
    supports_model_request,
    merge_capability_profiles,
    normalize_messages,
    required_input_modalities,
)


class LLMResponse:
    """LLM response chunk"""

    def __init__(self, content: str, finish_reason: Optional[str] = None, usage: Optional[Dict] = None):
        self.content = content
        self.finish_reason = finish_reason
        self.usage = usage or {}

    def __repr__(self):
        return f"LLMResponse(content={self.content}, finish_reason={self.finish_reason})"


class BaseLLM(ABC):
    """Base LLM interface with streaming support"""

    def __init__(self, model: str, **kwargs):
        self.model = model
        self.config = kwargs
        self.capabilities = merge_capability_profiles(kwargs.get("capabilities"))

    @abstractmethod
    async def stream_chat(
        self,
        messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]],
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        """
        Stream chat completion

        Args:
            messages: List of messages or raw dicts with 'role' and 'content'
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Yields:
            LLMResponse chunks
        """
        pass

    async def chat(self, messages: UnifiedModelRequest | Sequence[UnifiedMessage | Dict[str, Any]], **kwargs) -> str:
        """
        Non-streaming chat (convenience method)

        Args:
            messages: List of message dicts
            **kwargs: Additional parameters

        Returns:
            Complete response text
        """
        content = ""
        async for chunk in self.stream_chat(messages, **kwargs):
            content += chunk.content
        return content

    def normalize_messages(self, messages: Sequence[UnifiedMessage | Dict[str, Any]]) -> list[UnifiedMessage]:
        return normalize_messages(messages)

    def required_input_modalities(self, messages: Iterable[UnifiedMessage | Dict[str, Any]]) -> set[str]:
        return required_input_modalities(messages)

    def supports_request(self, request: ModelRequestProfile | Dict[str, Any]) -> bool:
        return supports_model_request(self.capabilities, request)
