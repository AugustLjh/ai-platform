package service

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/ai-platform/platform/database"
)

func TestMergeFixedSkillIDsAppendsMissingFixedSkills(t *testing.T) {
	merged := mergeFixedSkillIDs(
		[]string{"custom-skill", "planner-skill"},
		[]string{"planner-skill", "fixed-skill"},
	)

	if len(merged) != 3 {
		t.Fatalf("expected 3 merged skill ids, got %d", len(merged))
	}
	if merged[0] != "custom-skill" || merged[1] != "planner-skill" || merged[2] != "fixed-skill" {
		t.Fatalf("unexpected merge order: %#v", merged)
	}
}

func TestIsFixedSkillUsesMetadataAndPlannerFallback(t *testing.T) {
	if !isFixedSkill(&database.Skill{Slug: "implementation-planner"}) {
		t.Fatal("expected implementation-planner slug to be treated as fixed")
	}

	metadata, err := json.Marshal(map[string]any{"fixed_binding": true})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}
	if !isFixedSkill(&database.Skill{
		Slug:     "custom-skill",
		Metadata: metadata,
	}) {
		t.Fatal("expected metadata.fixed_binding=true to be treated as fixed")
	}

	if isFixedSkill(&database.Skill{Slug: "custom-skill", Metadata: json.RawMessage(`{}`)}) {
		t.Fatal("expected regular skills to remain unbound by default")
	}
}

func TestHydrateSkillContractNormalizesCapabilityPack(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"activation_intents": []string{"Research", "summarize", "research"},
		"activation_phases":  []string{"planning", "output", "output"},
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	skill, err := hydrateSkillContract(&database.Skill{
		Slug:          "kb-research",
		Name:          "KB Research",
		SystemPrompt:  "research prompt",
		OutputSchema:  json.RawMessage(`{"type":"object","properties":{"answer":{"type":"string"}}}`),
		ToolAllowlist: json.RawMessage(`["knowledge_search","knowledge_fetch_document"]`),
		Metadata:      metadata,
	})
	if err != nil {
		t.Fatalf("hydrateSkillContract returned error: %v", err)
	}

	contract, ok := parseJSONRaw(skill.Contract, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected contract object, got %#v", parseJSONRaw(skill.Contract, `{}`))
	}
	if contract["kind"] != "capability_pack" {
		t.Fatalf("expected capability_pack kind, got %#v", contract["kind"])
	}
	if contract["tool_policy_mode"] != "allowlist" {
		t.Fatalf("expected allowlist tool policy, got %#v", contract["tool_policy_mode"])
	}
	if contract["intent_policy"] != "explicit" || contract["phase_policy"] != "explicit" {
		t.Fatalf("expected explicit intent/phase policies, got %#v", contract)
	}

	normalizedMetadata, ok := parseJSONRaw(skill.Metadata, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected normalized metadata map, got %#v", parseJSONRaw(skill.Metadata, `{}`))
	}
	if normalizedMetadata["contract_kind"] != "capability_pack" {
		t.Fatalf("expected metadata.contract_kind=capability_pack, got %#v", normalizedMetadata["contract_kind"])
	}
}

func TestHydrateSkillContractUpgradesInvalidRolePrompt(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"contract_kind":     "role_prompt",
		"activation_phases": []string{"planning", "output"},
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	skill, err := hydrateSkillContract(&database.Skill{
		Slug:         "code-review",
		Name:         "Code Review",
		SystemPrompt: "review prompt",
		OutputSchema: json.RawMessage(`{"type":"object","properties":{"answer":{"type":"string"}}}`),
		Metadata:     metadata,
	})
	if err != nil {
		t.Fatalf("hydrateSkillContract returned error: %v", err)
	}

	contract, ok := parseJSONRaw(skill.Contract, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected contract object, got %#v", parseJSONRaw(skill.Contract, `{}`))
	}
	if contract["kind"] != "capability_pack" {
		t.Fatalf("expected role_prompt conflict to be upgraded to capability_pack, got %#v", contract["kind"])
	}
}

