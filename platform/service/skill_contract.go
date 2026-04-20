package service

import (
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/ai-platform/platform/database"
)

var allowedSkillPhases = map[string]struct{}{
	"planning":  {},
	"execution": {},
	"synthesis": {},
	"output":    {},
}

var allowedSkillContractKinds = map[string]struct{}{
	"capability_pack": {},
	"role_prompt":     {},
}

func hydrateSkillContract(skill *database.Skill) (*database.Skill, error) {
	if skill == nil {
		return nil, nil
	}

	metadata, ok := parseJSONRaw(skill.Metadata, `{}`).(map[string]any)
	if !ok {
		metadata = map[string]any{}
	}
	contract := buildSkillContract(skill, metadata)
	normalizedMetadata := make(map[string]any, len(metadata)+8)
	for key, value := range metadata {
		normalizedMetadata[key] = value
	}
	normalizedMetadata["contract_kind"] = contract["kind"]
	normalizedMetadata["display_name"] = contract["display_name"]
	if capabilityType := strings.TrimSpace(stringValue(contract["capability_type"])); capabilityType != "" {
		normalizedMetadata["capability_type"] = capabilityType
	}
	normalizedMetadata["activation_intents"] = contract["activation_intents"]
	normalizedMetadata["activation_phases"] = contract["activation_phases"]
	normalizedMetadata["managed_tool_kinds"] = contract["managed_tool_kinds"]
	normalizedMetadata["fixed_binding"] = stringValue(contract["binding_mode"]) == "fixed"
	if boolValue(contract["system_skill"]) {
		normalizedMetadata["system_skill"] = true
	}

	skill.Metadata = database.NormalizeJSONRawForExport(marshalJSONRaw(normalizedMetadata, `{}`), `{}`)
	skill.Contract = database.NormalizeJSONRawForExport(marshalJSONRaw(contract, `{}`), `{}`)
	return skill, nil
}

