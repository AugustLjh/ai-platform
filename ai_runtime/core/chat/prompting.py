from typing import Any, Dict, List, Optional, Sequence

from ai_runtime.core.prompt import PromptBuilder
from ai_runtime.core.llm.messages import ContentPart, UnifiedMessage


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

    def build_unified_messages(
        self,
        user_message: str,
        history: Optional[Sequence[UnifiedMessage | Dict[str, Any]]] = None,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        user_parts: Optional[Sequence[ContentPart | Dict[str, Any]]] = None,
    ) -> list[UnifiedMessage]:
        return self._prompt_builder.build_unified(
            system_prompt=system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT,
            user_message=user_message,
            context=context,
            history=history,
            user_parts=user_parts,
        )
