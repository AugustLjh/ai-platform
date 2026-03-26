from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


RunStatus = Literal["queued", "running", "waiting_user", "completed", "failed", "cancelled"]
StepStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
ToolCallStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
PlannerActionType = Literal["final_answer", "tool_call", "ask_user"]
PlannerStepStatus = Literal["completed", "in_progress", "pending"]


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    system_prompt: str = ""
    model: Optional[str] = None
    status: str = "active"
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentRun(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    agent_definition_id: str
    tenant_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    status: RunStatus
    input: Dict[str, Any] = Field(default_factory=dict)
    plan: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    final_output: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentRunStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    run_id: str
    step_index: int
    title: Optional[str] = None
    kind: str
    status: StepStatus
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentRunEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    run_id: str
    sequence: int
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    run_id: str
    step_id: Optional[str] = None
    tool_name: str
    tool_kind: str = "builtin"
    status: ToolCallStatus
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PlannerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: PlannerActionType
    title: Optional[str] = None
    content: Optional[str] = None
    question: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)


class PlannerStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    kind: str = "analysis"
    status: PlannerStepStatus = "pending"
    details: Optional[str] = None


class PlannerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: PlannerAction
    reasoning: str = ""
    steps: List[PlannerStep] = Field(default_factory=list)
    iteration: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeCreateRunRequest(BaseModel):
    agent_definition_id: str
    input: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    auto_start: bool = True


class RuntimeResumeRunRequest(BaseModel):
    input_patch: Dict[str, Any] = Field(default_factory=dict)


class AgentRunSummaryResponse(BaseModel):
    run: AgentRun


class AgentRunListResponse(BaseModel):
    runs: List[AgentRun]
    total: int


class AgentRunEventListResponse(BaseModel):
    events: List[AgentRunEvent]
    total: int
