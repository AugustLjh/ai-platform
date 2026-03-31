from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

from core.agent_runtime.models import AgentDefinition

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

REFERENCE_MARKERS = (
    "它",
    "他",
    "她",
    "它们",
    "他们",
    "她们",
    "这个",
    "这个问题",
    "这个功能",
    "这个页面",
    "这篇",
    "这条",
    "这些",
    "那個",
    "那个",
    "那些",
    "其",
    "上述",
    "前者",
    "后者",
    "it",
    "this",
    "that",
    "these",
    "those",
    "them",
    "they",
)

SUMMARY_MARKERS = ("总结", "概括", "摘要", "sum up", "summar")
COMPARE_MARKERS = ("对比", "比较", "哪个好", "区别", "compare", "versus", "vs")
RESEARCH_MARKERS = ("最新", "最近", "今天", "搜索", "查一下", "look up", "search", "find")
PLAN_MARKERS = ("怎么做", "方案", "计划", "规划", "plan", "design", "roadmap")
IMPLEMENT_MARKERS = ("实现", "编写", "写代码", "修改", "改一下", "修复", "fix", "implement", "build", "update", "refactor", "code")
REVIEW_MARKERS = ("review", "code review", "审查", "代码审查", "检查改动", "找问题", "找 bug", "找bug")
DECISION_MARKERS = ("你选", "我该选", "帮我选", "which one", "pick one", "choose")


