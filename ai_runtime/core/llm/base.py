from typing import AsyncIterator, Dict, List, Optional
from abc import ABC, abstractmethod


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

    @abstractmethod
    async def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[LLMResponse]:
        """
        Stream chat completion

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Yields:
            LLMResponse chunks
        """
        pass

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
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
