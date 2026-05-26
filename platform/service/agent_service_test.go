package service

import (
	"encoding/json"
	"errors"
	"strings"
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

func TestHydrateSkillContractBlocksNonSystemSkillWithoutExplicitGovernance(t *testing.T) {
	skill, err := hydrateSkillContract(&database.Skill{
		Slug:         "custom-review",
		Name:         "Custom Review",
		SystemPrompt: "review prompt",
	})
	if err != nil {
		t.Fatalf("hydrateSkillContract returned error: %v", err)
	}

	contract, ok := parseJSONRaw(skill.Contract, `{}`).(map[string]any)
	if !ok {
		t.Fatalf("expected contract object, got %#v", parseJSONRaw(skill.Contract, `{}`))
	}
	if contract["governance_status"] != "blocked" {
		t.Fatalf("expected blocked governance status, got %#v", contract["governance_status"])
	}
	errorsList := normalizeStringMessages(contract["governance_errors"])
	if len(errorsList) < 2 {
		t.Fatalf("expected governance errors to be populated, got %#v", contract["governance_errors"])
	}
}

func TestValidateSkillGovernanceRejectsBlockedSkill(t *testing.T) {
	err := validateSkillGovernance(&database.Skill{
		Slug:         "custom-review",
		Name:         "Custom Review",
		SystemPrompt: "review prompt",
	})
	if err == nil {
		t.Fatal("expected blocked skill governance to be rejected")
	}
	if !strings.Contains(err.Error(), "governance blocked") {
		t.Fatalf("expected governance blocked error, got %v", err)
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

func TestBuildMCPSecurityScoreAndAuditReport(t *testing.T) {
	now := time.Date(2026, 5, 18, 12, 0, 0, 0, time.UTC)
	server := &database.MCPServer{
		ID:        "server-1",
		TenantID:  "tenant-1",
		Name:      "Docs MCP",
		Transport: "http",
		Endpoint:  "http://example.com/mcp",
		Status:    "active",
		Connection: &database.MCPConnection{
			Status: "degraded",
		},
		Catalog: &database.MCPCatalog{
			Status:    "stale",
			ToolCount: 2,
			IsStale:   true,
		},
		BindingUsage: &database.MCPBindingUsage{
			AgentCount:       4,
			ActiveAgentCount: 3,
		},
		Recovery: &database.MCPRecovery{
			Status:      "blocked",
			FailureMode: "connection_failed",
			Recoverable: true,
		},
		Env:      json.RawMessage(`{"API_KEY":"secret"}`),
		Metadata: json.RawMessage(`{"headers":{"Authorization":"Bearer secret"}}`),
		Events: []*database.MCPServerEvent{
			{Status: "failed", ActionType: "test", FailureMode: "connection_failed"},
			{Status: "succeeded", ActionType: "refresh", FailureMode: "catalog_stale"},
		},
	}

	score := buildMCPSecurityScore(server, []*database.MCPServerTool{{ToolName: "tool-a"}, {ToolName: "tool-b"}}, now)
	if score == nil || score.Score == 0 {
		t.Fatalf("expected security score, got %#v", score)
	}
	if score.RiskLevel != "critical" {
		t.Fatalf("expected critical risk, got %#v", score)
	}
	if len(score.Breakdown) != 5 {
		t.Fatalf("expected 5 score breakdown items, got %#v", score.Breakdown)
	}
	server.SecurityScore = score

	report := buildMCPAuditReportFromHydratedServers("tenant-1", []*database.MCPServer{server}, []*database.MCPServerEvent{
		{Status: "failed", ActionType: "test", FailureMode: "connection_failed"},
	}, 5, now)
	if report.Overview.TotalServers != 1 {
		t.Fatalf("expected one server in report, got %#v", report.Overview)
	}
	if report.Overview.CriticalRiskCount != 1 {
		t.Fatalf("expected critical risk count 1, got %#v", report.Overview)
	}
	if len(report.RecommendedActions) == 0 {
		t.Fatalf("expected recommended actions, got %#v", report)
	}
}

func TestBuildMCPBulkPreviewOrdersByImpactAndSeverity(t *testing.T) {
	candidates := []mcpBulkServerCandidate{
		{server: &database.MCPServer{
			ID:   "server-low",
			Name: "Low Impact",
			Recovery: &database.MCPRecovery{
				Status:      "stale",
				Summary:     "catalog stale",
				FailureMode: "catalog_stale",
				Actions: []*database.MCPRecoveryAction{
					{Type: "refresh", Label: "刷新 Catalog", Priority: "medium"},
				},
				Impact: &database.MCPRecoveryImpact{
					AgentCount:       1,
					ActiveAgentCount: 1,
					Summary:          "影响 1 个 agent。",
				},
			},
		}, order: 1},
		{server: &database.MCPServer{
			ID:   "server-high",
			Name: "High Impact",
			Recovery: &database.MCPRecovery{
				Status:      "blocked",
				Summary:     "connection failed",
				FailureMode: "connection_failed",
				Actions: []*database.MCPRecoveryAction{
					{Type: "test", Label: "测试连接", Priority: "high"},
					{Type: "refresh", Label: "刷新 Catalog", Priority: "medium"},
				},
				Impact: &database.MCPRecoveryImpact{
					AgentCount:       4,
					ActiveAgentCount: 3,
					Summary:          "影响 4 个 agent，其中 3 个 active。",
				},
			},
		}, order: 2},
	}
	recommendations := []*MCPServerBulkActionRecommendation{
		buildMCPBulkRecommendation(candidates[0].server, "refresh", 2),
		buildMCPBulkRecommendation(candidates[1].server, "test", 1),
	}

	preview, payload, err := buildMCPBulkPreview("test", true, "failure_mode", 5, 1, time.Date(2026, 4, 15, 10, 0, 0, 0, time.UTC), candidates, recommendations)
	if err != nil {
		t.Fatalf("buildMCPBulkPreview returned error: %v", err)
	}
	if preview == nil || payload == nil {
		t.Fatal("expected preview to be built")
	}
	if !preview.PreviewOnly {
		t.Fatal("expected preview_only to round-trip")
	}
	if preview.PreviewToken == "" {
		t.Fatal("expected preview token to be generated")
	}
	if !preview.RequiresConfirmation {
		t.Fatal("expected preview to require confirmation for high-impact actions")
	}
	if !strings.Contains(preview.RiskSummary, "4 个已绑定 agent") && !strings.Contains(preview.RiskSummary, "5 个已绑定 agent") {
		t.Fatalf("unexpected risk summary: %s", preview.RiskSummary)
	}
	if preview.Recommendations[0].ServerID != "server-low" {
		t.Fatalf("preview should preserve supplied order, got %#v", preview.Recommendations)
	}
	if len(payload.ServerStateSnapshots) != 2 {
		t.Fatalf("expected 2 state snapshots, got %#v", payload.ServerStateSnapshots)
	}
}

func TestBuildMCPBulkFollowUpPlanSummarizesFailedAndRecoveryStages(t *testing.T) {
	plan := buildMCPBulkFollowUpPlan([]*MCPServerBulkActionResult{
		{
			ServerID:       "server-1",
			OK:             false,
			Action:         "enable",
			RecoveryStatus: "blocked",
			ImpactSummary:  "当前影响 3 个已绑定 agent，其中 2 个处于 active 状态。",
			SuggestedFollowUps: []*database.MCPRecoveryAction{
				{Type: "test", Label: "重新测试连接", Priority: "high"},
			},
		},
		{
			ServerID:       "server-2",
			OK:             true,
			RecoveryStatus: "stale",
			SuggestedFollowUps: []*database.MCPRecoveryAction{
				{Type: "refresh", Label: "刷新 Catalog", Priority: "medium"},
			},
		},
	}, nil)

	if plan == nil {
		t.Fatal("expected follow-up plan")
	}
	if plan.Status != "needs_follow_up" {
		t.Fatalf("expected needs_follow_up status, got %#v", plan)
	}
	if len(plan.FailedServerIDs) != 1 || plan.FailedServerIDs[0] != "server-1" {
		t.Fatalf("unexpected failed server ids: %#v", plan.FailedServerIDs)
	}
	if len(plan.RecoveryStageCounts) < 2 {
		t.Fatalf("expected multiple recovery stages, got %#v", plan.RecoveryStageCounts)
	}
	if len(plan.RecommendedActions) == 0 {
		t.Fatalf("expected recommended actions, got %#v", plan)
	}
	if !plan.RequiresManualReview || plan.ManualReviewReason == "" {
		t.Fatalf("expected manual review guidance, got %#v", plan)
	}
	if len(plan.CompensationActions) == 0 {
		t.Fatalf("expected compensation actions, got %#v", plan)
	}
	if len(plan.RollbackActions) == 0 {
		t.Fatalf("expected rollback actions, got %#v", plan)
	}
}

func TestUpdateMCPBulkResultFromServerCarriesFollowUps(t *testing.T) {
	result := &MCPServerBulkActionResult{Action: "test"}
	server := &database.MCPServer{
		ID:   "server-1",
		Name: "Docs MCP",
		Recovery: &database.MCPRecovery{
			Status:      "blocked",
			FailureMode: "connection_failed",
			Actions: []*database.MCPRecoveryAction{
				{Type: "test", Label: "重新测试连接", Priority: "high"},
				{Type: "refresh", Label: "连接恢复后刷新 Catalog", Priority: "medium"},
			},
			Impact: &database.MCPRecoveryImpact{
				Summary: "当前影响 3 个已绑定 agent。",
			},
		},
	}

	updated := updateMCPBulkResultFromServer(result, server, "test")
	if updated.ServerID != "server-1" || updated.ServerName != "Docs MCP" {
		t.Fatalf("unexpected result identity: %#v", updated)
	}
	if updated.FailureMode != "connection_failed" || updated.RecoveryStatus != "blocked" {
		t.Fatalf("unexpected recovery snapshot: %#v", updated)
	}
	if len(updated.SuggestedFollowUps) != 1 || updated.SuggestedFollowUps[0].Type != "refresh" {
		t.Fatalf("expected refresh follow-up after test action, got %#v", updated.SuggestedFollowUps)
	}
	if updated.ImpactSummary != "当前影响 3 个已绑定 agent。" {
		t.Fatalf("unexpected impact summary: %s", updated.ImpactSummary)
	}
}

func TestEncodeDecodeMCPBulkPreviewTokenRoundTrip(t *testing.T) {
	payload := &mcpBulkPreviewTokenPayload{
		Action:            "refresh",
		GroupBy:           "failure_mode",
		MaxBatchSize:      3,
		RetryFailed:       1,
		GeneratedAt:       time.Date(2026, 4, 15, 11, 0, 0, 0, time.UTC),
		ConfirmedRequired: true,
		SelectedServerIDs: []string{"server-1", "server-2"},
		ServerStateSnapshots: []*mcpBulkPreviewStateSnapshot{
			{ServerID: "server-1", Signature: "sig-1"},
		},
	}

	token, err := encodeMCPBulkPreviewToken(payload)
	if err != nil {
		t.Fatalf("encodeMCPBulkPreviewToken returned error: %v", err)
	}
	decoded, err := decodeMCPBulkPreviewToken(token)
	if err != nil {
		t.Fatalf("decodeMCPBulkPreviewToken returned error: %v", err)
	}
	if decoded.Action != payload.Action || decoded.GroupBy != payload.GroupBy || decoded.MaxBatchSize != payload.MaxBatchSize {
		t.Fatalf("unexpected decoded payload: %#v", decoded)
	}
}

func TestValidateMCPBulkPreviewTokenRejectsParameterMismatch(t *testing.T) {
	generatedAt := time.Now().UTC()
	tokenPayload := &mcpBulkPreviewTokenPayload{
		Action:            "test",
		GroupBy:           "status",
		MaxBatchSize:      2,
		RetryFailed:       1,
		GeneratedAt:       generatedAt,
		SelectedServerIDs: []string{"server-1"},
	}
	currentPayload := &mcpBulkPreviewTokenPayload{
		Action:            "test",
		GroupBy:           "status",
		MaxBatchSize:      2,
		RetryFailed:       1,
		GeneratedAt:       generatedAt,
		SelectedServerIDs: []string{"server-1"},
	}

	err := validateMCPBulkPreviewToken(tokenPayload, currentPayload, "refresh", "status", 2, 1, []string{"server-1"})
	if err == nil {
		t.Fatal("expected parameter mismatch to be rejected")
	}
}

func TestDetectMCPBulkPreviewDriftReturnsChangedServers(t *testing.T) {
	server := &database.MCPServer{
		ID:        "server-1",
		Name:      "Docs MCP",
		Status:    "active",
		UpdatedAt: time.Date(2026, 4, 15, 11, 0, 0, 0, time.UTC),
		Recovery:  &database.MCPRecovery{Status: "stale", FailureMode: "catalog_stale", Recoverable: true},
		Catalog:   &database.MCPCatalog{Status: "stale", ToolCount: 2, IsStale: true},
	}
	tokenPayload := &mcpBulkPreviewTokenPayload{
		ServerStateSnapshots: []*mcpBulkPreviewStateSnapshot{
			{ServerID: "server-1", ServerName: "Docs MCP", Signature: "old-signature"},
		},
	}

	drifted := detectMCPBulkPreviewDrift(tokenPayload, []mcpBulkServerCandidate{{server: server}})
	if len(drifted) != 1 || drifted[0] != "Docs MCP" {
		t.Fatalf("expected Docs MCP to be reported as drifted, got %#v", drifted)
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

func TestMaskSensitiveStringSanitizesEmbeddedSecrets(t *testing.T) {
	message := `request failed for https://user:pass@example.com/mcp?api_key=top-secret&mode=demo with Authorization: Bearer secret-token and password=hunter2`

	masked := maskSensitiveString(message)

	if strings.Contains(masked, "user:pass@") || strings.Contains(masked, "https://user") {
		t.Fatalf("expected userinfo to be masked, got %s", masked)
	}
	if strings.Contains(masked, "top-secret") || strings.Contains(masked, "secret-token") || strings.Contains(masked, "hunter2") {
		t.Fatalf("expected secrets to be masked, got %s", masked)
	}
	if strings.Contains(masked, "Authorization: ******** ********") == false {
		t.Fatalf("expected authorization token to be masked, got %s", masked)
	}
	if !strings.Contains(masked, "mode=demo") || !strings.Contains(masked, maskedSecretValue) {
		t.Fatalf("expected non-sensitive query items to survive and secrets to be masked, got %s", masked)
	}
}

func TestRecordMCPBulkActionAuditEventStoresPreviewTokenFingerprintOnly(t *testing.T) {
	preview := &MCPServerBulkActionPreview{
		Action:            "refresh",
		OrderedBy:         "impact_and_recovery",
		PreviewToken:      "secret-preview-token",
		SelectedServerIDs: []string{"server-1"},
		RiskSummary:       "risk summary",
	}
	details := map[string]any{
		"preview_token_fingerprint": fingerprintSensitiveToken(preview.PreviewToken),
		"preview_token":             preview.PreviewToken,
	}
	masked := maskSensitiveObject(details, false)

	if masked["preview_token"] != maskedSecretValue {
		t.Fatalf("expected preview token to be masked, got %#v", masked["preview_token"])
	}
	if masked["preview_token_fingerprint"] == "" || masked["preview_token_fingerprint"] == maskedSecretValue {
		t.Fatalf("expected preview token fingerprint to survive, got %#v", masked["preview_token_fingerprint"])
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

func TestBuildSubagentPublicationChangePreviewRequiresConfirmationForRollback(t *testing.T) {
	controlPlane := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:                    "subagent-1",
			PublicationScope:      "tenant",
			PublicationTenantID:   "tenant-1",
			HostAgentDefinitionID: "host-1",
		},
		Publication: &database.SubagentPublicationState{
			VersionID:        "version-3",
			VersionNumber:    3,
			Status:           "active",
			PublicationScope: "tenant",
			TenantID:         "tenant-1",
		},
		Authorizations: []*database.SubagentAuthorizedAgent{
			{AuthorizationID: "auth-1", AgentDefinitionID: "agent-1", AgentName: "Planner", AgentStatus: "active", Status: "enabled"},
			{AuthorizationID: "auth-2", AgentDefinitionID: "agent-2", AgentName: "Reviewer", AgentStatus: "active", Status: "enabled"},
		},
		Governance: &database.SubagentGovernanceSummary{
			CompatibilityMode: true,
		},
	}

	preview := buildSubagentPublicationChangePreview(controlPlane, &database.SubagentDefinitionVersion{
		ID:            "version-2",
		VersionNumber: 2,
	}, "tenant", "active")
	if preview == nil {
		t.Fatal("expected preview to be built")
	}
	if preview.ChangeType != "rollback" {
		t.Fatalf("expected rollback change type, got %s", preview.ChangeType)
	}
	if preview.RiskLevel != "high" || !preview.RequiresConfirmation {
		t.Fatalf("expected high-risk confirmed rollback preview, got %#v", preview)
	}
	if preview.EnabledAuthorizationCount != 2 {
		t.Fatalf("expected enabled authorization count 2, got %d", preview.EnabledAuthorizationCount)
	}
	if len(preview.RecommendedActions) == 0 {
		t.Fatal("expected rollback recommended actions")
	}
}

func TestBuildSubagentPublicationChangePreviewAllowsLowRiskMetadataUpdate(t *testing.T) {
	controlPlane := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:                  "subagent-1",
			PublicationScope:    "tenant",
			PublicationTenantID: "tenant-1",
		},
		Publication: &database.SubagentPublicationState{
			VersionID:        "version-1",
			VersionNumber:    1,
			Status:           "active",
			PublicationScope: "tenant",
			TenantID:         "tenant-1",
		},
	}

	preview := buildSubagentPublicationChangePreview(controlPlane, &database.SubagentDefinitionVersion{
		ID:            "version-1",
		VersionNumber: 1,
	}, "tenant", "active")
	if preview == nil {
		t.Fatal("expected preview to be built")
	}
	if preview.ChangeType != "metadata_update" {
		t.Fatalf("expected metadata_update, got %s", preview.ChangeType)
	}
	if preview.RequiresConfirmation {
		t.Fatalf("expected low-risk metadata update without confirmation, got %#v", preview)
	}
}

func TestBuildSubagentGovernanceSummaryTracksMetadataAliasAndReadiness(t *testing.T) {
	controlPlane := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:                    "subagent-1",
			HostAgentDefinitionID: "host-1",
			Metadata:              json.RawMessage(`{"target_agent_definition_id":"host-1"}`),
		},
		Publication: &database.SubagentPublicationState{
			VersionID:          "version-2",
			VersionNumber:      2,
			Status:             "active",
			PublicationScope:   "tenant",
			AuthorizationCount: 1,
		},
		Versions: []*database.SubagentDefinitionVersion{
			{ID: "version-3", VersionNumber: 3},
			{ID: "version-2", VersionNumber: 2},
		},
		Authorizations: []*database.SubagentAuthorizedAgent{
			{AuthorizationID: "auth-1", AgentDefinitionID: "agent-1", AgentName: "Planner", AgentStatus: "active", Status: "enabled"},
		},
	}

	summary := buildSubagentGovernanceSummary(controlPlane)
	if summary == nil {
		t.Fatal("expected governance summary")
	}
	if !summary.CompatibilityMode {
		t.Fatal("expected compatibility mode to be enabled")
	}
	if len(summary.CompatibilityDetails) != 1 || summary.CompatibilityDetails[0].Kind != "metadata_alias" {
		t.Fatalf("expected a single metadata_alias detail, got %#v", summary.CompatibilityDetails)
	}
	if !summary.HasRollbackCandidate || summary.RollbackCandidateCount != 1 {
		t.Fatalf("expected rollback candidate metadata, got %#v", summary)
	}
	if len(summary.Warnings) == 0 {
		t.Fatal("expected governance warnings for compatibility bridge")
	}
	if summary.BridgeRemovalReadiness == nil {
		t.Fatal("expected bridge removal readiness")
	}
	if summary.BridgeRemovalReadiness.Ready {
		t.Fatalf("expected readiness to remain blocked until alias freeze is complete, got %#v", summary.BridgeRemovalReadiness)
	}
	if summary.BridgeRemovalReadiness.BlockingIssueCount != 1 {
		t.Fatalf("expected exactly one blocking issue for metadata alias, got %#v", summary.BridgeRemovalReadiness)
	}
}

func TestBuildSubagentGovernanceSummaryDetectsLegacyMetadataAlias(t *testing.T) {
	controlPlane := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:       "subagent-1",
			Metadata: json.RawMessage(`{"target_agent_definition_id":"host-legacy"}`),
		},
	}

	summary := buildSubagentGovernanceSummary(controlPlane)
	if summary == nil {
		t.Fatal("expected governance summary")
	}
	if !summary.CompatibilityMode {
		t.Fatal("expected metadata alias to trigger compatibility mode")
	}
	if len(summary.CompatibilityDetails) != 1 || summary.CompatibilityDetails[0].Kind != "metadata_alias" {
		t.Fatalf("expected metadata_alias detail, got %#v", summary.CompatibilityDetails)
	}
}

