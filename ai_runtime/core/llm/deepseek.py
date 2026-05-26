from typing import Any, AsyncIterator, Dict, Optional, Sequence
from .base import BaseLLM, LLMResponse
from .messages import ModelCapabilityProfile, UnifiedMessage, normalize_messages


class DeepseekLLM(BaseLLM):
    def __init__(self, model: str = "deepseek-chat", api_key: Optional[str] = None, **kwargs):
        api_base = kwargs.pop("api_base", "https://api.deepseek.com/v1")
        kwargs.setdefault("endpoint_protocol", "deepseek.chat_completions")
        super().__init__(model, **kwargs)
        self.api_key = api_key
        # DeepSeek API base URL
        self.api_base = api_base
        self.capabilities = ModelCapabilityProfile(
            input_modalities=["text"],
            output_modalities=["text"],
            endpoint_protocol=kwargs.get("endpoint_protocol"),
            supports_tools=bool(kwargs.get("supports_tools", False)),
        )

    async def stream_chat(self, messages: Sequence[UnifiedMessage | Dict[str, Any]], **kwargs) -> AsyncIterator[LLMResponse]:
        """
        Stream chat with DeepSeek

        Args:
            messages: Chat messages
            **kwargs: temperature, max_tokens, etc.

        Yields:
            LLMResponse chunks
        """
        try:
            normalized = normalize_messages(messages)
            if any(part.type != "text" for message in normalized for part in message.content):
                raise RuntimeError("DeepSeek text-only model cannot accept multimodal input")
            # Import httpx for async HTTP requests
            import httpx

            # Prepare request headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Merge config with kwargs
            params = {
                "model": self.model,
                "messages": [{"role": message.role, "content": "".join(part.text or "" for part in message.content)} for message in normalized],
                "stream": True,
                **self.config,
                **kwargs
            }

            # Send request
            async with httpx.AsyncClient() as client:
                async with client.stream(
                        "POST",
                        f"{self.api_base}/chat/completions",
                        headers=headers,
                        json=params
                ) as response:
                    response.raise_for_status()

                    # Process stream
                    async for chunk in response.aiter_text():
                        # Skip empty chunks
                        if not chunk.strip():
                            continue

                        # Parse each line (DeepSeek returns data chunks like OpenAI)
                        for line in chunk.splitlines():
                            # Skip SSE comments and empty lines
                            line = line.strip()
                            if not line or line == "data: [DONE]":
                                continue

                            # Remove "data: " prefix
                            if line.startswith("data: "):
                                line = line[6:]

                            # Parse JSON
                            import json
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            # Extract content
                            if "choices" in data and len(data["choices"]) > 0:
                                choice = data["choices"][0]
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")
                                finish_reason = choice.get("finish_reason")

                                if content:
                                    yield LLMResponse(content=content)

                                # Final chunk with usage info
                                if finish_reason:
                                    usage = data.get("usage", {})
                                    yield LLMResponse(
                                        content="",
                                        finish_reason=finish_reason,
                                        usage={
                                            "prompt_tokens": usage.get("prompt_tokens", 0),
                                            "completion_tokens": usage.get("completion_tokens", 0),
                                            "total_tokens": usage.get("total_tokens", 0)
                                        }
                                    )

        except ImportError as exc:
            raise RuntimeError("httpx library not installed") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
