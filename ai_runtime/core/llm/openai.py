from typing import AsyncIterator, Dict, List, Optional
from .base import BaseLLM, LLMResponse


class OpenAILLM(BaseLLM):
    """OpenAI LLM implementation with streaming"""

    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key

    async def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[LLMResponse]:
        """
        Stream chat with OpenAI

        Args:
            messages: Chat messages
            **kwargs: temperature, max_tokens, etc.

        Yields:
            LLMResponse chunks
        """
        try:
            # Import OpenAI client (optional dependency)
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

            # Merge config with kwargs
            params = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                **self.config,
                **kwargs
            }

            stream = await client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield LLMResponse(content=delta.content)

                    # Final chunk with usage info
                    if chunk.choices[0].finish_reason:
                        usage = {}
                        if hasattr(chunk, 'usage') and chunk.usage:
                            usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens
                            }
                        yield LLMResponse(
                            content="",
                            finish_reason=chunk.choices[0].finish_reason,
                            usage=usage
                        )

        except ImportError:
            # Fallback to mock implementation if OpenAI not installed
            yield LLMResponse(content="[Mock OpenAI Response] ")
            yield LLMResponse(content="OpenAI library not installed. ")
            yield LLMResponse(content="Please install: pip install openai")
            yield LLMResponse(content="", finish_reason="stop", usage={})

        except Exception as e:
            yield LLMResponse(content=f"Error: {str(e)}", finish_reason="error")
