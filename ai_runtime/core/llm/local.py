from typing import AsyncIterator, Dict, List
from .base import BaseLLM, LLMResponse
import asyncio


class LocalLLM(BaseLLM):
    """Local LLM implementation (mock for demo)"""

    def __init__(self, model: str = "local-model", **kwargs):
        super().__init__(model, **kwargs)

    async def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[LLMResponse]:
        """
        Mock streaming response for local LLM

        Args:
            messages: Chat messages
            **kwargs: Additional parameters

        Yields:
            LLMResponse chunks
        """
        # Mock response
        response_text = f"This is a mock response from {self.model}. "
        response_text += "In a real implementation, this would connect to a local LLM service "
        response_text += "(e.g., Ollama, vLLM, or custom endpoint). "

        # Add user query context
        if messages:
            last_message = messages[-1]
            if last_message.get('role') == 'user':
                response_text += f"\n\nYour question was: {last_message.get('content', '')}"

        # Stream word by word
        words = response_text.split()
        for word in words:
            await asyncio.sleep(0.05)  # Simulate streaming delay
            yield LLMResponse(content=word + " ")

        # Final chunk
        yield LLMResponse(
            content="",
            finish_reason="stop",
            usage={
                "prompt_tokens": sum(len(m.get('content', '').split()) for m in messages),
                "completion_tokens": len(words),
                "total_tokens": sum(len(m.get('content', '').split()) for m in messages) + len(words)
            }
        )