class IntentPreprocessor:
    def _extract_message(self, run_input: Dict[str, Any]) -> str:
        return str(run_input.get("message") or run_input.get("prompt") or "").strip()

    def _extract_json_payload(self, raw_response: str) -> Dict[str, Any]:
        text = (raw_response or "").strip()
        if not text:
            raise ValueError("intent preprocessor returned an empty response")

        candidates: List[str] = [text]
        candidates.extend(match.group(1) for match in JSON_BLOCK_RE.finditer(text))

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidates.append(text[first_brace : last_brace + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise ValueError(f"intent preprocessor did not return valid JSON: {text[:400]}")

    def _recent_messages(self, runtime_context: Dict[str, Any], *, limit: int = 8) -> List[Dict[str, Any]]:
        conversation = runtime_context.get("conversation", [])
        if not isinstance(conversation, Sequence) or isinstance(conversation, (str, bytes, bytearray)):
            return []

        items: List[Dict[str, Any]] = []
        for raw in list(conversation)[-limit:]:
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role") or "").strip()
            content = str(raw.get("content") or "").strip()
            if not role or not content:
                continue
            items.append({"role": role, "content": content})
        return items

    def _find_reference_hints(self, current_message: str, runtime_context: Dict[str, Any]) -> List[Dict[str, str]]:
        lowered = current_message.lower()
        if not any(marker in current_message or marker in lowered for marker in REFERENCE_MARKERS):
            return []

        recent_items = []
        for item in reversed(self._recent_messages(runtime_context, limit=6)):
            if item["content"] == current_message:
                continue
            recent_items.append(item)

        ordered_items = [
            *[item for item in recent_items if item["role"] == "user"],
            *[item for item in recent_items if item["role"] != "user"],
        ]

        hints: List[Dict[str, str]] = []
        for item in ordered_items:
            hints.append(
                {
                    "candidate": item["content"][:280],
                    "role": item["role"],
                }
            )
            if len(hints) >= 3:
                break
        return hints

    def _infer_intent(self, current_message: str) -> str:
        lowered = current_message.lower()
        if any(marker in current_message or marker in lowered for marker in SUMMARY_MARKERS):
            return "summarize"
        if any(marker in current_message or marker in lowered for marker in COMPARE_MARKERS):
            return "compare"
        if any(marker in current_message or marker in lowered for marker in REVIEW_MARKERS):
            return "review"
        if any(marker in current_message or marker in lowered for marker in PLAN_MARKERS):
            return "plan"
        if any(marker in current_message or marker in lowered for marker in IMPLEMENT_MARKERS):
            return "implement"
        if any(marker in current_message or marker in lowered for marker in RESEARCH_MARKERS):
            return "research"
        if any(marker in current_message or marker in lowered for marker in DECISION_MARKERS):
            return "decision"
        return "answer"

    def _fallback_state(
        self,
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_message = self._extract_message(run_input)
        reference_hints = self._find_reference_hints(current_message, runtime_context)
        resolved_references = []
        assumptions: List[str] = []

        if reference_hints:
            resolved_references.append(
                {
                    "mention": "recent reference",
                    "resolved_to": reference_hints[0]["candidate"],
                    "confidence": "medium",
                    "source_role": reference_hints[0]["role"],
                }
            )
            assumptions.append("Use the most recent relevant conversation topic as the omitted reference unless new evidence contradicts it.")

        normalized_message = current_message
        if reference_hints:
            normalized_message = f"{current_message}\n\nResolved context hint: {reference_hints[0]['candidate']}"

        return {
            "normalized_message": normalized_message,
            "inferred_intent": self._infer_intent(current_message),
            "resolved_references": resolved_references,
            "assumptions": assumptions,
            "missing_information": [],
            "blocking_missing_information": [],
            "requires_user_decision": False,
            "should_answer_with_assumptions": True,
            "search_queries": [current_message] if current_message else [],
            "reasoning_summary": "Fallback preprocessing used heuristic intent inference and recent-conversation reference resolution.",
            "reference_hints": reference_hints,
            "preprocess_source": "heuristic_fallback",
        }

    def _normalize_payload(
        self,
        payload: Dict[str, Any],
        *,
        run_input: Dict[str, Any],
        runtime_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._fallback_state(run_input=run_input, runtime_context=runtime_context)

        def _clean_str_list(value: Any) -> List[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        raw_refs = payload.get("resolved_references")
        resolved_references: List[Dict[str, str]] = []
        if isinstance(raw_refs, list):
            for item in raw_refs:
                if not isinstance(item, dict):
                    continue
                mention = str(item.get("mention") or "").strip()
                resolved_to = str(item.get("resolved_to") or "").strip()
                if not mention or not resolved_to:
                    continue
                resolved_references.append(
                    {
                        "mention": mention,
                        "resolved_to": resolved_to,
                        "confidence": str(item.get("confidence") or "medium").strip() or "medium",
                        "source_role": str(item.get("source_role") or "").strip(),
                    }
                )

        normalized_message = str(payload.get("normalized_message") or "").strip() or fallback["normalized_message"]
        inferred_intent = str(payload.get("inferred_intent") or "").strip() or fallback["inferred_intent"]
        assumptions = _clean_str_list(payload.get("assumptions")) or fallback["assumptions"]
        missing_information = _clean_str_list(payload.get("missing_information"))
        blocking_missing_information = _clean_str_list(payload.get("blocking_missing_information"))
        search_queries = _clean_str_list(payload.get("search_queries")) or fallback["search_queries"]

        requires_user_decision = bool(payload.get("requires_user_decision"))
        should_answer_with_assumptions = bool(
            payload.get("should_answer_with_assumptions")
            if payload.get("should_answer_with_assumptions") is not None
            else True
        )
        reasoning_summary = str(payload.get("reasoning_summary") or "").strip() or fallback["reasoning_summary"]

        return {
            "normalized_message": normalized_message,
            "inferred_intent": inferred_intent,
            "resolved_references": resolved_references or fallback["resolved_references"],
            "assumptions": assumptions,
            "missing_information": missing_information,
            "blocking_missing_information": blocking_missing_information,
            "requires_user_decision": requires_user_decision,
            "should_answer_with_assumptions": should_answer_with_assumptions,
            "search_queries": search_queries,
            "reasoning_summary": reasoning_summary,
            "reference_hints": fallback["reference_hints"],
            "preprocess_source": "llm",
        }

    def _build_system_prompt(self, *, definition: AgentDefinition, available_tools: List[Dict[str, Any]]) -> str:
        return "\n\n".join(
            [
                "You are the intent analysis and task-normalization layer for an autonomous agent.",
                "Resolve user intent, omitted subjects, shorthand references, and reasonable defaults before the planner runs.",
                "Use recent conversation to resolve pronouns, omitted objects, and deictic references whenever the inference is reasonable.",
                "Do not turn ordinary ambiguity into a blocking clarification question.",
                "If the request can proceed under reasonable assumptions, set should_answer_with_assumptions=true and keep blocking_missing_information empty.",
                "Mark blocking_missing_information only when the user must provide a choice, permission, credential, or target that cannot be inferred safely.",
                "Be aggressive about reference resolution and conservative about asking the user.",
                "Return JSON only.",
                "JSON schema:",
                json.dumps(
                    {
                        "normalized_message": "task rewritten as a self-contained request",
                        "inferred_intent": "answer|research|compare|summarize|plan|implement|review|decision",
                        "resolved_references": [
                            {
                                "mention": "the omitted or pronoun reference",
                                "resolved_to": "best resolved entity or topic",
                                "confidence": "high|medium|low",
                                "source_role": "user|assistant",
                            }
                        ],
                        "assumptions": ["reasonable assumption used to proceed"],
                        "missing_information": ["non-blocking gaps that can be handled by assumptions or tools"],
                        "blocking_missing_information": ["only truly blocking gaps"],
                        "requires_user_decision": False,
                        "should_answer_with_assumptions": True,
                        "search_queries": ["useful search or retrieval query"],
                        "reasoning_summary": "brief explanation",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "Available tools:",
                json.dumps(available_tools, ensure_ascii=False, indent=2),
                "Agent instructions:",
                definition.system_prompt.strip() or "No extra agent instructions.",
            ]
        )

    def _build_user_prompt(self, *, run_input: Dict[str, Any], runtime_context: Dict[str, Any]) -> str:
        current_message = self._extract_message(run_input)
        reference_hints = self._find_reference_hints(current_message, runtime_context)
        payload = {
            "task_input": run_input,
            "recent_conversation": self._recent_messages(runtime_context, limit=8),
            "reference_hints": reference_hints,
            "current_message": current_message,
        }
        return (
            "Normalize the request for downstream planning.\n"
            "Prefer proceeding with assumptions and resolved references instead of marking the request as blocked.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    async def preprocess(
        self,
        definition: AgentDefinition,
        run_input: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
        *,
        runtime_context: Dict[str, Any],
        llm_service,
        llm_resolution: Dict[str, Any],
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    definition=definition,
                    available_tools=available_tools,
                ),
            },
            {
                "role": "user",
                "content": self._build_user_prompt(
                    run_input=run_input,
                    runtime_context=runtime_context,
                ),
            },
        ]

        try:
            raw_response, model_info = await llm_service.chat_with_candidates(
                llm_resolution,
                messages,
                temperature=0.1,
                max_tokens=1200,
            )
            payload = self._extract_json_payload(raw_response)
            normalized = self._normalize_payload(
                payload,
                run_input=run_input,
                runtime_context=runtime_context,
            )
            normalized["model_info"] = model_info
            normalized["raw_response"] = raw_response
            return normalized
        except Exception:
            return self._fallback_state(
                run_input=run_input,
                runtime_context=runtime_context,
            )
