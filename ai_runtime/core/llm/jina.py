from typing import Optional

from .openai import OpenAILLM


class JinaLLM(OpenAILLM):
    """Jina chat model implementation via OpenAI-compatible API."""

    def __init__(self, model: str = "jina-deepsearch-v1", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("api_base", "https://deepsearch.jina.ai/v1")
        super().__init__(model=model, api_key=api_key, **kwargs)