func TestRunStatusNeedsCancellation(t *testing.T) {
	testCases := []struct {
		name   string
		runRef *database.AgentRunReference
		want   bool
	}{
		{name: "nil", runRef: nil, want: false},
		{name: "queued", runRef: &database.AgentRunReference{Status: "queued"}, want: true},
		{name: "running", runRef: &database.AgentRunReference{Status: "running"}, want: true},
		{name: "completed", runRef: &database.AgentRunReference{Status: "completed"}, want: false},
		{name: "waiting_user", runRef: &database.AgentRunReference{Status: "waiting_user"}, want: false},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			if got := runStatusNeedsCancellation(tc.runRef); got != tc.want {
				t.Fatalf("runStatusNeedsCancellation(%+v) = %v, want %v", tc.runRef, got, tc.want)
			}
		})
	}
}

func TestBuildMCPSummaries(t *testing.T) {
	now := time.Date(2026, 3, 31, 12, 0, 0, 0, time.UTC)
	lastTestedAt := now.Add(-10 * time.Minute)
	refreshedAt := now.Add(-30 * time.Minute)
	server := &database.MCPServer{
		ID:           "server-1",
		Name:         "Docs MCP",
		Status:       "active",
		LastTestedAt: &lastTestedAt,
	}
	tools := []*database.MCPServerTool{
		{ToolName: "search_docs", DiscoveredAt: refreshedAt},
		{ToolName: "fetch_page", DiscoveredAt: refreshedAt},
	}

	connection := buildMCPConnectionSummary(server)
	catalog := buildMCPCatalogSummary(server, tools, now)
	availability := buildMCPAvailabilitySummary(server, connection, catalog)

	if connection.Status != "healthy" {
		t.Fatalf("expected healthy connection, got %s", connection.Status)
	}
	if catalog.Status != "ready" || catalog.ToolCount != 2 {
		t.Fatalf("expected ready catalog with 2 tools, got status=%s count=%d", catalog.Status, catalog.ToolCount)
	}
	if availability.Status != "available" || !availability.Bindable {
		t.Fatalf("expected available/bindable server, got status=%s bindable=%v", availability.Status, availability.Bindable)
	}
}

func TestBuildMCPSummariesDetectsStaleAndUnavailableStates(t *testing.T) {
	now := time.Date(2026, 3, 31, 12, 0, 0, 0, time.UTC)
	lastError := "dial tcp: timeout"
	lastTestedAt := now.Add(-5 * time.Minute)
	staleDiscoveredAt := now.Add(-48 * time.Hour)
	server := &database.MCPServer{
		ID:           "server-2",
		Name:         "Failing MCP",
		Status:       "active",
		LastTestedAt: &lastTestedAt,
		LastError:    &lastError,
	}
	tools := []*database.MCPServerTool{
		{ToolName: "old_tool", DiscoveredAt: staleDiscoveredAt},
	}

	connection := buildMCPConnectionSummary(server)
	catalog := buildMCPCatalogSummary(server, tools, now)
	availability := buildMCPAvailabilitySummary(server, connection, catalog)

	if connection.Status != "degraded" {
		t.Fatalf("expected degraded connection, got %s", connection.Status)
	}
	if catalog.Status != "stale" || !catalog.IsStale {
		t.Fatalf("expected stale catalog, got status=%s stale=%v", catalog.Status, catalog.IsStale)
	}
	if availability.Status != "degraded" || availability.Bindable {
		t.Fatalf("expected degraded and not bindable availability, got status=%s bindable=%v", availability.Status, availability.Bindable)
	}
}