func buildSkillContract(skill *database.Skill, metadata map[string]any) map[string]any {
	activationIntents := normalizeStringList(metadata["activation_intents"], nil)
	activationPhases := normalizeStringList(metadata["activation_phases"], allowedSkillPhases)
	managedToolKinds := normalizeStringList(metadata["managed_tool_kinds"], nil)
	toolAllowlist := normalizeToolAllowlist(skill.ToolAllowlist)
	outputFieldNames, hasOutputSchema := outputSchemaFieldNames(skill.OutputSchema)
	hasSystemPrompt := strings.TrimSpace(skill.SystemPrompt) != ""
	isSystemSkill := boolValue(metadata["system_skill"])

	requestedKind := normalizeString(metadata["contract_kind"])
	if _, ok := allowedSkillContractKinds[requestedKind]; !ok {
		requestedKind = ""
	}
	derivedKind := requestedKind
	if derivedKind == "" {
		derivedKind = "capability_pack"
	}
	if derivedKind == "role_prompt" && (len(toolAllowlist) > 0 || len(managedToolKinds) > 0 || hasOutputSchema) {
		derivedKind = "capability_pack"
	}

	toolPolicyMode := "inherit"
	if len(managedToolKinds) > 0 {
		toolPolicyMode = "provider_managed"
	} else if len(toolAllowlist) > 0 {
		toolPolicyMode = "allowlist"
	}

	surfaces := make([]string, 0, 3)
	if hasSystemPrompt {
		surfaces = append(surfaces, "prompt")
	}
	if toolPolicyMode != "inherit" {
		surfaces = append(surfaces, "tools")
	}
	if hasOutputSchema {
		surfaces = append(surfaces, "output")
	}

	warnings := make([]string, 0, 4)
	errors := make([]string, 0, 6)
	requirements := make([]string, 0, 6)
	if requestedKind == "role_prompt" && derivedKind != requestedKind {
		warnings = append(warnings, "role_prompt 不能同时声明 tool_allowlist、managed_tool_kinds 或 output_schema，已按 capability_pack 解释。")
	}
	if derivedKind == "role_prompt" && containsAny(activationPhases, "execution", "output") {
		warnings = append(warnings, "role_prompt 通常只应参与 planning/synthesis，当前 phase 配置已超出推荐边界。")
	}
	if derivedKind == "capability_pack" && len(surfaces) == 0 {
		warnings = append(warnings, "capability_pack 没有声明 prompt、tools 或 output surface，契约为空。")
		errors = append(errors, "skill contract 必须至少声明一个执行 surface，当前缺少 prompt、tools 和 output_schema。")
		requirements = append(requirements, "为 capability_pack 至少补一个 surface：system_prompt、tool_allowlist/managed_tool_kinds 或 output_schema。")
	}
	if len(activationIntents) == 0 {
		warnings = append(warnings, "未声明 activation_intents，当前将按所有意图生效。")
		if !isSystemSkill {
			errors = append(errors, "非系统 skill 必须显式声明 activation_intents，避免默认对所有意图生效。")
			requirements = append(requirements, "在 metadata 中声明 activation_intents，限定 skill 的适用意图。")
		}
	}
	if len(activationPhases) == 0 {
		warnings = append(warnings, "未声明 activation_phases，当前将按所有阶段生效。")
		if !isSystemSkill {
			errors = append(errors, "非系统 skill 必须显式声明 activation_phases，避免默认对所有执行阶段生效。")
			requirements = append(requirements, "在 metadata 中声明 activation_phases，限定 skill 的生效阶段。")
		}
	}
	if requestedKind == "" && !isSystemSkill {
		errors = append(errors, "非系统 skill 必须显式声明 contract_kind。")
		requirements = append(requirements, "在 metadata 中声明 contract_kind，明确该 skill 是 capability_pack 还是 role_prompt。")
	}
	if len(managedToolKinds) > 0 && len(toolAllowlist) > 0 {
		errors = append(errors, "skill contract 不能同时声明 managed_tool_kinds 和 tool_allowlist。")
		requirements = append(requirements, "二选一：由 provider 托管工具种类，或显式声明 tool_allowlist。")
	}
	if skillBindingMode(skill, metadata) == "fixed" && !isSystemSkill && !strings.EqualFold(strings.TrimSpace(skill.Slug), fallbackFixedSkillSlug) {
		errors = append(errors, "只有系统 skill 才允许 fixed binding。")
		requirements = append(requirements, "移除 fixed_binding，或把该 skill 明确纳入系统固定能力。")
	}

	capabilityType := strings.TrimSpace(stringValue(metadata["capability_type"]))
	displayName := strings.TrimSpace(stringValue(metadata["display_name"]))
	if displayName == "" {
		displayName = strings.TrimSpace(skill.Name)
	}
	if displayName == "" {
		displayName = strings.TrimSpace(skill.Slug)
	}

	governanceStatus := "ready"
	if len(errors) > 0 {
		governanceStatus = "blocked"
	} else if len(warnings) > 0 {
		governanceStatus = "warning"
	}

	return map[string]any{
		"kind":                    derivedKind,
		"capability_type":         strings.ToLower(capabilityType),
		"display_name":            displayName,
		"binding_mode":            skillBindingMode(skill, metadata),
		"system_skill":            isSystemSkill,
		"activation_intents":      activationIntents,
		"activation_phases":       activationPhases,
		"intent_policy":           ternaryString(len(activationIntents) > 0, "explicit", "all"),
		"phase_policy":            ternaryString(len(activationPhases) > 0, "explicit", "all"),
		"has_system_prompt":       hasSystemPrompt,
		"tool_policy_mode":        toolPolicyMode,
		"managed_tool_kinds":      managedToolKinds,
		"has_output_schema":       hasOutputSchema,
		"output_field_names":      outputFieldNames,
		"surfaces":                surfaces,
		"governance_status":       governanceStatus,
		"governance_errors":       uniqueNonEmptyStrings(errors),
		"governance_warnings":     warnings,
		"governance_requirements": uniqueNonEmptyStrings(requirements),
	}
}