func TestBuildSubagentTenantGovernanceSummaryAggregatesCapabilityPressureAndEvents(t *testing.T) {
	controlPlaneA := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:                    "subagent-1",
			HostAgentDefinitionID: "host-1",
			Metadata:              json.RawMessage(`{"target_agent_definition_id":"legacy-host"}`),
		},
		Publication: &database.SubagentPublicationState{
			VersionID:          "version-1",
			VersionNumber:      1,
			Status:             "active",
			PublicationScope:   "tenant",
			AuthorizationCount: 2,
		},
		Versions: []*database.SubagentDefinitionVersion{
			{ID: "version-2", VersionNumber: 2},
			{ID: "version-1", VersionNumber: 1},
		},
		Authorizations: []*database.SubagentAuthorizedAgent{
			{AuthorizationID: "auth-1", AgentDefinitionID: "agent-1", AgentName: "Planner", AgentStatus: "active", Status: "enabled"},
			{AuthorizationID: "auth-2", AgentDefinitionID: "agent-2", AgentName: "Reviewer", AgentStatus: "disabled", Status: "disabled"},
		},
	}
	controlPlaneA = enrichSubagentControlPlaneGovernance(controlPlaneA)

	controlPlaneB := &database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID: "subagent-2",
		},
		Versions: []*database.SubagentDefinitionVersion{
			{ID: "version-1", VersionNumber: 1},
		},
	}
	controlPlaneB = enrichSubagentControlPlaneGovernance(controlPlaneB)

	events := []*database.SubagentPublicationEvent{
		{
			ID:                   "event-1",
			ActionType:           "rollback",
			EventStage:           "executed",
			ChangeType:           "rollback",
			RiskLevel:            "high",
			RequiresConfirmation: true,
			CompatibilityMode:    true,
		},
		{
			ID:                "event-2",
			ActionType:        "rollout",
			EventStage:        "previewed",
			ChangeType:        "rollout",
			RiskLevel:         "medium",
			CompatibilityMode: false,
		},
	}

	summary := buildSubagentTenantGovernanceSummary(
		[]*database.SubagentControlPlane{controlPlaneA, controlPlaneB},
		events,
		&database.SubagentPublicationEventFilters{Limit: 10, Offset: 0},
	)
	if summary == nil {
		t.Fatal("expected tenant governance summary")
	}
	if summary.TotalCapabilities != 2 {
		t.Fatalf("expected 2 capabilities, got %d", summary.TotalCapabilities)
	}
	if summary.CompatibilityCapabilities != 1 {
		t.Fatalf("expected 1 compatibility capability, got %d", summary.CompatibilityCapabilities)
	}
	if summary.HostOverrideCapabilities != 1 || summary.MetadataAliasCapabilities != 1 {
		t.Fatalf("unexpected host override or metadata alias counts: %#v", summary)
	}
	if summary.PublicationMissingCount != 1 || summary.PublicationNotLatestCount != 2 {
		t.Fatalf("unexpected publication counts: missing=%d not_latest=%d", summary.PublicationMissingCount, summary.PublicationNotLatestCount)
	}
	if summary.AuthorizationCount != 2 || summary.EnabledAuthorizationCount != 1 || summary.InactiveAuthorizationCount != 1 {
		t.Fatalf("unexpected authorization counts: %#v", summary)
	}
	if summary.BridgeRemovalReadyCapabilities != 0 || summary.BridgeRemovalBlockedCount < 1 {
		t.Fatalf("unexpected bridge removal counters: %#v", summary)
	}
	if summary.RecentEventCount != 2 || summary.HighRiskEventCount != 1 || summary.ConfirmationRequiredEventCount != 1 || summary.CompatibilityEventCount != 1 {
		t.Fatalf("unexpected event counters: %#v", summary)
	}
	if summary.ActionTypeCounts["rollback"] != 1 || summary.EventStageCounts["previewed"] != 1 || summary.ChangeTypeCounts["rollout"] != 1 || summary.RiskLevelCounts["medium"] != 1 {
		t.Fatalf("unexpected event distributions: %#v", summary)
	}
}