func TestBuildMCPBindingUsageSummary(t *testing.T) {
	summary := buildMCPBindingUsageSummary(&database.MCPServer{
		ID:     "server-1",
		Status: "active",
	}, []*database.MCPBindingAgent{
		{AgentID: "agent-1", Name: "Docs Agent", Status: "active"},
		{AgentID: "agent-2", Name: "Review Agent", Status: "disabled"},
	}, 3, 2, 1)

	if summary.AgentCount != 3 {
		t.Fatalf("expected binding count 3, got %d", summary.AgentCount)
	}
	if summary.ActiveAgentCount != 2 || summary.InactiveAgentCount != 1 {
		t.Fatalf("expected active/inactive binding counts 2/1, got %d/%d", summary.ActiveAgentCount, summary.InactiveAgentCount)
	}
	if summary.MoreCount != 1 {
		t.Fatalf("expected more count 1, got %d", summary.MoreCount)
	}
	if summary.Summary != "当前有 3 个 agent 正在使用这个 server。" {
		t.Fatalf("unexpected binding summary: %s", summary.Summary)
	}
	if len(summary.Agents) != 2 {
		t.Fatalf("expected 2 sampled agents, got %d", len(summary.Agents))
	}
}

func TestBuildMCPRecoverySummaryForConnectionFailure(t *testing.T) {
	lastError := "dial tcp: timeout"
	server := &database.MCPServer{
		ID:        "server-1",
		Name:      "Docs MCP",
		Status:    "active",
		LastError: &lastError,
	}
	connection := &database.MCPConnection{Status: "degraded", Error: lastError}
	catalog := &database.MCPCatalog{Status: "ready", ToolCount: 3}
	availability := &database.MCPAvailability{
		Status:   "degraded",
		Bindable: false,
		Reason:   "connection_failed",
	}
	bindingUsage := &database.MCPBindingUsage{
		AgentCount:         4,
		ActiveAgentCount:   3,
		InactiveAgentCount: 1,
	}

	recovery := buildMCPRecoverySummary(server, connection, catalog, availability, bindingUsage)

	if recovery.Status != "blocked" || recovery.Severity != "critical" || !recovery.Recoverable {
		t.Fatalf("unexpected recovery state: %#v", recovery)
	}
	if recovery.FailureMode != "connection_failed" {
		t.Fatalf("expected connection_failed failure mode, got %s", recovery.FailureMode)
	}
	if len(recovery.Actions) != 2 || recovery.Actions[0].Type != "test" || recovery.Actions[1].Type != "refresh" {
		t.Fatalf("expected test then refresh recovery actions, got %#v", recovery.Actions)
	}
	if recovery.Impact.AgentCount != 4 || recovery.Impact.ActiveAgentCount != 3 {
		t.Fatalf("unexpected recovery impact: %#v", recovery.Impact)
	}
}

func TestBuildMCPRecoverySummaryForStaleCatalog(t *testing.T) {
	server := &database.MCPServer{
		ID:     "server-2",
		Name:   "Review MCP",
		Status: "active",
	}
	connection := &database.MCPConnection{Status: "healthy"}
	catalog := &database.MCPCatalog{Status: "stale", ToolCount: 2, IsStale: true}
	availability := &database.MCPAvailability{
		Status:   "warning",
		Bindable: true,
		Reason:   "catalog_stale",
	}
	bindingUsage := &database.MCPBindingUsage{
		AgentCount:       1,
		ActiveAgentCount: 1,
	}

	recovery := buildMCPRecoverySummary(server, connection, catalog, availability, bindingUsage)

	if recovery.Status != "stale" || recovery.Severity != "medium" || recovery.FailureMode != "catalog_stale" {
		t.Fatalf("unexpected stale recovery state: %#v", recovery)
	}
	if len(recovery.Actions) != 1 || recovery.Actions[0].Type != "refresh" {
		t.Fatalf("expected refresh recovery action, got %#v", recovery.Actions)
	}
	if recovery.Impact.Summary != "当前影响 1 个已绑定 agent，且都处于 active 状态。" {
		t.Fatalf("unexpected impact summary: %s", recovery.Impact.Summary)
	}
}

