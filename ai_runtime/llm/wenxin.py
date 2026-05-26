"""Baidu Wenxin / ERNIE chat model (LangChain ``BaseChatModel`` subclass).

In the legacy codebase, ``WenxinLLM`` was a thin subclass of ``OpenAILLM``
pointing at ``https://qianfan.baidubce.com/v2``. The Qianfan API is
OpenAI-compatible, so we reuse ``_OpenAICompatBase`` (which wraps
``langchain_openai.ChatOpenAI``) with the correct defaults.
"""
from __future__ import annotations

from typing import ClassVar

from ai_runtime.llm.openai_compat import _OpenAICompatBase


class WenxinChatModel(_OpenAICompatBase):
    """Baidu Wenxin / ERNIE via Qianfan OpenAI-compatible endpoint."""

    DEFAULT_API_BASE: ClassVar[str] = "https://qianfan.baidubce.com/v2"
    DEFAULT_PROVIDER: ClassVar[str] = "wenxin"
    DEFAULT_ENDPOINT_PROTOCOL: ClassVar[str] = "baidu.qianfan_chat_completions"
    USES_CATALOG: ClassVar[bool] = True


__all__ = ["WenxinChatModel"]