func TestBuildSubagentMetadataAliasFreezePreviewExecutable(t *testing.T) {
	controlPlane := enrichSubagentControlPlaneGovernance(&database.SubagentControlPlane{
		Definition: &database.SubagentDefinition{
			ID:       "subagent-1",
			Name:     "Code Reviewer",
			Metadata: json.RawMessage(`{"target_agent_definition_id":"agent-1","slug":"code-reviewer"}`),
		},
		Publication: &database.SubagentPublicationState{
			VersionID:          "version-1",
			VersionNumber:      1,
			Status:             "active",
			PublicationScope:   "tenant",
			AuthorizationCount: 2,
		},
		Authorizations: []*database.SubagentAuthorizedAgent{
			{AuthorizationID: "auth-1", AgentDefinitionID: "agent-1", AgentName: "Planner", AgentStatus: "active", Status: "enabled"},
			{AuthorizationID: "auth-2", AgentDefinitionID: "agent-2", AgentName: "Reviewer", AgentStatus: "disabled", Status: "disabled"},
		},
	})

	preview := buildSubagentMetadataAliasFreezePreview([]*database.SubagentControlPlane{controlPlane}, &SubagentMetadataAliasFreezeRequest{
		Scope:         "selection",
		DefinitionIDs: []string{"subagent-1"},
	})
	if preview == nil {
		t.Fatal("expected metadata alias freeze preview")
	}
	if !preview.Executable || !preview.RequiresConfirmation {
		t.Fatalf("expected executable confirmation-gated preview, got %#v", preview)
	}
	if preview.Scope != "selection" || preview.ImpactedCapabilityCount != 1 {
		t.Fatalf("unexpected preview scope/count: %#v", preview)
	}
	if preview.EnabledAuthorizationCount != 1 || len(preview.AffectedCapabilities) != 1 {
		t.Fatalf("unexpected preview capability summary: %#v", preview)
	}
	if preview.AffectedCapabilities[0].LegacyAliasKey != "target_agent_definition_id" {
		t.Fatalf("expected legacy alias key to be preserved, got %#v", preview.AffectedCapabilities[0])
	}
}

