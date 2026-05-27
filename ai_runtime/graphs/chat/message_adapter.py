"""Translate UnifiedMessage lists to LangChain BaseMessage lists.

The chat graph builds ``UnifiedMessage`` objects (role + list of
``ContentPart``) via ``ChatPromptBuilder``. LangChain's ``BaseChatModel``
expects ``list[BaseMessage]``. This module bridges the two.

Mapping:
  role=system  → SystemMessage(content=str)
  role=user    → HumanMessage(content=str | list[dict])
  role=assistant → AIMessage(content=str)
  role=tool    → ToolMessage(content=str, tool_call_id=...)

For user messages with multimodal parts, we produce the OpenAI-style
content list format that LangChain passes through to the provider:
  [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from ai_runtime.core.llm.messages import ContentPart, UnifiedMessage


def unified_to_langchain(
    messages: Sequence[Union[UnifiedMessage, Dict[str, Any]]],
) -> List[BaseMessage]:
    """Convert a sequence of UnifiedMessage (or raw dicts) to BaseMessage."""
    result: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts = msg.get("content_parts") or (
                content if isinstance(content, list) else None
            )
            if parts and isinstance(parts, list):
                result.append(_convert_parts_message(role, parts))
            else:
                text = content if isinstance(content, str) else ""
                result.append(_make_message(role, text))
        elif isinstance(msg, UnifiedMessage):
            if len(msg.content) == 1 and msg.content[0].type == "text":
                result.append(_make_message(msg.role, msg.content[0].text or ""))
            elif all(p.type == "text" for p in msg.content):
                combined = "".join(p.text or "" for p in msg.content)
                result.append(_make_message(msg.role, combined))
            else:
                lc_parts = [_content_part_to_lc(p) for p in msg.content]
                result.append(_assemble_message(msg.role, lc_parts))
        else:
            result.append(HumanMessage(content=str(msg)))
    return result


def _make_message(role: str, text: str) -> BaseMessage:
    if role == "system":
        return SystemMessage(content=text)
    if role == "assistant":
        return AIMessage(content=text)
    if role == "tool":
        return ToolMessage(content=text, tool_call_id="")
    return HumanMessage(content=text)


def _convert_parts_message(role: str, parts: Any) -> BaseMessage:
    """Build a message from a list of content parts (dict or ContentPart)."""
    lc_content: List[Dict[str, Any]] = []
    for part in parts:
        if isinstance(part, ContentPart):
            lc_content.append(_content_part_to_lc(part))
        elif isinstance(part, dict):
            lc_content.append(_dict_part_to_lc(part))
        else:
            lc_content.append({"type": "text", "text": str(part)})
    return _assemble_message(role, lc_content)


def _assemble_message(role: str, lc_content: List[Dict[str, Any]]) -> BaseMessage:
    """Wrap pre-translated LangChain-format content parts in the role-appropriate message."""
    if role == "system":
        text = " ".join(
            p.get("text", "") for p in lc_content if p.get("type") == "text"
        )
        return SystemMessage(content=text)
    if role == "assistant":
        text = " ".join(
            p.get("text", "") for p in lc_content if p.get("type") == "text"
        )
        return AIMessage(content=text)
    return HumanMessage(content=lc_content)


def _content_part_to_lc(part: ContentPart) -> Dict[str, Any]:
    if part.type == "text":
        return {"type": "text", "text": part.text or ""}
    if part.type == "image":
        url = part.url or (
            f"data:{part.mime_type or 'image/png'};base64,{part.base64}"
            if part.base64
            else None
        )
        if url:
            return {"type": "image_url", "image_url": {"url": url}}
        if part.file_id:
            return {"type": "image_url", "image_url": {"url": f"file://{part.file_id}"}}
        return {"type": "text", "text": f"[image: {part.file_name or 'unnamed'}]"}
    if part.type in ("audio", "video", "file"):
        text = part.text or f"[{part.type}: {part.file_name or part.file_id or 'unnamed'}]"
        return {"type": "text", "text": text}
    if part.type == "tool_result":
        return {"type": "text", "text": part.text or "[tool_result]"}
    return {"type": "text", "text": str(part.text or "")}


def _dict_part_to_lc(part: Dict[str, Any]) -> Dict[str, Any]:
    ptype = str(part.get("type") or "text").lower()
    if ptype == "text":
        return {"type": "text", "text": str(part.get("text") or "")}
    if ptype == "image":
        url = part.get("url")
        if not url and part.get("base64"):
            mime = part.get("mime_type") or "image/png"
            url = f"data:{mime};base64,{part['base64']}"
        if url:
            return {"type": "image_url", "image_url": {"url": url}}
        if part.get("file_id"):
            return {"type": "image_url", "image_url": {"url": f"file://{part['file_id']}"}}
        return {"type": "text", "text": f"[image: {part.get('file_name', 'unnamed')}]"}
    if ptype in ("audio", "video", "file"):
        text = part.get("text") or f"[{ptype}: {part.get('file_name') or part.get('file_id') or 'unnamed'}]"
        return {"type": "text", "text": text}
    if ptype == "tool_result":
        return {"type": "text", "text": part.get("text") or "[tool_result]"}
    return {"type": "text", "text": str(part.get("text") or "")}


__all__ = ["unified_to_langchain"]
