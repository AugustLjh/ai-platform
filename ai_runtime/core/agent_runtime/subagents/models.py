from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field


SubagentRunStatus = Literal["queued", "running", "waiting_user", "completed", "failed", "cancelled"]


class SubagentTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    slug: str
    name: str
    agent_definition_id: str | None = None
    subagent_definition_id: str | None = None
    publication_id: str | None = None
    version_id: str | None = None
    authorization_id: str | None = None
    description: str | None = None
    handoff_prompt: str | None = None
    system_prompt: str = ""
    model: str | None = None
    config: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    handoff_input_schema: Dict[str, Any] = Field(default_factory=dict)
    tool_allowlist: list[str] = Field(default_factory=list)
    skill_allowlist: list[str] = Field(default_factory=list)
    mcp_allowlist: list[str] = Field(default_factory=list)
    knowledge_policy: Dict[str, Any] = Field(default_factory=dict)
    review_policy: Dict[str, Any] = Field(default_factory=dict)
    runtime_policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def uses_managed_capability(self) -> bool:
        return bool(
            self.publication_id
            or self.version_id
            or self.authorization_id
            or self.subagent_definition_id
            or self.system_prompt.strip()
            or self.config
            or self.output_schema
            or self.tool_allowlist
            or self.skill_allowlist
            or self.mcp_allowlist
            or self.knowledge_policy
            or self.review_policy
            or self.runtime_policy
        )

    def allows_nested_delegation(self) -> bool:
        value = self.runtime_policy.get("allow_delegation")
        if value is None:
            value = self.runtime_policy.get("allow_nested_delegation")
        return bool(value) if value is not None else not self.uses_managed_capability()

    def requires_review(self) -> bool:
        value = self.review_policy.get("required")
        if value is None:
            value = self.review_policy.get("review_required")
        return bool(value)

    def delegation_mode(self) -> str:
        value = (
            self.runtime_policy.get("delegation_mode")
            or self.runtime_policy.get("task_suitability")
            or self.metadata.get("task_suitability")
            or self.metadata.get("delegation_mode")
            or ""
        )
        return str(value).strip().lower()

    def max_delegation_depth(self) -> int | None:
        value = (
            self.runtime_policy.get("max_delegation_depth")
            or self.runtime_policy.get("delegation_depth_limit")
            or self.metadata.get("max_delegation_depth")
        )
        if value in (None, ""):
            return None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return None

    def max_context_observations(self) -> int:
        value = (
            self.runtime_policy.get("max_context_observations")
            or self.runtime_policy.get("context_window_steps")
            or self.metadata.get("max_context_observations")
            or 4
        )
        try:
            return max(1, min(int(value), 12))
        except (TypeError, ValueError):
            return 4


class SubagentDelegationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    child_run_id: str
    status: SubagentRunStatus
    target: SubagentTarget
    input: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    final_output: str | None = None
    final_output_text: str | None = None
    final_output_json: Any = None
    artifacts: list[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
