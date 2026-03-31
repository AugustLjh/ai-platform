package service

import (
	"encoding/json"
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
