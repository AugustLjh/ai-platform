from typing import Optional

from .catalog import infer_model_capabilities
from .messages import capability_profile_from_settings
from .openai import OpenAILLM


class QwenLLM(OpenAILLM):
    """Qwen/Tongyi chat model via DashScope OpenAI-compatible API."""

    @staticmethod
    def _infer_capabilities(model: str) -> dict:
        return infer_model_capabilities("qwen", model)

    def __init__(self, model: str = "qwen-plus", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("provider", "qwen")
        kwargs.setdefault("api_base", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        kwargs.setdefault("endpoint_protocol", "dashscope.openai_compatible")
        kwargs.setdefault(
            "capabilities",
            capability_profile_from_settings(QwenLLM._infer_capabilities(model)).model_dump(),
        )
        super().__init__(model=model, api_key=api_key, **kwargs)


class WenxinLLM(OpenAILLM):
    """Baidu Wenxin/Qianfan chat model via OpenAI-compatible API."""

    def __init__(self, model: str = "ernie-4.0-turbo-8k", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("provider", "wenxin")
        kwargs.setdefault("api_base", "https://qianfan.baidubce.com/v2")
        kwargs.setdefault("endpoint_protocol", "baidu.qianfan_chat_completions")
        kwargs.setdefault(
            "capabilities",
            capability_profile_from_settings(infer_model_capabilities("wenxin", model)).model_dump(),
        )
        super().__init__(model=model, api_key=api_key, **kwargs)


class GLMLLM(OpenAILLM):
    """Zhipu GLM chat model via OpenAI-compatible API."""

    def __init__(self, model: str = "glm-4-plus", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("provider", "glm")
        kwargs.setdefault("api_base", "https://open.bigmodel.cn/api/paas/v4")
        kwargs.setdefault("endpoint_protocol", "bigmodel.chat_completions")
        kwargs.setdefault(
            "capabilities",
            capability_profile_from_settings(infer_model_capabilities("glm", model)).model_dump(),
        )
        super().__init__(model=model, api_key=api_key, **kwargs)


class KimiLLM(OpenAILLM):
    """Kimi/Moonshot chat model via OpenAI-compatible API."""

    def __init__(self, model: str = "moonshot-v1-8k", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("provider", "kimi")
        kwargs.setdefault("api_base", "https://api.moonshot.cn/v1")
        kwargs.setdefault("endpoint_protocol", "moonshot.chat_completions")
        kwargs.setdefault(
            "capabilities",
            capability_profile_from_settings(infer_model_capabilities("kimi", model)).model_dump(),
        )
        super().__init__(model=model, api_key=api_key, **kwargs)


class DoubaoLLM(OpenAILLM):
    """Doubao/Volcengine Ark chat model via OpenAI-compatible API."""

    def __init__(self, model: str = "doubao-seed-1-6", api_key: Optional[str] = None, **kwargs):
        kwargs.setdefault("provider", "doubao")
        kwargs.setdefault("api_base", "https://ark.cn-beijing.volces.com/api/v3")
        kwargs.setdefault("endpoint_protocol", "volcengine.ark_chat_completions")
        kwargs.setdefault(
            "capabilities",
            capability_profile_from_settings(infer_model_capabilities("doubao", model)).model_dump(),
        )
        super().__init__(model=model, api_key=api_key, **kwargs)
