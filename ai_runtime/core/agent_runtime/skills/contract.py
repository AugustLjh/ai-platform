from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, ConfigDict, Field


ALLOWED_SKILL_PHASES = ("planning", "execution", "synthesis", "output")
ALLOWED_SKILL_CONTRACT_KINDS = ("capability_pack", "role_prompt")


def _normalize_slug(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_string_list(
    value: Any,
    *,
    allowed: Iterable[str] | None = None,
) -> List[str]:
    allowed_values = {_normalize_slug(item) for item in allowed or [] if _normalize_slug(item)}
    result: List[str] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return result
    for item in value:
        normalized = _normalize_slug(item)
        if not normalized:
            continue
        if allowed_values and normalized not in allowed_values:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _normalize_slug(value) in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


class SkillContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str = "capability_pack"
    capability_type: str = ""
    display_name: str = ""
    binding_mode: str = "optional"
    system_skill: bool = False
    activation_intents: List[str] = Field(default_factory=list)
    activation_phases: List[str] = Field(default_factory=list)
    intent_policy: str = "all"
    phase_policy: str = "all"
    has_system_prompt: bool = False
    tool_policy_mode: str = "inherit"
    managed_tool_kinds: List[str] = Field(default_factory=list)
    has_output_schema: bool = False
    output_field_names: List[str] = Field(default_factory=list)
    surfaces: List[str] = Field(default_factory=list)
    governance_status: str = "ready"
    governance_errors: List[str] = Field(default_factory=list)
    governance_warnings: List[str] = Field(default_factory=list)
    governance_requirements: List[str] = Field(default_factory=list)


def derive_skill_contract(
    *,
    slug: str,
    name: str,
    system_prompt: str,
    output_schema: Dict[str, Any] | None,
    tool_allowlist: List[str] | None,
    metadata: Dict[str, Any] | None,
) -> SkillContract:
    metadata = metadata if isinstance(metadata, dict) else {}
    normalized_slug = _normalize_slug(slug)
    managed_tool_kinds = _normalize_string_list(metadata.get("managed_tool_kinds"))
    normalized_tool_allowlist = [str(item).strip() for item in tool_allowlist or [] if str(item).strip()]
    has_system_prompt = bool(str(system_prompt or "").strip())
    has_output_schema = isinstance(output_schema, dict) and bool(output_schema)
    system_skill = _coerce_bool(metadata.get("system_skill"))
    output_field_names = []
    if isinstance(output_schema, dict) and isinstance(output_schema.get("properties"), dict):
        output_field_names = sorted(str(key) for key in output_schema["properties"].keys() if str(key).strip())

    requested_kind = _normalize_slug(metadata.get("contract_kind"))
    if requested_kind not in ALLOWED_SKILL_CONTRACT_KINDS:
        requested_kind = ""

    derived_kind = requested_kind or "capability_pack"
    if derived_kind == "role_prompt" and (normalized_tool_allowlist or managed_tool_kinds or has_output_schema):
        derived_kind = "capability_pack"

    activation_intents = _normalize_string_list(metadata.get("activation_intents"))
    activation_phases = _normalize_string_list(
        metadata.get("activation_phases"),
        allowed=ALLOWED_SKILL_PHASES,
    )

    capability_type = str(metadata.get("capability_type") or "").strip().lower()
    display_name = str(metadata.get("display_name") or name or slug or "").strip()
    fixed_binding = _coerce_bool(metadata.get("fixed_binding")) or normalized_slug == "implementation-planner"

    tool_policy_mode = "inherit"
    if managed_tool_kinds:
        tool_policy_mode = "provider_managed"
    elif normalized_tool_allowlist:
        tool_policy_mode = "allowlist"

    surfaces: List[str] = []
    if has_system_prompt:
        surfaces.append("prompt")
    if tool_policy_mode != "inherit":
        surfaces.append("tools")
    if has_output_schema:
        surfaces.append("output")

    governance_warnings: List[str] = []
    governance_errors: List[str] = []
    governance_requirements: List[str] = []
    if requested_kind == "role_prompt" and derived_kind != requested_kind:
        governance_warnings.append(
            "role_prompt 不能同时声明 tool_allowlist、managed_tool_kinds 或 output_schema，已按 capability_pack 解释。"
        )
    if derived_kind == "role_prompt" and activation_phases and any(phase in {"execution", "output"} for phase in activation_phases):
        governance_warnings.append("role_prompt 通常只应参与 planning/synthesis，当前 phase 配置已超出推荐边界。")
    if derived_kind == "capability_pack" and not surfaces:
        governance_warnings.append("capability_pack 没有声明 prompt、tools 或 output surface，契约为空。")
        governance_errors.append("skill contract 必须至少声明一个执行 surface，当前缺少 prompt、tools 和 output_schema。")
        governance_requirements.append("为 capability_pack 至少补一个 surface：system_prompt、tool_allowlist/managed_tool_kinds 或 output_schema。")
    if not activation_intents:
        governance_warnings.append("未声明 activation_intents，当前将按所有意图生效。")
        if not system_skill:
            governance_errors.append("非系统 skill 必须显式声明 activation_intents，避免默认对所有意图生效。")
            governance_requirements.append("在 metadata 中声明 activation_intents，限定 skill 的适用意图。")
    if not activation_phases:
        governance_warnings.append("未声明 activation_phases，当前将按所有阶段生效。")
        if not system_skill:
            governance_errors.append("非系统 skill 必须显式声明 activation_phases，避免默认对所有执行阶段生效。")
            governance_requirements.append("在 metadata 中声明 activation_phases，限定 skill 的生效阶段。")
    if not requested_kind and not system_skill:
        governance_errors.append("非系统 skill 必须显式声明 contract_kind。")
        governance_requirements.append("在 metadata 中声明 contract_kind，明确该 skill 是 capability_pack 还是 role_prompt。")
    if managed_tool_kinds and normalized_tool_allowlist:
        governance_errors.append("skill contract 不能同时声明 managed_tool_kinds 和 tool_allowlist。")
        governance_requirements.append("二选一：由 provider 托管工具种类，或显式声明 tool_allowlist。")
    if fixed_binding and not system_skill and normalized_slug != "implementation-planner":
        governance_errors.append("只有系统 skill 才允许 fixed binding。")
        governance_requirements.append("移除 fixed_binding，或把该 skill 明确纳入系统固定能力。")

    governance_status = "ready"
    if governance_errors:
        governance_status = "blocked"
    elif governance_warnings:
        governance_status = "warning"

    return SkillContract(
        kind=derived_kind,
        capability_type=capability_type,
        display_name=display_name or name or slug,
        binding_mode="fixed" if fixed_binding else "optional",
        system_skill=system_skill,
        activation_intents=activation_intents,
        activation_phases=activation_phases,
        intent_policy="explicit" if activation_intents else "all",
        phase_policy="explicit" if activation_phases else "all",
        has_system_prompt=has_system_prompt,
        tool_policy_mode=tool_policy_mode,
        managed_tool_kinds=managed_tool_kinds,
        has_output_schema=has_output_schema,
        output_field_names=output_field_names,
        surfaces=surfaces,
        governance_status=governance_status,
        governance_errors=list(dict.fromkeys(governance_errors)),
        governance_warnings=governance_warnings,
        governance_requirements=list(dict.fromkeys(governance_requirements)),
    )


def apply_skill_contract(skill) -> Any:
    metadata = skill.metadata if isinstance(skill.metadata, dict) else {}
    contract = derive_skill_contract(
        slug=skill.slug,
        name=skill.name,
        system_prompt=skill.system_prompt,
        output_schema=skill.output_schema,
        tool_allowlist=skill.tool_allowlist,
        metadata=metadata,
    )

    normalized_metadata = dict(metadata)
    normalized_metadata["contract_kind"] = contract.kind
    normalized_metadata["display_name"] = contract.display_name
    if contract.capability_type:
        normalized_metadata["capability_type"] = contract.capability_type
    normalized_metadata["activation_intents"] = contract.activation_intents
    normalized_metadata["activation_phases"] = contract.activation_phases
    normalized_metadata["managed_tool_kinds"] = contract.managed_tool_kinds
    normalized_metadata["fixed_binding"] = contract.binding_mode == "fixed"
    if contract.system_skill:
        normalized_metadata["system_skill"] = True

    return skill.model_copy(
        update={
            "metadata": normalized_metadata,
            "contract": contract.model_dump(mode="json"),
        }
    )
