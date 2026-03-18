from typing import Any, Dict, List, Optional

from core.prompt import PromptBuilder


DEFAULT_CHAT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. "
    "When retrieval context is provided, answer strictly from that context. "
    "If the context is insufficient, say so clearly instead of making up facts."
)


class ChatPromptBuilder:
    """Build prompts for the low-latency chat runtime."""

    def __init__(self, prompt_builder: Optional[PromptBuilder] = None):
        self._prompt_builder = prompt_builder or PromptBuilder()

    def build_messages(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        return self._prompt_builder.build(
            system_prompt=system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT,
            user_message=user_message,
            context=context,
            history=history,
        )