func skillGovernanceStatus(skill *database.Skill) string {
	if skill == nil {
		return ""
	}
	contract, ok := parseJSONRaw(skill.Contract, `{}`).(map[string]any)
	if !ok {
		return ""
	}
	return normalizeString(contract["governance_status"])
}

func validateSkillGovernance(skill *database.Skill) error {
	if skill == nil {
		return errors.New("skill is required")
	}
	hydrated, err := hydrateSkillContract(skill)
	if err != nil {
		return err
	}
	if skillGovernanceStatus(hydrated) != "blocked" {
		return nil
	}
	contract, ok := parseJSONRaw(hydrated.Contract, `{}`).(map[string]any)
	if !ok {
		return errors.New("skill contract governance blocked")
	}
	errorsList := normalizeStringMessages(contract["governance_errors"])
	if len(errorsList) == 0 {
		return fmt.Errorf("skill %s governance blocked", firstNonEmpty(hydrated.Slug, hydrated.Name))
	}
	return fmt.Errorf("skill %s governance blocked: %s", firstNonEmpty(hydrated.Slug, hydrated.Name), strings.Join(errorsList, "；"))
}

func normalizeToolAllowlist(raw json.RawMessage) []string {
	parsed, ok := parseJSONRaw(raw, `[]`).([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(parsed))
	seen := make(map[string]struct{}, len(parsed))
	for _, item := range parsed {
		value := strings.TrimSpace(stringValue(item))
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func normalizeStringList(value any, allowed map[string]struct{}) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	seen := make(map[string]struct{}, len(items))
	for _, item := range items {
		normalized := normalizeString(item)
		if normalized == "" {
			continue
		}
		if len(allowed) > 0 {
			if _, exists := allowed[normalized]; !exists {
				continue
			}
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		result = append(result, normalized)
	}
	return result
}

func normalizeStringMessages(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	seen := make(map[string]struct{}, len(items))
	for _, item := range items {
		message := strings.TrimSpace(stringValue(item))
		if message == "" {
			continue
		}
		if _, exists := seen[message]; exists {
			continue
		}
		seen[message] = struct{}{}
		result = append(result, message)
	}
	return result
}

func outputSchemaFieldNames(raw json.RawMessage) ([]string, bool) {
	schema, ok := parseJSONRaw(raw, `{}`).(map[string]any)
	if !ok || len(schema) == 0 {
		return nil, false
	}
	properties, ok := schema["properties"].(map[string]any)
	if !ok || len(properties) == 0 {
		return nil, true
	}
	result := make([]string, 0, len(properties))
	for key := range properties {
		key = strings.TrimSpace(key)
		if key == "" {
			continue
		}
		result = append(result, key)
	}
	sort.Strings(result)
	return result, true
}

func skillBindingMode(skill *database.Skill, metadata map[string]any) string {
	if strings.EqualFold(strings.TrimSpace(skill.Slug), fallbackFixedSkillSlug) || boolValue(metadata["fixed_binding"]) {
		return "fixed"
	}
	return "optional"
}

func normalizeString(value any) string {
	return strings.ToLower(strings.TrimSpace(stringValue(value)))
}

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return ""
	}
}

func boolValue(value any) bool {
	switch typed := value.(type) {
	case bool:
		return typed
	case string:
		switch normalizeString(typed) {
		case "1", "true", "yes", "on":
			return true
		default:
			return false
		}
	case float64:
		return typed != 0
	case int:
		return typed != 0
	default:
		return false
	}
}

func ternaryString(condition bool, left, right string) string {
	if condition {
		return left
	}
	return right
}

func containsAny(values []string, targets ...string) bool {
	if len(values) == 0 || len(targets) == 0 {
		return false
	}
	set := make(map[string]struct{}, len(values))
	for _, value := range values {
		set[value] = struct{}{}
	}
	for _, target := range targets {
		if _, exists := set[target]; exists {
			return true
		}
	}
	return false
}
