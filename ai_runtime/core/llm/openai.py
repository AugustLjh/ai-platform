from typing import AsyncIterator, Dict, List, Optional
from .base import BaseLLM, LLMResponse


class OpenAILLM(BaseLLM):
    """OpenAI LLM implementation with streaming"""

    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None, **kwargs):
        api_base = kwargs.pop("api_base", None)
        super().__init__(model, **kwargs)
        self.api_key = api_key
        self.api_base = api_base

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
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if text:
                    parts.append(text)
            return "".join(parts)

        return str(content) if content else ""

    @staticmethod
    def _extract_response_error(response) -> Optional[str]:
        error = getattr(response, "error", None)
        if not error:
            return None

        if isinstance(error, dict):
            return error.get("message") or error.get("code")

        return getattr(error, "message", None) or str(error)

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
            client = self._build_client()

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

        except ImportError as exc:
            raise RuntimeError("OpenAI library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        try:
            client = self._build_client()

            params = {
                "model": self.model,
                "messages": messages,
                **self.config,
                **kwargs,
            }

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
