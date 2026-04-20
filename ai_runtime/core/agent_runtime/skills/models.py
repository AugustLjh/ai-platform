from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    slug: str
    name: str
    version: str = "1"
    description: str = ""
    root_path: str = ""
    system_prompt: str = ""
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    tool_allowlist: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    contract: Dict[str, Any] = Field(default_factory=dict)


class SkillRuntimeContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    skills: List[SkillDefinition] = Field(default_factory=list)
    system_prompt: str = ""
    tool_allowlist: List[str] = Field(default_factory=list)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