func TestBuildSubagentMetadataAliasFreezeEventCarriesCapabilityContext(t *testing.T) {
	preview := &database.SubagentMetadataAliasFreezePreview{
		Executable:                 true,
		RequiresConfirmation:       true,
		Summary:                    "tenant 内有 2 个 capability 仍残留 legacy metadata alias。",
		Scope:                      "tenant",
		DefinitionIDs:              []string{"subagent-1", "subagent-2"},
		ImpactedCapabilityCount:    2,
		AuthorizationCount:         5,
		EnabledAuthorizationCount:  3,
		InactiveAuthorizationCount: 2,
		RecommendedActions:         []string{"执行后重新检查 compatibility detail。"},
		AffectedCapabilities: []*database.SubagentMetadataAliasFreezeCandidate{
			{
				DefinitionID:              "subagent-1",
				DefinitionName:            "Code Reviewer",
				LegacyAliasKey:            "target_agent_definition_id",
				LegacyAliasValue:          "agent-1",
				EnabledAuthorizationCount: 2,
				AuthorizationCount:        3,
			},
		},
	}

	event := buildSubagentMetadataAliasFreezeEvent(
		"tenant-1",
		"user-1",
		preview,
		preview.AffectedCapabilities[0],
		2,
		"executed",
	)
	if event == nil {
		t.Fatal("expected metadata alias freeze event")
	}
	if event.ActionType != "metadata_alias_freeze" || event.ChangeType != "metadata_alias_freeze" {
		t.Fatalf("unexpected freeze event type: %#v", event)
	}
	if event.DefinitionID != "subagent-1" || !event.Confirmed {
		t.Fatalf("unexpected freeze event identity: %#v", event)
	}
	if !strings.Contains(event.Summary, "2 个 capability") {
		t.Fatalf("expected execution summary to mention impacted capability count, got %q", event.Summary)
	}
}

