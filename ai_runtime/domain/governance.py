"""Governance state types referenced by graph state and node functions.

For now these are dict-shaped containers; once `core/agent_runtime/tenant_governance.py`
and `core/agent_runtime/policy.py` are repackaged into the `governance/` module
during P6, the canonical Pydantic models land here.
"""
from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field


ExecutionMode = Literal[
    "context_only",
    "read_only_workspace",
    "patch_proposal",
    "sandbox_verified",
    "network_research",
]

ReviewVerdict = Literal["pending", "approved", "rejected", "needs_changes"]


class GovernanceState(BaseModel):
    model_config = ConfigDict(extra="allow")

    delegation_depth: int = 0
    max_delegation_depth: int = 3
    tool_call_budget_remaining: int | None = None
    workspace_bytes_remaining: int | None = None
    tenant_id: str | None = None
    quota: Dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(BaseModel):
    verdict: ReviewVerdict = "pending"
    note: str | None = None
    reviewer_id: str | None = None


__all__ = [
    "ExecutionMode",
    "GovernanceState",
    "ReviewDecision",
    "ReviewVerdict",
]
