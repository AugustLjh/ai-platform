"""Stable event-name constants emitted by the agent / chat graphs.

These names are part of the streaming contract observed by the Go platform and
the Vue frontend. Adding new event types is allowed; renaming existing ones
breaks downstream consumers.
"""

RUN_STARTED = "run.started"
RUN_COMPLETED = "run.completed"
RUN_WAITING_USER = "run.waiting_user"
RUN_CANCELLED = "run.cancelled"
RUN_FAILED = "run.failed"

PLAN_CREATED = "plan.created"
PLAN_ASK_USER_REJECTED = "plan.ask_user_rejected"

STEP_STARTED = "step.started"
STEP_COMPLETED = "step.completed"
STEP_FAILED = "step.failed"
STEP_CANCELLED = "step.cancelled"

TOOL_STARTED = "tool.started"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"
TOOL_CANCELLED = "tool.cancelled"

POLICY_REQUESTED = "policy.requested"
POLICY_APPROVED = "policy.approved"
POLICY_DENIED = "policy.denied"

SUBAGENT_STARTED = "subagent.started"
SUBAGENT_COMPLETED = "subagent.completed"
SUBAGENT_WAITING_USER = "subagent.waiting_user"
SUBAGENT_FAILED = "subagent.failed"
SUBAGENT_CANCELLED = "subagent.cancelled"
SUBAGENT_REJECTED = "subagent.rejected"
SUBAGENT_REVIEW_BLOCKED = "subagent.review_blocked"

SKILLS_APPLIED = "skills.applied"
CONTEXT_COMPRESSION_UPDATED = "context.compression.updated"
WORKSPACE_BOUND = "workspace.bound"


from ai_runtime.core.agent_runtime.events import (
    build_event_payload,
    sanitize_runtime_payload,
)

__all__ = [
    "RUN_STARTED",
    "RUN_COMPLETED",
    "RUN_WAITING_USER",
    "RUN_CANCELLED",
    "RUN_FAILED",
    "PLAN_CREATED",
    "PLAN_ASK_USER_REJECTED",
    "STEP_STARTED",
    "STEP_COMPLETED",
    "STEP_FAILED",
    "STEP_CANCELLED",
    "TOOL_STARTED",
    "TOOL_COMPLETED",
    "TOOL_FAILED",
    "TOOL_CANCELLED",
    "POLICY_REQUESTED",
    "POLICY_APPROVED",
    "POLICY_DENIED",
    "SUBAGENT_STARTED",
    "SUBAGENT_COMPLETED",
    "SUBAGENT_WAITING_USER",
    "SUBAGENT_FAILED",
    "SUBAGENT_CANCELLED",
    "SUBAGENT_REJECTED",
    "SUBAGENT_REVIEW_BLOCKED",
    "SKILLS_APPLIED",
    "CONTEXT_COMPRESSION_UPDATED",
    "WORKSPACE_BOUND",
    "build_event_payload",
    "sanitize_runtime_payload",
]