func TestBuildMCPGovernanceSummaryFromHydratedServers(t *testing.T) {
	service := &AgentService{}
	longStaleAge := int64((96 * time.Hour).Seconds())
	shortStaleAge := int64((30 * time.Hour).Seconds())

	summary, err := service.buildMCPGovernanceSummary("tenant-1", []*database.MCPServer{
		{
			ID:     "server-1",
			Name:   "Docs MCP",
			Status: "active",
			Connection: &database.MCPConnection{
				Status:  "degraded",
				Summary: "最近一次连接测试失败。",
			},
			Catalog: &database.MCPCatalog{
				Status:     "ready",
				ToolCount:  3,
				AgeSeconds: func() *int64 { value := int64(120); return &value }(),
			},
			Recovery: &database.MCPRecovery{
				Status:      "blocked",
				FailureMode: "connection_failed",
				Recoverable: true,
			},
			BindingUsage: &database.MCPBindingUsage{
				AgentCount:       4,
				ActiveAgentCount: 3,
			},
		},
		{
			ID:     "server-2",
			Name:   "Review MCP",
			Status: "active",
			Connection: &database.MCPConnection{
				Status:  "healthy",
				Summary: "最近一次连接测试通过。",
			},
			Catalog: &database.MCPCatalog{
				Status:     "stale",
				ToolCount:  2,
				IsStale:    true,
				AgeSeconds: &longStaleAge,
			},
			Recovery: &database.MCPRecovery{
				Status:      "stale",
				FailureMode: "catalog_stale",
				Recoverable: true,
			},
			BindingUsage: &database.MCPBindingUsage{
				AgentCount:       2,
				ActiveAgentCount: 1,
			},
		},
		{
			ID:     "server-3",
			Name:   "New MCP",
			Status: "active",
			Connection: &database.MCPConnection{
				Status:  "untested",
				Summary: "尚未执行连接测试。",
			},
			Catalog: &database.MCPCatalog{
				Status:     "stale",
				ToolCount:  1,
				IsStale:    true,
				AgeSeconds: &shortStaleAge,
			},
			Recovery: &database.MCPRecovery{
				Status:      "verify",
				FailureMode: "connection_untested",
				Recoverable: true,
			},
			BindingUsage: &database.MCPBindingUsage{
				AgentCount:       1,
				ActiveAgentCount: 1,
			},
		},
	}, &MCPGovernanceEventFilters{
		ActionType: "refresh",
		Status:     "failed",
		Limit:      20,
	})
	if err != nil {
		t.Fatalf("buildMCPGovernanceSummary returned error: %v", err)
	}
	if summary.TotalServers != 3 {
		t.Fatalf("expected total servers 3, got %d", summary.TotalServers)
	}
	if summary.RecoveringServers != 3 {
		t.Fatalf("expected 3 recovering servers, got %d", summary.RecoveringServers)
	}
	if summary.BlockedServers != 1 {
		t.Fatalf("expected 1 blocked server, got %d", summary.BlockedServers)
	}
	if summary.StaleServers != 2 {
		t.Fatalf("expected 2 stale servers, got %d", summary.StaleServers)
	}
	if summary.UntestedServers != 1 {
		t.Fatalf("expected 1 untested server, got %d", summary.UntestedServers)
	}
	if summary.ImpactedAgents != 7 || summary.ActiveImpactedAgents != 5 {
		t.Fatalf("unexpected impacted agent counts: total=%d active=%d", summary.ImpactedAgents, summary.ActiveImpactedAgents)
	}
	if len(summary.LongStaleServers) != 1 || summary.LongStaleServers[0].ID != "server-2" {
		t.Fatalf("expected server-2 as the only long stale server, got %#v", summary.LongStaleServers)
	}
	if summary.FailureModeCounts["connection_failed"] != 1 ||
		summary.FailureModeCounts["catalog_stale"] != 1 ||
		summary.FailureModeCounts["connection_untested"] != 1 {
		t.Fatalf("unexpected failure mode counts: %#v", summary.FailureModeCounts)
	}
	if summary.EventFilters == nil || summary.EventFilters.ActionType != "refresh" || summary.EventFilters.Status != "failed" || summary.EventFilters.Limit != 20 {
		t.Fatalf("unexpected event filters: %#v", summary.EventFilters)
	}
}

