"""Jina chat model (LangChain ``BaseChatModel`` subclass).

In the legacy codebase, ``JinaLLM`` was a thin subclass of ``OpenAILLM``
pointing at ``https://deepsearch.jina.ai/v1``. The Jina API is
OpenAI-compatible, so we reuse ``_OpenAICompatBase`` (which wraps
``langchain_openai.ChatOpenAI``) with the correct defaults.
"""
from __future__ import annotations

from typing import ClassVar

from ai_runtime.llm.openai_compat import _OpenAICompatBase


class JinaChatModel(_OpenAICompatBase):
    """Jina DeepSearch via OpenAI-compatible endpoint."""

    DEFAULT_API_BASE: ClassVar[str] = "https://deepsearch.jina.ai/v1"
    DEFAULT_PROVIDER: ClassVar[str] = "jina"
    DEFAULT_ENDPOINT_PROTOCOL: ClassVar[str] = "openai.chat_completions"


__all__ = ["JinaChatModel"]
