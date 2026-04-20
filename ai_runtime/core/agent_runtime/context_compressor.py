from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Sequence


COMPRESSED_CONTEXT_KEY = "compressed_context"
PROMPT_CONTEXT_KEY = "prompt_context"
COMPRESSION_STATE_KEY = "context_compression"


@dataclass(frozen=True)
class ContextCompressorConfig:
    conversation_tail: int = 6
    observation_tail: int = 6
    max_conversation_messages_before_compression: int = 8
    max_step_history_before_compression: int = 6
    max_raw_context_chars_before_compression: int = 12000
    max_message_chars: int = 1200
    max_result_chars: int = 1600
    max_json_chars: int = 2400
    max_evidence_items: int = 12
    max_decision_items: int = 10
    max_open_questions: int = 8


class ContextCompressor:
    """Builds a compact prompt-facing view while preserving full runtime context."""

    protocol_version = "agent-context-compression.v1"

    def __init__(self, config: ContextCompressorConfig | None = None) -> None:
        self.config = config or ContextCompressorConfig()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _safe_list(self, value: Any) -> list[Any]:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return list(value)
        return []

    def _safe_dict(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _compact_text(self, value: Any, limit: int | None = None) -> str:
        text = str(value or "").strip()
        text = " ".join(text.split())
        max_chars = limit or self.config.max_message_chars
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."

    def _compact_value(self, value: Any, limit: int | None = None) -> Any:
        if value is None:
            return None
        max_chars = limit or self.config.max_json_chars
        if isinstance(value, str):
            return self._compact_text(value, max_chars)
        if isinstance(value, (int, float, bool)):
            return value
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
        if len(text) <= max_chars:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text[: max_chars - 3].rstrip() + "..."

    def _context_chars(self, conversation: list[Any], step_history: list[Any]) -> int:
        try:
            return len(json.dumps({"conversation": conversation, "step_history": step_history}, ensure_ascii=False))
        except TypeError:
            return len(str(conversation)) + len(str(step_history))

    def _unique_strings(self, values: Iterable[Any], *, limit: int) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = self._compact_text(value, 500)
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
            if len(items) >= limit:
                break
        return items

    def _message_tail(self, conversation: list[Any]) -> list[dict[str, str]]:
        tail: list[dict[str, str]] = []
        for item in conversation[-self.config.conversation_tail :]:
            if not isinstance(item, dict):
                continue
            role = self._compact_text(item.get("role"), 40) or "unknown"
            content = self._compact_text(item.get("content"), self.config.max_message_chars)
            if content:
                tail.append({"role": role, "content": content})
        return tail

    def _conversation_digest(self, conversation: list[Any]) -> list[dict[str, str]]:
        older = conversation[: -self.config.conversation_tail] if len(conversation) > self.config.conversation_tail else []
        digest: list[dict[str, str]] = []
        for item in older[-6:]:
            if not isinstance(item, dict):
                continue
            role = self._compact_text(item.get("role"), 40) or "unknown"
            content = self._compact_text(item.get("content"), 420)
            if content:
                digest.append({"role": role, "summary": content})
        return digest

    def _extract_result_excerpt(self, result: Any) -> str:
        if isinstance(result, str):
            return self._compact_text(result, self.config.max_result_chars)
        if not isinstance(result, dict):
            return self._compact_text(self._compact_value(result), self.config.max_result_chars)

        for key in ("text", "summary", "answer", "final_output", "content", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return self._compact_text(value, self.config.max_result_chars)

        structured = result.get("structured_content")
        if isinstance(structured, dict):
            for key in ("summary", "answer", "text"):
                value = structured.get(key)
                if isinstance(value, str) and value.strip():
                    return self._compact_text(value, self.config.max_result_chars)

        return self._compact_text(self._compact_value(result, self.config.max_result_chars), self.config.max_result_chars)

    def _observation_summary(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        summary: dict[str, Any] = {
            "step_index": item.get("step_index"),
            "title": self._compact_text(item.get("title"), 220) or None,
            "kind": self._compact_text(item.get("kind"), 80) or None,
            "status": self._compact_text(item.get("status"), 80) or None,
        }
        tool_name = self._compact_text(item.get("tool_name"), 160)
        delegate_target = self._compact_text(item.get("delegate_target"), 160)
        if tool_name:
            summary["tool_name"] = tool_name
        if delegate_target:
            summary["delegate_target"] = delegate_target
        if item.get("tool_arguments") is not None:
            summary["tool_arguments"] = self._compact_value(item.get("tool_arguments"), 800)
        if item.get("result") is not None:
            summary["result_excerpt"] = self._extract_result_excerpt(item.get("result"))
        error = self._compact_text(item.get("error"), 600)
        if error:
            summary["error"] = error
        return {key: value for key, value in summary.items() if value is not None}

    def _observation_tail(self, step_history: list[Any]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for item in step_history[-self.config.observation_tail :]:
            summary = self._observation_summary(item)
            if summary:
                summaries.append(summary)
        return summaries

    def _observation_digest(self, step_history: list[Any]) -> list[dict[str, Any]]:
        older = step_history[: -self.config.observation_tail] if len(step_history) > self.config.observation_tail else []
        summaries: list[dict[str, Any]] = []
        for item in older[-8:]:
            summary = self._observation_summary(item)
            if not summary:
                continue
            summaries.append(
                {
                    key: summary[key]
                    for key in ("step_index", "title", "kind", "status", "tool_name", "delegate_target", "error", "result_excerpt")
                    if key in summary
                }
            )
        return summaries

    def _build_objective(self, run_input: dict[str, Any], runtime_context: dict[str, Any]) -> str:
        normalized_task_input = self._safe_dict(runtime_context.get("normalized_task_input"))
        candidates = [
            normalized_task_input.get("message"),
            normalized_task_input.get("original_message"),
            run_input.get("message"),
            run_input.get("prompt"),
        ]
        for candidate in candidates:
            text = self._compact_text(candidate, 1200)
            if text:
                return text
        return "No explicit objective was provided."

    def _build_open_questions(self, runtime_context: dict[str, Any]) -> list[str]:
        intent_state = self._safe_dict(runtime_context.get("intent_state"))
        values: list[Any] = []
        if runtime_context.get("pending_question"):
            values.append(runtime_context.get("pending_question"))
        values.extend(self._safe_list(intent_state.get("blocking_missing_information")))
        values.extend(self._safe_list(intent_state.get("missing_information")))
        return self._unique_strings(values, limit=self.config.max_open_questions)

    def _build_constraints(self, runtime_context: dict[str, Any]) -> list[str]:
        intent_state = self._safe_dict(runtime_context.get("intent_state"))
        values: list[Any] = []
        values.extend(self._safe_list(intent_state.get("assumptions")))
        if intent_state.get("requires_user_decision"):
            values.append("A user decision may be required before acting on high-impact choices.")
        if runtime_context.get("mounted_knowledge_base_ids"):
            values.append(f"Mounted knowledge bases: {', '.join(str(item) for item in runtime_context.get('mounted_knowledge_base_ids') or [])}")
        managed_subagent = self._safe_dict(runtime_context.get("managed_subagent"))
        if managed_subagent:
            values.append("Managed subagent policy is active for this run.")
        return self._unique_strings(values, limit=10)

    def _build_evidence_digest(self, step_history: list[Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for item in step_history:
            if not isinstance(item, dict) or item.get("result") is None:
                continue
            summary = self._observation_summary(item)
            if not summary:
                continue
            status = str(item.get("status") or "").lower()
            if status and status not in {"completed", "succeeded", "success"}:
                continue
            evidence.append(
                {
                    "source": summary.get("tool_name") or summary.get("delegate_target") or summary.get("title") or "step",
                    "step_index": summary.get("step_index"),
                    "summary": summary.get("result_excerpt") or summary.get("title"),
                }
            )
            if len(evidence) >= self.config.max_evidence_items:
                break
        return evidence

    def _build_decisions(self, step_history: list[Any]) -> list[str]:
        values: list[str] = []
        for item in step_history:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").lower()
            title = self._compact_text(item.get("title"), 240)
            tool_name = self._compact_text(item.get("tool_name"), 160)
            delegate_target = self._compact_text(item.get("delegate_target"), 160)
            if status in {"completed", "succeeded", "success"}:
                if tool_name:
                    values.append(f"Completed tool step {tool_name}: {title or 'untitled'}")
                elif delegate_target:
                    values.append(f"Completed delegation to {delegate_target}: {title or 'untitled'}")
                elif title:
                    values.append(f"Completed step: {title}")
            elif status == "failed":
                label = tool_name or delegate_target or title
                if label:
                    values.append(f"Previous attempt failed: {label}")
        return self._unique_strings(values, limit=self.config.max_decision_items)

    def _build_tool_state(self, runtime_context: dict[str, Any], step_history: list[Any]) -> dict[str, Any]:
        tool_attempts = []
        failed_tools = []
        for item in step_history:
            if not isinstance(item, dict):
                continue
            name = self._compact_text(item.get("tool_name") or item.get("delegate_target"), 160)
            if not name:
                continue
            status = self._compact_text(item.get("status"), 80)
            tool_attempts.append({"name": name, "status": status or "unknown", "step_index": item.get("step_index")})
            if status.lower() == "failed":
                failed_tools.append(name)
        return {
            "execution_count": runtime_context.get("execution_count", 0),
            "tool_failures": runtime_context.get("tool_failures", 0),
            "attempt_count": len(tool_attempts),
            "recent_attempts": tool_attempts[-6:],
            "failed_tools": self._unique_strings(failed_tools, limit=6),
        }

    def should_compress(self, runtime_context: dict[str, Any]) -> tuple[bool, list[str], dict[str, int]]:
        conversation = self._safe_list(runtime_context.get("conversation"))
        step_history = self._safe_list(runtime_context.get("step_history"))
        raw_context_chars = self._context_chars(conversation, step_history)
        counters = {
            "conversation_message_count": len(conversation),
            "step_history_count": len(step_history),
            "raw_context_chars": raw_context_chars,
        }
        reasons: list[str] = []
        if len(conversation) > self.config.max_conversation_messages_before_compression:
            reasons.append("conversation_message_threshold")
        if len(step_history) > self.config.max_step_history_before_compression:
            reasons.append("step_history_threshold")
        if raw_context_chars > self.config.max_raw_context_chars_before_compression:
            reasons.append("raw_context_size_threshold")
        return bool(reasons), reasons, counters

    def compress(
        self,
        *,
        run_input: dict[str, Any],
        runtime_context: dict[str, Any],
        phase: str,
        force: bool = False,
    ) -> dict[str, Any]:
        conversation = self._safe_list(runtime_context.get("conversation"))
        step_history = self._safe_list(runtime_context.get("step_history"))
        should_compress, reasons, counters = self.should_compress(runtime_context)
        applied = force or should_compress
        if force and "forced" not in reasons:
            reasons = ["forced", *reasons]

        compressed = {
            "protocol_version": self.protocol_version,
            "phase": phase,
            "applied": applied,
            "reasons": reasons,
            "generated_at": self._utc_now(),
            "objective": self._build_objective(run_input, runtime_context),
            "constraints": self._build_constraints(runtime_context),
            "open_questions": self._build_open_questions(runtime_context),
            "decisions": self._build_decisions(step_history),
            "evidence_digest": self._build_evidence_digest(step_history),
            "tool_state": self._build_tool_state(runtime_context, step_history),
            "conversation_digest": self._conversation_digest(conversation),
            "observation_digest": self._observation_digest(step_history),
            "recent_tail": {
                "conversation": self._message_tail(conversation),
                "observations": self._observation_tail(step_history),
            },
            "source_counters": counters,
        }
        runtime_context[COMPRESSED_CONTEXT_KEY] = compressed
        runtime_context[COMPRESSION_STATE_KEY] = {
            "protocol_version": self.protocol_version,
            "applied": applied,
            "phase": phase,
            "reasons": reasons,
            **counters,
            "conversation_tail_count": len(compressed["recent_tail"]["conversation"]),
            "observation_tail_count": len(compressed["recent_tail"]["observations"]),
            "generated_at": compressed["generated_at"],
        }
        runtime_context[PROMPT_CONTEXT_KEY] = self.build_prompt_context(runtime_context)
        return compressed

    def build_prompt_context(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        compressed = self._safe_dict(runtime_context.get(COMPRESSED_CONTEXT_KEY))
        compression_state = self._safe_dict(runtime_context.get(COMPRESSION_STATE_KEY))
        use_compressed = bool(compression_state.get("applied")) and bool(compressed)
        conversation = self._safe_list(runtime_context.get("conversation"))
        step_history = self._safe_list(runtime_context.get("step_history"))

        if use_compressed:
            return {
                "mode": "compressed",
                "compressed_context": compressed,
                "conversation": compressed.get("recent_tail", {}).get("conversation", []),
                "step_history": compressed.get("recent_tail", {}).get("observations", []),
                "intent_state": runtime_context.get("intent_state", {}),
                "ask_user_guard": runtime_context.get("ask_user_guard"),
                "pending_question": runtime_context.get("pending_question"),
            }

        return {
            "mode": "full",
            "compressed_context": compressed,
            "conversation": conversation,
            "step_history": step_history,
            "intent_state": runtime_context.get("intent_state", {}),
            "ask_user_guard": runtime_context.get("ask_user_guard"),
            "pending_question": runtime_context.get("pending_question"),
        }