func TestNormalizeMCPGovernanceEventFilters(t *testing.T) {
	filters := normalizeMCPGovernanceEventFilters(&MCPGovernanceEventFilters{
		ServerID:    " server-1 ",
		ActionType:  " Refresh ",
		Status:      " Failed ",
		FailureMode: " Connection_Failed ",
		Limit:       999,
	})

	if filters.ServerID != "server-1" || filters.ActionType != "refresh" || filters.Status != "failed" || filters.FailureMode != "connection_failed" {
		t.Fatalf("unexpected normalized filters: %#v", filters)
	}
	if filters.Limit != 200 {
		t.Fatalf("expected capped limit 200, got %d", filters.Limit)
	}
}

func TestNormalizeMCPBulkGroupBy(t *testing.T) {
	if got := normalizeMCPBulkGroupBy("failure_mode"); got != "failure_mode" {
		t.Fatalf("expected failure_mode, got %s", got)
	}
	if got := normalizeMCPBulkGroupBy("weird"); got != "none" {
		t.Fatalf("expected fallback none, got %s", got)
	}
}

func TestBuildMCPBulkGroupKey(t *testing.T) {
	server := &database.MCPServer{
		Status:    "disabled",
		Transport: "stdio",
		Recovery:  &database.MCPRecovery{FailureMode: "connection_failed"},
	}
	if got := buildMCPBulkGroupKey(server, "status"); got != "disabled" {
		t.Fatalf("expected disabled group key, got %s", got)
	}
	if got := buildMCPBulkGroupKey(server, "transport"); got != "stdio" {
		t.Fatalf("expected stdio group key, got %s", got)
	}
	if got := buildMCPBulkGroupKey(server, "failure_mode"); got != "connection_failed" {
		t.Fatalf("expected connection_failed group key, got %s", got)
	}
}

func TestSummarizeMCPBindingAgents(t *testing.T) {
	got := summarizeMCPBindingAgents([]*database.MCPBindingAgent{
		{Name: "Planner"},
		{AgentID: "agent-2"},
		nil,
	})

	if got != "Planner, agent-2" {
		t.Fatalf("unexpected binding agent summary: %s", got)
	}
}

func TestMaskSensitiveObjectMasksNestedSecrets(t *testing.T) {
	masked := maskSensitiveObject(map[string]any{
		"server_info": map[string]any{
			"name": "demo",
		},
		"headers": map[string]any{
			"Authorization": "Bearer secret-token",
		},
		"session_token": "abc123",
	}, false)

	headers, ok := masked["headers"].(map[string]any)
	if !ok {
		t.Fatalf("expected headers map after masking, got %#v", masked["headers"])
	}
	if headers["Authorization"] != maskedSecretValue {
		t.Fatalf("expected Authorization to be masked, got %#v", headers["Authorization"])
	}
	if masked["session_token"] != maskedSecretValue {
		t.Fatalf("expected session_token to be masked, got %#v", masked["session_token"])
	}
}

func TestExtractSubagentRuntimeMetadata(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"host_agent_definition_id": "agent-reviewer",
		"handoff_prompt":           "Review with a strict checklist.",
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	targetAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(metadata)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "agent-reviewer" {
		t.Fatalf("expected host agent definition id agent-reviewer, got %s", targetAgentDefinitionID)
	}
	if handoffPrompt != "Review with a strict checklist." {
		t.Fatalf("expected handoff prompt to round-trip, got %s", handoffPrompt)
	}
}

func TestExtractSubagentRuntimeMetadataSupportsLegacyAgentDefinitionIDKey(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"agent_definition_id": "agent-reviewer",
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	targetAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(metadata)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "agent-reviewer" {
		t.Fatalf("expected legacy agent_definition_id to be accepted, got %s", targetAgentDefinitionID)
	}
	if handoffPrompt != "" {
		t.Fatalf("expected empty handoff prompt, got %s", handoffPrompt)
	}
}

func TestExtractSubagentRuntimeMetadataAllowsManagedCapabilityWithoutCompatibilityTarget(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"handoff_prompt": "Use the managed capability contract.",
		"slug":           "managed-reviewer",
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	targetAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(metadata)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "" {
		t.Fatalf("expected no compatibility target agent definition id, got %s", targetAgentDefinitionID)
	}
	if handoffPrompt != "Use the managed capability contract." {
		t.Fatalf("expected handoff prompt to round-trip, got %s", handoffPrompt)
	}
}

