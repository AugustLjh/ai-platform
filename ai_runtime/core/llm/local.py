from typing import Any, AsyncIterator, Dict, Sequence
from .base import BaseLLM, LLMResponse
import asyncio
from .messages import ModelCapabilityProfile, UnifiedMessage, normalize_messages


class LocalLLM(BaseLLM):
    """Local LLM implementation (mock for demo)"""

    def __init__(self, model: str = "local-model", **kwargs):
        kwargs.setdefault("endpoint_protocol", "local.chat_completions")
        super().__init__(model, **kwargs)
        self.capabilities = ModelCapabilityProfile(
            endpoint_protocol=kwargs.get("endpoint_protocol"),
            input_modalities=["text"],
            output_modalities=["text"],
        )

    async def stream_chat(self, messages: Sequence[UnifiedMessage | Dict[str, Any]], **kwargs) -> AsyncIterator[LLMResponse]:
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
        normalized = normalize_messages(messages)
        if normalized:
            last_message = normalized[-1]
            if last_message.role == 'user':
                response_text += f"\n\nYour question was: {''.join(part.text or '' for part in last_message.content if part.type == 'text')}"

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
                "prompt_tokens": sum(len(''.join(part.text or '' for part in m.content if part.type == 'text').split()) for m in normalized),
                "completion_tokens": len(words),
                "total_tokens": sum(len(''.join(part.text or '' for part in m.content if part.type == 'text').split()) for m in normalized) + len(words)
            }
        )