func TestValidateSubagentPublicationGovernanceInputsRequiresRollbackPlan(t *testing.T) {
	preview := &database.SubagentPublicationChangePreview{
		ChangeType:           "rollback",
		RequiresConfirmation: true,
		Target: &database.SubagentPublicationChangeEndpoint{
			Status: "active",
		},
	}

	err := validateSubagentPublicationGovernanceInputs(preview, &SubagentPublicationUpdateRequest{
		ChangeReason:         "线上回归需要紧急回滚",
		RollbackRecoveryPlan: "",
	})
	if err == nil {
		t.Fatal("expected rollback without recovery plan to be rejected")
	}
}

func TestBuildSubagentPublicationEventCarriesGovernanceNotes(t *testing.T) {
	preview := &database.SubagentPublicationChangePreview{
		ChangeType:                 "rollback",
		RiskLevel:                  "high",
		RequiresConfirmation:       true,
		Summary:                    "即将把 publication 从 v3 回滚到 v2。",
		ImpactedAuthorizationCount: 3,
		EnabledAuthorizationCount:  2,
		InactiveAuthorizationCount: 1,
		CompatibilityMode:          true,
		RecommendedActions:         []string{"先创建测试运行"},
		AffectedAgents: []*database.SubagentPublicationImpactAgent{
			{
				AuthorizationID:     "auth-1",
				AgentDefinitionID:   "agent-1",
				AgentName:           "Planner",
				AgentStatus:         "active",
				AuthorizationStatus: "enabled",
			},
		},
		Current: &database.SubagentPublicationChangeEndpoint{
			VersionID:        "version-3",
			VersionNumber:    3,
			Status:           "active",
			PublicationScope: "tenant",
		},
		Target: &database.SubagentPublicationChangeEndpoint{
			VersionID:        "version-2",
			VersionNumber:    2,
			Status:           "active",
			PublicationScope: "tenant",
		},
	}

	event := buildSubagentPublicationEvent(
		"tenant-1",
		"user-1",
		"subagent-1",
		"publication-1",
		"executed",
		preview,
		&database.SubagentPublicationState{
			ID:               "publication-1",
			VersionID:        "version-3",
			VersionNumber:    3,
			Status:           "active",
			PublicationScope: "tenant",
		},
		&SubagentPublicationUpdateRequest{
			ChangeReason:         "线上回归需要止血",
			ChangeNotes:          "已通知值班同学观察",
			RollbackRecoveryPlan: "修复完成后重新发布 v3.1",
			GovernanceMetadata:   json.RawMessage(`{"ticket":"OPS-123"}`),
			Confirmed:            true,
		},
	)
	if event == nil {
		t.Fatal("expected publication event")
	}
	if event.ActionType != "rollback" || event.EventStage != "executed" {
		t.Fatalf("unexpected publication event action: %#v", event)
	}
	if event.ChangeReason != "线上回归需要止血" || event.RollbackRecoveryPlan != "修复完成后重新发布 v3.1" {
		t.Fatalf("expected governance notes to be preserved, got %#v", event)
	}
	if event.VersionNumber != 2 || event.PreviousVersionNumber != 3 {
		t.Fatalf("expected version transition to be preserved, got %#v", event)
	}
	if event.EnabledAuthorizationCount != 2 || !event.CompatibilityMode {
		t.Fatalf("expected impact summary to survive, got %#v", event)
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