func TestMergeSubagentMetadataPreservesRuntimeBridgeAndSlug(t *testing.T) {
	metadata, err := json.Marshal(map[string]any{
		"legacy_setting":             true,
		"target_agent_definition_id": "agent-reviewer",
	})
	if err != nil {
		t.Fatalf("failed to encode metadata: %v", err)
	}

	merged, err := mergeSubagentMetadata(metadata, "managed-reviewer", "agent-reviewer", "Use a strict checklist.")
	if err != nil {
		t.Fatalf("mergeSubagentMetadata returned error: %v", err)
	}

	targetAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(merged)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "agent-reviewer" {
		t.Fatalf("expected host agent definition id to survive merge, got %s", targetAgentDefinitionID)
	}
	if handoffPrompt != "Use a strict checklist." {
		t.Fatalf("expected handoff_prompt to survive merge, got %s", handoffPrompt)
	}
	if extractSubagentSlug(merged) != "managed-reviewer" {
		t.Fatalf("expected slug to be injected, got %s", extractSubagentSlug(merged))
	}
	payload, ok := parseJSONRaw(merged, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected merged metadata object, got %#v", parseJSONRaw(merged, `{}`))
	}
	if _, exists := payload["target_agent_definition_id"]; exists {
		t.Fatal("expected legacy target_agent_definition_id key to be removed during canonicalization")
	}
	if payload["legacy_setting"] != true {
		t.Fatalf("expected unrelated metadata to survive merge, got %#v", payload["legacy_setting"])
	}
}

func TestMergeSubagentMetadataSupportsManagedCapabilityWithoutRuntimeBridge(t *testing.T) {
	merged, err := mergeSubagentMetadata(json.RawMessage(`{"review_required":true}`), "managed-reviewer", "", "")
	if err != nil {
		t.Fatalf("mergeSubagentMetadata returned error: %v", err)
	}

	targetAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(merged)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "" {
		t.Fatalf("expected no target_agent_definition_id, got %s", targetAgentDefinitionID)
	}
	if handoffPrompt != "" {
		t.Fatalf("expected empty handoff prompt, got %s", handoffPrompt)
	}
	if extractSubagentSlug(merged) != "managed-reviewer" {
		t.Fatalf("expected slug to be injected, got %s", extractSubagentSlug(merged))
	}
}

func TestMergeSubagentMetadataCanonicalizesLegacyHostAgentKeyWithoutExplicitOverride(t *testing.T) {
	merged, err := mergeSubagentMetadata(json.RawMessage(`{"target_agent_definition_id":"agent-reviewer"}`), "managed-reviewer", "", "")
	if err != nil {
		t.Fatalf("mergeSubagentMetadata returned error: %v", err)
	}

	targetAgentDefinitionID, _, err := extractSubagentRuntimeMetadata(merged)
	if err != nil {
		t.Fatalf("extractSubagentRuntimeMetadata returned error: %v", err)
	}
	if targetAgentDefinitionID != "agent-reviewer" {
		t.Fatalf("expected legacy target to survive canonicalization, got %s", targetAgentDefinitionID)
	}

	payload, ok := parseJSONRaw(merged, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected merged metadata object, got %#v", parseJSONRaw(merged, `{}`))
	}
	if payload["host_agent_definition_id"] != "agent-reviewer" {
		t.Fatalf("expected canonical host_agent_definition_id key, got %#v", payload["host_agent_definition_id"])
	}
	if _, exists := payload["target_agent_definition_id"]; exists {
		t.Fatal("expected legacy target_agent_definition_id key to be removed")
	}
}

func TestEnsureSubagentAdminRole(t *testing.T) {
	if err := ensureSubagentAdminRole("admin"); err != nil {
		t.Fatalf("expected admin role to be accepted, got %v", err)
	}
	if err := ensureSubagentAdminRole("user"); !errors.Is(err, ErrAgentUnauthorized) {
		t.Fatalf("expected user role to be rejected with ErrAgentUnauthorized, got %v", err)
	}
}
