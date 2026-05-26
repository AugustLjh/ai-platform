from typing import Any, Dict, Optional

from .base import BaseLLM
from .chinese import DoubaoLLM, GLMLLM, KimiLLM, QwenLLM, WenxinLLM
from .deepseek import DeepseekLLM
from .jina import JinaLLM
from .local import LocalLLM
from .openai import OpenAILLM


SUPPORTED_LLM_PROVIDERS = (
    "openai",
    "deepseek",
    "jina",
    "qwen",
    "wenxin",
    "glm",
    "kimi",
    "doubao",
    "local",
    "mock",
)
SUPPORTED_LLM_PROVIDER_PATTERN = f"^({'|'.join(SUPPORTED_LLM_PROVIDERS)})$"
OPENAI_COMPATIBLE_LLM_PROVIDERS = {
    "openai",
    "jina",
    "qwen",
    "wenxin",
    "glm",
    "kimi",
    "doubao",
}


def create_llm_for_provider(
    provider: str,
    *,
    model: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> BaseLLM:
    normalized_provider = (provider or "").lower()
    llm_kwargs = dict(config or {})
    if api_base:
        llm_kwargs["api_base"] = api_base
    llm_kwargs.setdefault("provider", normalized_provider)
    if "capabilities" in llm_kwargs and isinstance(llm_kwargs["capabilities"], dict):
        llm_kwargs["capabilities"] = dict(llm_kwargs["capabilities"])

    if normalized_provider == "openai":
        return OpenAILLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "deepseek":
        return DeepseekLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "jina":
        return JinaLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "qwen":
        return QwenLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "wenxin":
        return WenxinLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "glm":
        return GLMLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "kimi":
        return KimiLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider == "doubao":
        return DoubaoLLM(model=model, api_key=api_key, **llm_kwargs)
    if normalized_provider in {"local", "mock"}:
        return LocalLLM(model=model, **llm_kwargs)

    raise ValueError(f"Unsupported LLM provider: {normalized_provider}")
