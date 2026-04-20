from __future__ import annotations

from ai_runtime.core.agent_runtime.subagents.models import SubagentTarget


def _normalize_match_key(value: str) -> str:
    return "".join(char for char in str(value or "").strip().lower() if char.isalnum())


class SubagentRouter:
    def select_target(self, targets: list[SubagentTarget], requested_target: str | None) -> SubagentTarget:
        if not targets:
            raise ValueError("delegate requested but no subagents are configured")

        requested = str(requested_target or "").strip()
        if not requested:
            if len(targets) == 1:
                return targets[0]
            raise ValueError("delegate requested without delegate_target while multiple subagents are available")

        requested_key = _normalize_match_key(requested)
        for target in targets:
            exact_candidates = {
                target.slug,
                target.name,
                target.agent_definition_id,
                target.subagent_definition_id,
                target.publication_id,
                target.version_id,
                target.authorization_id,
            }
            if requested in exact_candidates:
                return target
            normalized_candidates = {
                _normalize_match_key(target.slug),
                _normalize_match_key(target.name),
                _normalize_match_key(target.agent_definition_id or ""),
                _normalize_match_key(target.subagent_definition_id or ""),
                _normalize_match_key(target.publication_id or ""),
                _normalize_match_key(target.version_id or ""),
                _normalize_match_key(target.authorization_id or ""),
            }
            if requested_key in normalized_candidates:
                return target

        raise ValueError(f"delegate requested unknown subagent target: {requested}")
