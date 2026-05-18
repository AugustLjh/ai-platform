package service

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/ai-platform/platform/api/grpc"
	"github.com/ai-platform/platform/database"
)

var ErrAgentUnauthorized = errors.New("unauthorized")
var ErrNotImplemented = errors.New("not implemented")

const (
	maskedSecretValue      = "********"
	fallbackFixedSkillSlug = "implementation-planner"
	mcpCatalogStaleAfter   = 24 * time.Hour
	mcpBulkPreviewTTL      = 15 * time.Minute
)

var systemSkillSlugs = []string{
	"implementation-planner",
	"engineering",
}

var (
	sensitiveAssignmentPattern = regexp.MustCompile(`(?i)(\b(?:api[_-]?key|access[_-]?key|client[_-]?secret|secret|password|passwd|token|authorization|private[_-]?key|cookie)\b\s*[:=]\s*)([^\s,&;"']+)`)
	bearerTokenPattern         = regexp.MustCompile(`(?i)\bBearer\s+([A-Za-z0-9._~+/=-]{8,})`)
	basicAuthPattern           = regexp.MustCompile(`(?i)\bBasic\s+([A-Za-z0-9._~+/=-]{8,})`)
)

type AgentDefinitionUpsertRequest struct {
	Name         string          `json:"name"`
	Description  string          `json:"description"`
	SystemPrompt string          `json:"system_prompt"`
	Model        string          `json:"model"`
	Config       json.RawMessage `json:"config"`
	Metadata     json.RawMessage `json:"metadata"`
}

type CreateAgentRunRequest struct {
	Input     json.RawMessage `json:"input"`
	SessionID string          `json:"session_id"`
	Metadata  map[string]any  `json:"metadata"`
	AutoStart *bool           `json:"auto_start,omitempty"`
}

type ResumeAgentRunRequest struct {
	InputPatch json.RawMessage `json:"input_patch"`
}

type UpdateAgentSkillsRequest struct {
	SkillIDs []string `json:"skill_ids"`
}

type UpdateAgentMCPServersRequest struct {
	ServerIDs []string `json:"server_ids"`
}

type UpdateAgentKnowledgeBasesRequest struct {
	KnowledgeBaseIDs []string `json:"knowledge_base_ids"`
}

type SubagentDefinitionUpsertRequest struct {
	Name                  string          `json:"name"`
	Slug                  string          `json:"slug"`
	Description           string          `json:"description"`
	SystemPrompt          string          `json:"system_prompt"`
	Model                 string          `json:"model"`
	HostAgentDefinitionID string          `json:"host_agent_definition_id"`
	HandoffPrompt         string          `json:"handoff_prompt"`
	Status                string          `json:"status"`
	DefinitionStatus      string          `json:"definition_status"`
	LifecycleStatus       string          `json:"lifecycle_status"`
	PublicationScope      string          `json:"publication_scope"`
	Config                json.RawMessage `json:"config"`
	Metadata              json.RawMessage `json:"metadata"`
	OutputSchema          json.RawMessage `json:"output_schema"`
	HandoffInputSchema    json.RawMessage `json:"handoff_input_schema"`
	ToolAllowlist         json.RawMessage `json:"tool_allowlist"`
	SkillAllowlist        json.RawMessage `json:"skill_allowlist"`
	MCPAllowlist          json.RawMessage `json:"mcp_allowlist"`
	KnowledgePolicy       json.RawMessage `json:"knowledge_policy"`
	ReviewPolicy          json.RawMessage `json:"review_policy"`
	RuntimePolicy         json.RawMessage `json:"runtime_policy"`
	PublicationMetadata   json.RawMessage `json:"publication_metadata"`
}

type UpdateAgentSubagentsRequest struct {
	SubagentIDs []string `json:"subagent_ids"`
}

type SubagentVersionCreateRequest struct {
	LifecycleStatus     string          `json:"lifecycle_status"`
	SystemPrompt        string          `json:"system_prompt"`
	Model               string          `json:"model"`
	Config              json.RawMessage `json:"config"`
	Metadata            json.RawMessage `json:"metadata"`
	OutputSchema        json.RawMessage `json:"output_schema"`
	HandoffInputSchema  json.RawMessage `json:"handoff_input_schema"`
	ToolAllowlist       json.RawMessage `json:"tool_allowlist"`
	SkillAllowlist      json.RawMessage `json:"skill_allowlist"`
	MCPAllowlist        json.RawMessage `json:"mcp_allowlist"`
	KnowledgePolicy     json.RawMessage `json:"knowledge_policy"`
	ReviewPolicy        json.RawMessage `json:"review_policy"`
	RuntimePolicy       json.RawMessage `json:"runtime_policy"`
	Publish             bool            `json:"publish"`
	PublicationScope    string          `json:"publication_scope"`
	PublicationStatus   string          `json:"publication_status"`
	PublicationMetadata json.RawMessage `json:"publication_metadata"`
}

type SubagentPublicationUpdateRequest struct {
	VersionID            string          `json:"version_id"`
	PublicationScope     string          `json:"publication_scope"`
	Status               string          `json:"status"`
	PublicationMetadata  json.RawMessage `json:"publication_metadata"`
	ChangeReason         string          `json:"change_reason,omitempty"`
	ChangeNotes          string          `json:"change_notes,omitempty"`
	RollbackRecoveryPlan string          `json:"rollback_recovery_plan,omitempty"`
	GovernanceMetadata   json.RawMessage `json:"governance_metadata,omitempty"`
	PreviewOnly          bool            `json:"preview_only,omitempty"`
	Confirmed            bool            `json:"confirmed,omitempty"`
}

type SubagentMetadataAliasFreezeRequest struct {
	DefinitionIDs []string `json:"definition_ids,omitempty"`
	Scope         string   `json:"scope,omitempty"`
	PreviewOnly   bool     `json:"preview_only,omitempty"`
	Confirmed     bool     `json:"confirmed,omitempty"`
}

type SubagentTenantGovernanceSummary struct {
	TotalCapabilities              int                                       `json:"total_capabilities"`
	CompatibilityCapabilities      int                                       `json:"compatibility_capabilities"`
	HostOverrideCapabilities       int                                       `json:"host_override_capabilities"`
	MetadataAliasCapabilities      int                                       `json:"metadata_alias_capabilities"`
	PublicationMissingCount        int                                       `json:"publication_missing_count"`
	PublicationNotLatestCount      int                                       `json:"publication_not_latest_count"`
	AuthorizationCount             int                                       `json:"authorization_count"`
	EnabledAuthorizationCount      int                                       `json:"enabled_authorization_count"`
	InactiveAuthorizationCount     int                                       `json:"inactive_authorization_count"`
	BridgeRemovalReadyCapabilities int                                       `json:"bridge_removal_ready_capabilities"`
	BridgeRemovalBlockedCount      int                                       `json:"bridge_removal_blocked_count"`
	BridgeRemovalPendingCount      int                                       `json:"bridge_removal_pending_count"`
	HighRiskEventCount             int                                       `json:"high_risk_event_count"`
	ConfirmationRequiredEventCount int                                       `json:"confirmation_required_event_count"`
	CompatibilityEventCount        int                                       `json:"compatibility_event_count"`
	RecentEventCount               int                                       `json:"recent_event_count"`
	ActionTypeCounts               map[string]int                            `json:"action_type_counts"`
	EventStageCounts               map[string]int                            `json:"event_stage_counts"`
	ChangeTypeCounts               map[string]int                            `json:"change_type_counts"`
	RiskLevelCounts                map[string]int                            `json:"risk_level_counts"`
	Filters                        *database.SubagentPublicationEventFilters `json:"event_filters,omitempty"`
}

type SubagentGovernanceResponse struct {
	Events                     []*database.SubagentPublicationEvent         `json:"events"`
	Summary                    *SubagentTenantGovernanceSummary             `json:"summary"`
	MetadataAliasFreezePreview *database.SubagentMetadataAliasFreezePreview `json:"metadata_alias_freeze_preview,omitempty"`
	Total                      int                                          `json:"total"`
	Limit                      int                                          `json:"limit"`
	Offset                     int                                          `json:"offset"`
}

type SubagentTestRunRequest struct {
	VersionID         string          `json:"version_id"`
	AgentDefinitionID string          `json:"agent_definition_id"`
	Input             json.RawMessage `json:"input"`
	SessionID         string          `json:"session_id"`
	Metadata          map[string]any  `json:"metadata"`
	AutoStart         *bool           `json:"auto_start,omitempty"`
}

type ClearAgentContextRequest struct {
	SessionID string `json:"session_id"`
}

type AgentToolSpec struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	InputSchema json.RawMessage `json:"input_schema"`
	Kind        string          `json:"kind"`
	Metadata    json.RawMessage `json:"metadata"`
}

type AgentToolListResponse struct {
	Tools         []*AgentToolSpec `json:"tools"`
	Total         int              `json:"total"`
	ExecutionMode map[string]any   `json:"execution_mode,omitempty"`
}

type AgentWorkspaceSourceResponse struct {
	Status      string           `json:"status"`
	Enabled     bool             `json:"enabled"`
	BaseRoot    string           `json:"base_root"`
	SourceRoots []string         `json:"source_roots"`
	Count       int              `json:"count"`
	MaxEntries  int              `json:"max_entries"`
	MaxDepth    int              `json:"max_depth"`
	Sources     []map[string]any `json:"sources"`
}

type AgentWorkspaceInspectionResponse struct {
	Status             string           `json:"status"`
	BaseRoot           string           `json:"base_root"`
	RetentionHours     int              `json:"retention_hours"`
	WorkspaceCount     int              `json:"workspace_count"`
	ExpiredCount       int              `json:"expired_count"`
	QuotaExceededCount int              `json:"quota_exceeded_count"`
	TotalSizeBytes     int64            `json:"total_size_bytes"`
	TotalFileCount     int64            `json:"total_file_count"`
	GeneratedAt        string           `json:"generated_at"`
	LockSummary        map[string]any   `json:"lock_summary,omitempty"`
	Health             map[string]any   `json:"health,omitempty"`
	Workspaces         []map[string]any `json:"workspaces"`
}

type AgentWorkspaceCleanupResponse struct {
	Status         string           `json:"status"`
	DryRun         bool             `json:"dry_run"`
	BaseRoot       string           `json:"base_root"`
	TenantID       string           `json:"tenant_id,omitempty"`
	RetentionHours int              `json:"retention_hours"`
	CandidateCount int              `json:"candidate_count"`
	SelectedCount  int              `json:"selected_count"`
	DeletedCount   int              `json:"deleted_count"`
	FailedCount    int              `json:"failed_count"`
	SkippedCount   int              `json:"skipped_count,omitempty"`
	GeneratedAt    string           `json:"generated_at"`
	Deleted        []map[string]any `json:"deleted"`
	Failed         []map[string]any `json:"failed"`
	Skipped        []map[string]any `json:"skipped,omitempty"`
}

type AgentRuntimeStatusResponse map[string]any

type MCPServerUpsertRequest struct {
	Name      string          `json:"name"`
	Transport string          `json:"transport"`
	Endpoint  string          `json:"endpoint"`
	Command   string          `json:"command"`
	Args      json.RawMessage `json:"args"`
	Env       json.RawMessage `json:"env"`
	Status    string          `json:"status"`
	Metadata  json.RawMessage `json:"metadata"`
}

type MCPServerTestResponse struct {
	Result       map[string]any            `json:"result"`
	Server       *database.MCPServer       `json:"server,omitempty"`
	Connection   *database.MCPConnection   `json:"connection,omitempty"`
	Catalog      *database.MCPCatalog      `json:"catalog,omitempty"`
	Availability *database.MCPAvailability `json:"availability,omitempty"`
}

type MCPServerRefreshResponse struct {
	Tools        []*database.MCPServerTool `json:"tools"`
	Total        int                       `json:"total"`
	Server       *database.MCPServer       `json:"server,omitempty"`
	Connection   *database.MCPConnection   `json:"connection,omitempty"`
	Catalog      *database.MCPCatalog      `json:"catalog,omitempty"`
	Availability *database.MCPAvailability `json:"availability,omitempty"`
}

type MCPServerGovernanceSummary struct {
	TotalServers         int                        `json:"total_servers"`
	RecoveringServers    int                        `json:"recovering_servers"`
	BlockedServers       int                        `json:"blocked_servers"`
	StaleServers         int                        `json:"stale_servers"`
	UntestedServers      int                        `json:"untested_servers"`
	ImpactedAgents       int                        `json:"impacted_agents"`
	ActiveImpactedAgents int                        `json:"active_impacted_agents"`
	RecentEventCount     int                        `json:"recent_event_count"`
	LongStaleServers     []*database.MCPServer      `json:"long_stale_servers"`
	RecoverableServers   []*database.MCPServer      `json:"recoverable_servers"`
	RecentEvents         []*database.MCPServerEvent `json:"recent_events"`
	FailureModeCounts    map[string]int             `json:"failure_mode_counts"`
	ActionTypeCounts     map[string]int             `json:"action_type_counts"`
	EventStatusCounts    map[string]int             `json:"event_status_counts"`
	EventFilters         *MCPGovernanceEventFilters `json:"event_filters,omitempty"`
}

type MCPGovernanceEventFilters struct {
	ServerID    string `json:"server_id,omitempty"`
	ActionType  string `json:"action_type,omitempty"`
	Status      string `json:"status,omitempty"`
	FailureMode string `json:"failure_mode,omitempty"`
	Limit       int    `json:"limit,omitempty"`
}

type MCPGovernanceResponse struct {
	Servers []*database.MCPServer       `json:"servers"`
	Summary *MCPServerGovernanceSummary `json:"summary"`
	Total   int                         `json:"total"`
}

type MCPServerAuditReport struct {
	TenantID           string                          `json:"tenant_id"`
	GeneratedAt        time.Time                       `json:"generated_at"`
	Overview           *MCPServerAuditReportOverview   `json:"overview"`
	TopRiskServers     []*MCPServerAuditServerSnapshot `json:"top_risk_servers"`
	ScoreDistribution  map[string]int                  `json:"score_distribution"`
	RecentEvents       []*database.MCPServerEvent      `json:"recent_events"`
	FailureModeCounts  map[string]int                  `json:"failure_mode_counts"`
	ActionTypeCounts   map[string]int                  `json:"action_type_counts"`
	RecommendedActions []string                        `json:"recommended_actions"`
}

type MCPServerAuditReportOverview struct {
	TotalServers      int     `json:"total_servers"`
	AverageScore      float64 `json:"average_score"`
	MedianScore       int     `json:"median_score"`
	LowRiskCount      int     `json:"low_risk_count"`
	MediumRiskCount   int     `json:"medium_risk_count"`
	HighRiskCount     int     `json:"high_risk_count"`
	CriticalRiskCount int     `json:"critical_risk_count"`
	BlockedCount      int     `json:"blocked_count"`
	RecoveringCount   int     `json:"recovering_count"`
	StaleCount        int     `json:"stale_count"`
	UntestedCount     int     `json:"untested_count"`
}

type MCPServerAuditServerSnapshot struct {
	ServerID     string                           `json:"server_id"`
	ServerName   string                           `json:"server_name"`
	Transport    string                           `json:"transport"`
	Status       string                           `json:"status"`
	Score        int                              `json:"score"`
	RiskLevel    string                           `json:"risk_level"`
	Summary      string                           `json:"summary"`
	FailureMode  string                           `json:"failure_mode,omitempty"`
	Recoverable  bool                             `json:"recoverable"`
	BindingCount int                              `json:"binding_count"`
	ActiveCount  int                              `json:"active_count"`
	EventCount   int                              `json:"event_count"`
	LastTestedAt *time.Time                       `json:"last_tested_at,omitempty"`
	EvaluatedAt  *time.Time                       `json:"evaluated_at,omitempty"`
	Breakdown    []*database.MCPSecurityBreakdown `json:"breakdown,omitempty"`
}

type MCPServerBulkActionRequest struct {
	ServerIDs    []string `json:"server_ids"`
	Action       string   `json:"action"`
	GroupBy      string   `json:"group_by,omitempty"`
	MaxBatchSize int      `json:"max_batch_size,omitempty"`
	RetryFailed  int      `json:"retry_failed,omitempty"`
	PreviewOnly  bool     `json:"preview_only,omitempty"`
	PreviewToken string   `json:"preview_token,omitempty"`
	Confirmed    bool     `json:"confirmed,omitempty"`
}

type MCPServerBulkActionResult struct {
	ServerID            string                        `json:"server_id"`
	ServerName          string                        `json:"server_name,omitempty"`
	Action              string                        `json:"action"`
	OK                  bool                          `json:"ok"`
	Message             string                        `json:"message"`
	Server              *database.MCPServer           `json:"server,omitempty"`
	Attempts            int                           `json:"attempts,omitempty"`
	GroupKey            string                        `json:"group_key,omitempty"`
	FailureMode         string                        `json:"failure_mode,omitempty"`
	RecoveryStatus      string                        `json:"recovery_status,omitempty"`
	ImpactSummary       string                        `json:"impact_summary,omitempty"`
	SuggestedFollowUps  []*database.MCPRecoveryAction `json:"suggested_follow_ups,omitempty"`
	RecommendedPriority string                        `json:"recommended_priority,omitempty"`
}

type MCPServerBulkActionExecution struct {
	GroupBy       string `json:"group_by"`
	MaxBatchSize  int    `json:"max_batch_size"`
	RetryFailed   int    `json:"retry_failed"`
	SelectedCount int    `json:"selected_count"`
	GroupCount    int    `json:"group_count"`
	PreviewOnly   bool   `json:"preview_only"`
	OrderedBy     string `json:"ordered_by,omitempty"`
}

type MCPServerBulkFollowUpStage struct {
	Key      string `json:"key"`
	Label    string `json:"label"`
	Count    int    `json:"count"`
	Priority string `json:"priority,omitempty"`
	Summary  string `json:"summary,omitempty"`
}

type MCPServerBulkFollowUpPlan struct {
	Status               string                        `json:"status"`
	Summary              string                        `json:"summary"`
	RecommendedActions   []string                      `json:"recommended_actions,omitempty"`
	FailedServerIDs      []string                      `json:"failed_server_ids,omitempty"`
	DriftedServerIDs     []string                      `json:"drifted_server_ids,omitempty"`
	RecoveryStageCounts  []*MCPServerBulkFollowUpStage `json:"recovery_stage_counts,omitempty"`
	RequiresManualReview bool                          `json:"requires_manual_review,omitempty"`
	ManualReviewReason   string                        `json:"manual_review_reason,omitempty"`
	CompensationActions  []string                      `json:"compensation_actions,omitempty"`
	RollbackActions      []string                      `json:"rollback_actions,omitempty"`
}

type MCPServerBulkActionGroup struct {
	Key     string                       `json:"key"`
	Label   string                       `json:"label"`
	Total   int                          `json:"total"`
	Success int                          `json:"success"`
	Failed  int                          `json:"failed"`
	Results []*MCPServerBulkActionResult `json:"results"`
}

type MCPServerBulkActionRecommendation struct {
	Order                int                           `json:"order"`
	ServerID             string                        `json:"server_id"`
	ServerName           string                        `json:"server_name,omitempty"`
	Action               string                        `json:"action"`
	Priority             string                        `json:"priority"`
	Reason               string                        `json:"reason"`
	FailureMode          string                        `json:"failure_mode,omitempty"`
	RecoveryStatus       string                        `json:"recovery_status,omitempty"`
	ImpactedAgents       int                           `json:"impacted_agents,omitempty"`
	ActiveImpactedAgents int                           `json:"active_impacted_agents,omitempty"`
	SuggestedFollowUps   []*database.MCPRecoveryAction `json:"suggested_follow_ups,omitempty"`
}

type MCPServerBulkActionPreview struct {
	Action               string                               `json:"action"`
	PreviewOnly          bool                                 `json:"preview_only"`
	PreviewToken         string                               `json:"preview_token,omitempty"`
	OrderedBy            string                               `json:"ordered_by"`
	RiskSummary          string                               `json:"risk_summary"`
	RequiresConfirmation bool                                 `json:"requires_confirmation"`
	ConfirmationMessage  string                               `json:"confirmation_message,omitempty"`
	GeneratedAt          *time.Time                           `json:"generated_at,omitempty"`
	ExpiresAt            *time.Time                           `json:"expires_at,omitempty"`
	SelectedServerIDs    []string                             `json:"selected_server_ids,omitempty"`
	Recommendations      []*MCPServerBulkActionRecommendation `json:"recommendations,omitempty"`
}

type mcpBulkServerCandidate struct {
	server *database.MCPServer
	order  int
}

type mcpBulkPreviewTokenPayload struct {
	Action               string                         `json:"action"`
	GroupBy              string                         `json:"group_by"`
	MaxBatchSize         int                            `json:"max_batch_size"`
	RetryFailed          int                            `json:"retry_failed"`
	GeneratedAt          time.Time                      `json:"generated_at"`
	ConfirmedRequired    bool                           `json:"confirmed_required"`
	SelectedServerIDs    []string                       `json:"selected_server_ids"`
	ServerStateSnapshots []*mcpBulkPreviewStateSnapshot `json:"server_state_snapshots"`
}

type mcpBulkPreviewStateSnapshot struct {
	ServerID   string `json:"server_id"`
	Signature  string `json:"signature"`
	ServerName string `json:"server_name,omitempty"`
}

type MCPServerBulkActionResponse struct {
	Action    string                        `json:"action"`
	Results   []*MCPServerBulkActionResult  `json:"results"`
	Total     int                           `json:"total"`
	Success   int                           `json:"success"`
	Failed    int                           `json:"failed"`
	Summary   *MCPServerGovernanceSummary   `json:"summary,omitempty"`
	Execution *MCPServerBulkActionExecution `json:"execution,omitempty"`
	Groups    []*MCPServerBulkActionGroup   `json:"groups,omitempty"`
	Preview   *MCPServerBulkActionPreview   `json:"preview,omitempty"`
	FollowUp  *MCPServerBulkFollowUpPlan    `json:"follow_up,omitempty"`
}

type AgentService struct {
	aiClient           *grpc.AIClient
	agentStore         *database.AgentStore
	subagentStore      *database.SubagentStore
	sessionStore       *database.SessionStore
	skillStore         *database.SkillStore
	mcpStore           *database.MCPStore
	skillsRoot         string
	systemSkillsSynced bool
}

func NewAgentService(
	aiClient *grpc.AIClient,
	agentStore *database.AgentStore,
	subagentStore *database.SubagentStore,
	sessionStore *database.SessionStore,
	skillStore *database.SkillStore,
	mcpStore *database.MCPStore,
) *AgentService {
	return &AgentService{
		aiClient:      aiClient,
		agentStore:    agentStore,
		subagentStore: subagentStore,
		sessionStore:  sessionStore,
		skillStore:    skillStore,
		mcpStore:      mcpStore,
		skillsRoot:    resolveSkillsRoot(),
	}
}

func resolveSkillsRoot() string {
	candidates := make([]string, 0, 5)

	if configured := strings.TrimSpace(os.Getenv("AI_RUNTIME_SKILLS_DIR")); configured != "" {
		candidates = append(candidates, configured)
	}

	if workdir, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(workdir, "ai_runtime", "skills"))
	}

	if executable, err := os.Executable(); err == nil {
		execDir := filepath.Dir(executable)
		candidates = append(candidates,
			filepath.Join(execDir, "ai_runtime", "skills"),
			filepath.Join(execDir, "skills"),
		)
	}

	fallback := filepath.Join("/mnt/ai-platform", "ai_runtime", "skills")
	candidates = append(candidates, fallback)

	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		info, err := os.Stat(candidate)
		if err == nil && info.IsDir() {
			return candidate
		}
	}

	if len(candidates) > 0 {
		return candidates[0]
	}
	return fallback
}

func (s *AgentService) CreateAgentDefinition(tenantID, userID string, req *AgentDefinitionUpsertRequest) (*database.AgentDefinition, error) {
	def := &database.AgentDefinition{
		TenantID:     tenantID,
		Name:         strings.TrimSpace(req.Name),
		Description:  strings.TrimSpace(req.Description),
		SystemPrompt: req.SystemPrompt,
		Model:        strings.TrimSpace(req.Model),
		Config:       database.NormalizeJSONRawForExport(req.Config, `{}`),
		Metadata:     database.NormalizeJSONRawForExport(req.Metadata, `{}`),
		CreatedBy:    stringPtr(userID),
	}
	if def.Name == "" {
		return nil, errors.New("name is required")
	}
	created, err := s.agentStore.CreateAgentDefinition(def)
	if err != nil {
		return nil, err
	}
	return s.hydrateAgentBindings(created)
}

func (s *AgentService) UpdateAgentDefinition(tenantID, userID, agentID string, req *AgentDefinitionUpsertRequest) (*database.AgentDefinition, error) {
	current, err := s.agentStore.GetAgentDefinition(agentID, tenantID)
	if err != nil {
		return nil, err
	}
	current.Name = strings.TrimSpace(req.Name)
	current.Description = strings.TrimSpace(req.Description)
	current.SystemPrompt = req.SystemPrompt
	current.Model = strings.TrimSpace(req.Model)
	current.Config = database.NormalizeJSONRawForExport(req.Config, `{}`)
	current.Metadata = database.NormalizeJSONRawForExport(req.Metadata, `{}`)
	current.UpdatedBy = stringPtr(userID)
	updated, err := s.agentStore.UpdateAgentDefinition(current)
	if err != nil {
		return nil, err
	}
	return s.hydrateAgentBindings(updated)
}

func (s *AgentService) GetAgentDefinition(tenantID, agentID string) (*database.AgentDefinition, error) {
	definition, err := s.agentStore.GetAgentDefinition(agentID, tenantID)
	if err != nil {
		return nil, err
	}
	return s.hydrateAgentBindings(definition)
}

func (s *AgentService) ListAgentDefinitions(tenantID string, includeArchived bool) ([]*database.AgentDefinition, error) {
	items, err := s.agentStore.ListAgentDefinitions(tenantID, includeArchived)
	if err != nil {
		return nil, err
	}
	for _, item := range items {
		if _, err := s.hydrateAgentBindings(item); err != nil {
			return nil, err
		}
	}
	return items, nil
}

func (s *AgentService) ArchiveAgentDefinition(tenantID, userID, agentID string) error {
	return s.agentStore.ArchiveAgentDefinition(agentID, tenantID, userID)
}

func (s *AgentService) DeleteAgentDefinition(ctx context.Context, tenantID, userID, agentID string) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}

	runRefs, err := s.agentStore.ListAgentRunReferencesByDefinition(agentID, tenantID)
	if err != nil {
		return err
	}
	if err := s.cancelActiveRuns(ctx, tenantID, runRefs); err != nil {
		return err
	}
	return s.agentStore.HardDeleteAgentDefinition(agentID, tenantID)
}

func (s *AgentService) ClearAgentContext(ctx context.Context, tenantID, userID, agentID string, req *ClearAgentContextRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}

	sessionID := strings.TrimSpace(req.SessionID)
	if sessionID == "" {
		return errors.New("session_id is required")
	}
	if s.sessionStore != nil {
		session, err := s.sessionStore.GetSession(sessionID)
		if err != nil && !isSessionNotFound(err) {
			return err
		}
		if err == nil && (session.UserID != userID || session.TenantID != tenantID) {
			return ErrUnauthorized
		}
	}

	runRefs, err := s.agentStore.ListAgentRunReferencesByDefinitionAndSession(agentID, tenantID, sessionID)
	if err != nil {
		return err
	}
	if err := s.cancelActiveRuns(ctx, tenantID, runRefs); err != nil {
		return err
	}
	return s.agentStore.ClearAgentSessionContext(agentID, tenantID, sessionID)
}

func (s *AgentService) CreateRun(ctx context.Context, tenantID, userID, agentID string, req *CreateAgentRunRequest) (*database.AgentRun, error) {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return nil, err
	}
	sessionID := strings.TrimSpace(req.SessionID)
	if err := s.ensureRunSession(tenantID, userID, sessionID); err != nil {
		return nil, err
	}
	autoStart := true
	if req.AutoStart != nil {
		autoStart = *req.AutoStart
	}

	run, err := s.aiClient.CreateAgentRun(ctx, &grpc.AgentRunCreateRequest{
		AgentDefinitionID: agentID,
		TenantID:          tenantID,
		UserID:            userID,
		SessionID:         sessionID,
		Input:             req.Input,
		Metadata:          req.Metadata,
		AutoStart:         autoStart,
	})
	if err != nil {
		return nil, err
	}
	return run, nil
}

func (s *AgentService) ensureRunSession(tenantID, userID, sessionID string) error {
	if s.sessionStore == nil || sessionID == "" {
		return nil
	}

	session, err := s.sessionStore.GetSession(sessionID)
	if err == nil {
		if session.UserID != userID || session.TenantID != tenantID {
			return ErrUnauthorized
		}
		return nil
	}
	if !isSessionNotFound(err) {
		return err
	}

	return s.sessionStore.CreateSession(&database.Session{
		ID:       sessionID,
		UserID:   userID,
		TenantID: tenantID,
		Title:    "Agent 对话",
	})
}

func (s *AgentService) ListRuns(tenantID, userID string, limit, offset int) ([]*database.AgentRun, error) {
	return s.agentStore.ListAgentRuns(tenantID, userID, limit, offset)
}

func (s *AgentService) GetRun(tenantID, runID string) (*database.AgentRun, error) {
	return s.agentStore.GetAgentRun(runID, tenantID)
}

func (s *AgentService) ListRunEvents(tenantID, runID string, afterSequence int64, limit int) ([]*database.AgentRunEvent, error) {
	return s.agentStore.ListAgentRunEvents(runID, tenantID, afterSequence, limit)
}

func (s *AgentService) ListRunInvocations(ctx context.Context, tenantID, runID string) ([]*grpc.AgentSubagentInvocation, error) {
	return s.aiClient.ListAgentRunInvocations(ctx, runID, tenantID)
}

func (s *AgentService) GetRunTree(ctx context.Context, tenantID, runID string, maxDepth int) (*grpc.AgentRunTreeResponse, error) {
	return s.aiClient.GetAgentRunTree(ctx, runID, tenantID, maxDepth)
}

func (s *AgentService) StreamRunEvents(ctx context.Context, runID, tenantID string, afterSequence int64) (<-chan *database.AgentRunEvent, error) {
	return s.aiClient.StreamAgentRunEvents(ctx, runID, tenantID, afterSequence)
}

func (s *AgentService) CancelRun(ctx context.Context, tenantID, runID string) (*database.AgentRun, error) {
	return s.aiClient.CancelAgentRun(ctx, runID, tenantID)
}

func (s *AgentService) ResumeRun(ctx context.Context, tenantID, runID string, req *ResumeAgentRunRequest) (*database.AgentRun, error) {
	return s.aiClient.ResumeAgentRun(ctx, runID, tenantID, req.InputPatch)
}

func (s *AgentService) ListAvailableTools(ctx context.Context, tenantID, agentDefinitionID string) (*AgentToolListResponse, error) {
	response, err := s.aiClient.ListAgentTools(ctx, tenantID, agentDefinitionID)
	if err != nil {
		return nil, err
	}

	result := make([]*AgentToolSpec, 0, len(response.Tools))
	for _, item := range response.Tools {
		spec := item
		result = append(result, &AgentToolSpec{
			Name:        spec.Name,
			Description: spec.Description,
			InputSchema: spec.InputSchema,
			Kind:        spec.Kind,
			Metadata:    spec.Metadata,
		})
	}
	return &AgentToolListResponse{
		Tools:         result,
		Total:         len(result),
		ExecutionMode: response.ExecutionMode,
	}, nil
}

func (s *AgentService) ListWorkspaceSources(ctx context.Context, tenantID, userID string, maxEntries, maxDepth int) (*AgentWorkspaceSourceResponse, error) {
	response, err := s.aiClient.ListWorkspaceSources(ctx, tenantID, userID, maxEntries, maxDepth)
	if err != nil {
		return nil, err
	}
	return &AgentWorkspaceSourceResponse{
		Status:      response.Status,
		Enabled:     response.Enabled,
		BaseRoot:    response.BaseRoot,
		SourceRoots: response.SourceRoots,
		Count:       response.Count,
		MaxEntries:  response.MaxEntries,
		MaxDepth:    response.MaxDepth,
		Sources:     response.Sources,
	}, nil
}

func (s *AgentService) InspectWorkspaces(ctx context.Context, tenantID, userID string) (*AgentWorkspaceInspectionResponse, error) {
	response, err := s.aiClient.InspectWorkspaces(ctx, tenantID, userID)
	if err != nil {
		return nil, err
	}
	return &AgentWorkspaceInspectionResponse{
		Status:             response.Status,
		BaseRoot:           response.BaseRoot,
		RetentionHours:     response.RetentionHours,
		WorkspaceCount:     response.WorkspaceCount,
		ExpiredCount:       response.ExpiredCount,
		QuotaExceededCount: response.QuotaExceededCount,
		TotalSizeBytes:     response.TotalSizeBytes,
		TotalFileCount:     response.TotalFileCount,
		GeneratedAt:        response.GeneratedAt,
		LockSummary:        response.LockSummary,
		Health:             response.Health,
		Workspaces:         response.Workspaces,
	}, nil
}

func (s *AgentService) CleanupWorkspaces(
	ctx context.Context,
	tenantID, userID string,
	dryRun bool,
	maxDelete int,
	confirmed bool,
) (*AgentWorkspaceCleanupResponse, error) {
	response, err := s.aiClient.CleanupWorkspaces(ctx, tenantID, userID, dryRun, maxDelete, confirmed)
	if err != nil {
		return nil, err
	}
	return &AgentWorkspaceCleanupResponse{
		Status:         response.Status,
		DryRun:         response.DryRun,
		BaseRoot:       response.BaseRoot,
		TenantID:       response.TenantID,
		RetentionHours: response.RetentionHours,
		CandidateCount: response.CandidateCount,
		SelectedCount:  response.SelectedCount,
		DeletedCount:   response.DeletedCount,
		FailedCount:    response.FailedCount,
		SkippedCount:   response.SkippedCount,
		GeneratedAt:    response.GeneratedAt,
		Deleted:        response.Deleted,
		Failed:         response.Failed,
		Skipped:        response.Skipped,
	}, nil
}

func (s *AgentService) CleanupWorkspaceLocks(
	ctx context.Context,
	tenantID, userID string,
	dryRun bool,
	maxDelete int,
	confirmed bool,
) (*AgentWorkspaceCleanupResponse, error) {
	response, err := s.aiClient.CleanupWorkspaceLocks(ctx, tenantID, userID, dryRun, maxDelete, confirmed)
	if err != nil {
		return nil, err
	}
	return &AgentWorkspaceCleanupResponse{
		Status:         response.Status,
		DryRun:         response.DryRun,
		BaseRoot:       response.BaseRoot,
		TenantID:       response.TenantID,
		CandidateCount: response.CandidateCount,
		SelectedCount:  response.SelectedCount,
		DeletedCount:   response.DeletedCount,
		FailedCount:    response.FailedCount,
		SkippedCount:   response.SkippedCount,
		GeneratedAt:    response.GeneratedAt,
		Deleted:        response.Deleted,
		Failed:         response.Failed,
		Skipped:        response.Skipped,
	}, nil
}

func (s *AgentService) GetRuntimeStatus(ctx context.Context, tenantID, userID string) (map[string]any, error) {
	return s.aiClient.GetRuntimeStatus(ctx, tenantID, userID)
}

func (s *AgentService) ListSkills(tenantID string) ([]*database.Skill, error) {
	if err := s.ensureSystemSkillsSynced(); err != nil {
		return nil, err
	}
	items, err := s.skillStore.ListSkills(tenantID)
	if err != nil {
		return nil, err
	}
	for index, item := range items {
		hydrated, err := hydrateSkillContract(item)
		if err != nil {
			return nil, err
		}
		items[index] = hydrated
	}
	return items, nil
}

func (s *AgentService) GetSkill(tenantID, skillID string) (*database.Skill, error) {
	if err := s.ensureSystemSkillsSynced(); err != nil {
		return nil, err
	}
	item, err := s.skillStore.GetSkill(skillID, tenantID)
	if err != nil {
		return nil, err
	}
	return hydrateSkillContract(item)
}

func (s *AgentService) SyncSkills() ([]*database.Skill, error) {
	entries, err := os.ReadDir(s.skillsRoot)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, fmt.Errorf("failed to scan skills directory: %w", err)
	}
	var synced []*database.Skill
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		skill, err := s.loadSkillFromDirectory(filepath.Join(s.skillsRoot, entry.Name()))
		if err != nil {
			return nil, err
		}
		if err := validateSkillGovernance(skill); err != nil {
			return nil, err
		}
		upserted, err := s.skillStore.UpsertSkill(skill)
		if err != nil {
			return nil, err
		}
		upserted, err = hydrateSkillContract(upserted)
		if err != nil {
			return nil, err
		}
		synced = append(synced, upserted)
	}
	s.systemSkillsSynced = true
	return synced, nil
}

func (s *AgentService) UpdateAgentSkills(tenantID, agentID string, req *UpdateAgentSkillsRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	if err := s.ensureSystemSkillsSynced(); err != nil {
		return err
	}
	fixedSkillIDs, err := s.fixedSkillIDs(tenantID)
	if err != nil {
		return err
	}
	mergedSkillIDs := mergeFixedSkillIDs(req.SkillIDs, fixedSkillIDs)
	if err := s.validateAgentSkillSelection(tenantID, mergedSkillIDs); err != nil {
		return err
	}
	return s.skillStore.ReplaceAgentSkillBindings(agentID, mergedSkillIDs)
}

func (s *AgentService) hydrateAgentBindings(definition *database.AgentDefinition) (*database.AgentDefinition, error) {
	if definition == nil {
		return nil, nil
	}
	if err := s.ensureSystemSkillsSynced(); err != nil {
		return nil, err
	}
	skillIDs, err := s.skillStore.ListAgentSkillBindings(definition.ID)
	if err != nil {
		return nil, err
	}
	fixedSkillIDs, err := s.fixedSkillIDs(definition.TenantID)
	if err != nil {
		return nil, err
	}
	definition.SkillIDs = mergeFixedSkillIDs(skillIDs, fixedSkillIDs)
	mcpServerIDs, err := s.mcpStore.ListAgentMCPBindings(definition.ID)
	if err != nil {
		return nil, err
	}
	definition.MCPServerIDs = mcpServerIDs
	knowledgeBaseIDs, err := s.agentStore.ListAgentKnowledgeBindings(definition.ID)
	if err != nil {
		return nil, err
	}
	definition.KnowledgeBaseIDs = knowledgeBaseIDs
	subagentIDs, err := s.subagentStore.ListAgentSubagentAuthorizationPublicationIDs(definition.ID)
	if err != nil {
		return nil, err
	}
	definition.SubagentIDs = subagentIDs
	return definition, nil
}

func (s *AgentService) ListMCPServers(tenantID string) ([]*database.MCPServer, error) {
	items, err := s.mcpStore.ListServers(tenantID)
	if err != nil {
		return nil, err
	}
	for _, item := range items {
		if _, err := s.hydrateMCPServer(item); err != nil {
			return nil, err
		}
	}
	return items, nil
}

func (s *AgentService) GetMCPGovernance(
	tenantID string,
	serverID string,
	actionType string,
	status string,
	failureMode string,
	limit int,
) (*MCPGovernanceResponse, error) {
	servers, err := s.ListMCPServers(tenantID)
	if err != nil {
		return nil, err
	}
	summary, err := s.buildMCPGovernanceSummary(tenantID, servers, &MCPGovernanceEventFilters{
		ServerID:    strings.TrimSpace(serverID),
		ActionType:  strings.TrimSpace(actionType),
		Status:      strings.TrimSpace(status),
		FailureMode: strings.TrimSpace(failureMode),
		Limit:       limit,
	})
	if err != nil {
		return nil, err
	}
	return &MCPGovernanceResponse{
		Servers: servers,
		Summary: summary,
		Total:   len(servers),
	}, nil
}

func (s *AgentService) GetMCPAuditReport(tenantID string, limit int) (*MCPServerAuditReport, error) {
	servers, err := s.ListMCPServers(tenantID)
	if err != nil {
		return nil, err
	}
	if limit <= 0 {
		limit = 12
	}
	recentEvents, err := s.mcpStore.ListTenantServerEvents(tenantID, "", "", "", "", limit)
	if err != nil {
		return nil, err
	}
	return buildMCPAuditReportFromHydratedServers(tenantID, servers, recentEvents, limit, time.Now().UTC()), nil
}

func buildMCPAuditReportFromHydratedServers(
	tenantID string,
	servers []*database.MCPServer,
	recentEvents []*database.MCPServerEvent,
	limit int,
	generatedAt time.Time,
) *MCPServerAuditReport {
	if limit <= 0 {
		limit = 12
	}
	report := &MCPServerAuditReport{
		TenantID:           tenantID,
		GeneratedAt:        generatedAt.UTC(),
		Overview:           &MCPServerAuditReportOverview{},
		TopRiskServers:     make([]*MCPServerAuditServerSnapshot, 0),
		ScoreDistribution:  map[string]int{"low": 0, "medium": 0, "high": 0, "critical": 0},
		FailureModeCounts:  map[string]int{},
		ActionTypeCounts:   map[string]int{},
		RecommendedActions: []string{},
	}

	scores := make([]int, 0, len(servers))
	for _, server := range servers {
		if server == nil || server.SecurityScore == nil {
			continue
		}
		scores = append(scores, server.SecurityScore.Score)
		report.Overview.TotalServers++
		switch server.SecurityScore.RiskLevel {
		case "low":
			report.Overview.LowRiskCount++
			report.ScoreDistribution["low"]++
		case "medium":
			report.Overview.MediumRiskCount++
			report.ScoreDistribution["medium"]++
		case "high":
			report.Overview.HighRiskCount++
			report.ScoreDistribution["high"]++
		case "critical":
			report.Overview.CriticalRiskCount++
			report.ScoreDistribution["critical"]++
		}
		if server.Recovery != nil {
			if server.Recovery.Status == "blocked" {
				report.Overview.BlockedCount++
			}
			if server.Recovery.Recoverable && server.Recovery.Status != "healthy" {
				report.Overview.RecoveringCount++
			}
		}
		if server.Catalog != nil && server.Catalog.IsStale {
			report.Overview.StaleCount++
		}
		if server.Connection != nil && server.Connection.Status == "untested" {
			report.Overview.UntestedCount++
		}
		failureMode := ""
		if server.Recovery != nil {
			failureMode = strings.TrimSpace(server.Recovery.FailureMode)
		}
		report.TopRiskServers = append(report.TopRiskServers, &MCPServerAuditServerSnapshot{
			ServerID:    server.ID,
			ServerName:  server.Name,
			Transport:   server.Transport,
			Status:      server.Status,
			Score:       server.SecurityScore.Score,
			RiskLevel:   server.SecurityScore.RiskLevel,
			Summary:     server.SecurityScore.Summary,
			FailureMode: failureMode,
			Recoverable: server.Recovery != nil && server.Recovery.Recoverable,
			BindingCount: func() int {
				if server.BindingUsage == nil {
					return 0
				}
				return server.BindingUsage.AgentCount
			}(),
			ActiveCount: func() int {
				if server.BindingUsage == nil {
					return 0
				}
				return server.BindingUsage.ActiveAgentCount
			}(),
			EventCount:   len(server.Events),
			LastTestedAt: server.LastTestedAt,
			EvaluatedAt:  server.SecurityScore.EvaluatedAt,
			Breakdown:    server.SecurityScore.Breakdown,
		})
		for _, event := range server.Events {
			if event == nil {
				continue
			}
			if strings.TrimSpace(event.FailureMode) != "" && strings.TrimSpace(event.FailureMode) != "none" {
				report.FailureModeCounts[strings.TrimSpace(event.FailureMode)]++
			}
			if strings.TrimSpace(event.ActionType) != "" {
				report.ActionTypeCounts[strings.TrimSpace(event.ActionType)]++
			}
		}
	}

	if len(scores) > 0 {
		sort.Ints(scores)
		sum := 0
		for _, score := range scores {
			sum += score
		}
		report.Overview.AverageScore = float64(sum) / float64(len(scores))
		report.Overview.MedianScore = scores[len(scores)/2]
	}

	sort.SliceStable(report.TopRiskServers, func(i, j int) bool {
		if report.TopRiskServers[i].Score != report.TopRiskServers[j].Score {
			return report.TopRiskServers[i].Score < report.TopRiskServers[j].Score
		}
		return report.TopRiskServers[i].ServerName < report.TopRiskServers[j].ServerName
	})
	if len(report.TopRiskServers) > limit {
		report.TopRiskServers = report.TopRiskServers[:limit]
	}

	report.RecentEvents = recentEvents
	for _, event := range recentEvents {
		if event == nil {
			continue
		}
		if strings.TrimSpace(event.FailureMode) != "" && strings.TrimSpace(event.FailureMode) != "none" {
			report.FailureModeCounts[strings.TrimSpace(event.FailureMode)]++
		}
		if strings.TrimSpace(event.ActionType) != "" {
			report.ActionTypeCounts[strings.TrimSpace(event.ActionType)]++
		}
	}

	switch {
	case report.Overview.CriticalRiskCount > 0 || report.Overview.BlockedCount > 0:
		report.RecommendedActions = append(report.RecommendedActions, "先处理 critical/blocked server，再处理 stale 和 untested 项。")
	case report.Overview.HighRiskCount > 0:
		report.RecommendedActions = append(report.RecommendedActions, "优先修复高风险 server 的连接和 catalog，再恢复绑定。")
	default:
		report.RecommendedActions = append(report.RecommendedActions, "继续按连接测试、catalog 刷新和审计轮转保持稳定。")
	}
	if report.Overview.StaleCount > 0 {
		report.RecommendedActions = append(report.RecommendedActions, "对 stale catalog server 重新执行 refresh，压缩旧工具快照。")
	}
	if report.Overview.UntestedCount > 0 {
		report.RecommendedActions = append(report.RecommendedActions, "补齐 untested server 的连接验证，建立新基线。")
	}

	return report
}

func (s *AgentService) CreateMCPServer(tenantID, userID string, req *MCPServerUpsertRequest) (*database.MCPServer, error) {
	server := &database.MCPServer{
		TenantID:  tenantID,
		Name:      strings.TrimSpace(req.Name),
		Transport: strings.TrimSpace(req.Transport),
		Endpoint:  strings.TrimSpace(req.Endpoint),
		Command:   strings.TrimSpace(req.Command),
		Args:      database.NormalizeJSONRawForExport(req.Args, `[]`),
		Env:       database.NormalizeJSONRawForExport(req.Env, `{}`),
		Status:    defaultString(strings.TrimSpace(req.Status), "active"),
		Metadata:  database.NormalizeJSONRawForExport(req.Metadata, `{}`),
		CreatedBy: stringPtr(userID),
	}
	if server.Name == "" || server.Transport == "" {
		return nil, errors.New("name and transport are required")
	}
	if err := validateMCPServer(server); err != nil {
		return nil, err
	}
	created, err := s.mcpStore.CreateServer(server)
	if err != nil {
		return nil, err
	}
	hydrated, err := s.hydrateMCPServer(created)
	if err != nil {
		return nil, err
	}
	event, _ := s.recordMCPServerEvent(tenantID, userID, hydrated, "server.updated", "create", "succeeded", "server_created", "MCP server 已创建。")
	hydrated = prependMCPServerEvent(hydrated, event)
	return hydrated, nil
}

func (s *AgentService) UpdateMCPServer(tenantID, userID, serverID string, req *MCPServerUpsertRequest) (*database.MCPServer, error) {
	current, err := s.mcpStore.GetServer(serverID, tenantID)
	if err != nil {
		return nil, err
	}
	server := &database.MCPServer{
		ID:        serverID,
		TenantID:  tenantID,
		Name:      defaultString(strings.TrimSpace(req.Name), current.Name),
		Transport: defaultString(strings.TrimSpace(req.Transport), current.Transport),
		Endpoint:  firstNonEmpty(strings.TrimSpace(req.Endpoint), current.Endpoint),
		Command:   firstNonEmpty(strings.TrimSpace(req.Command), current.Command),
		Args:      mergeJSONRaw(current.Args, req.Args, `[]`),
		Env:       mergeMaskedSecretJSONRaw(current.Env, req.Env, `{}`),
		Status:    defaultString(strings.TrimSpace(req.Status), current.Status),
		Metadata:  mergeMaskedSecretJSONRaw(current.Metadata, req.Metadata, `{}`),
		UpdatedBy: stringPtr(userID),
	}
	if err := validateMCPServer(server); err != nil {
		return nil, err
	}
	updated, err := s.mcpStore.UpdateServer(server)
	if err != nil {
		return nil, err
	}
	hydrated, err := s.hydrateMCPServer(updated)
	if err != nil {
		return nil, err
	}
	event, _ := s.recordMCPServerEvent(tenantID, userID, hydrated, "server.updated", "update", "succeeded", "server_updated", "MCP server 配置已更新。")
	hydrated = prependMCPServerEvent(hydrated, event)
	return hydrated, nil
}

func (s *AgentService) GetMCPServer(tenantID, serverID string) (*database.MCPServer, error) {
	server, err := s.mcpStore.GetServer(serverID, tenantID)
	if err != nil {
		return nil, err
	}
	return s.hydrateMCPServer(server)
}

func prependMCPServerEvent(server *database.MCPServer, event *database.MCPServerEvent) *database.MCPServer {
	if server == nil || event == nil {
		return server
	}
	events := make([]*database.MCPServerEvent, 0, len(server.Events)+1)
	events = append(events, event)
	for _, item := range server.Events {
		if item == nil || item.ID == event.ID {
			continue
		}
		events = append(events, item)
	}
	server.Events = events
	return server
}

func (s *AgentService) DeleteMCPServer(tenantID, userID, serverID string) error {
	server, err := s.GetMCPServer(tenantID, serverID)
	if err != nil {
		return err
	}
	bindingAgents, bindingCount, _, _, err := s.mcpStore.ListServerBindingAgents(serverID, tenantID, 5)
	if err != nil {
		return err
	}
	if bindingCount > 0 {
		return fmt.Errorf(
			"mcp server %s is still bound to %d agent(s): %s; remove those bindings from each agent's extensions page before deleting the server",
			serverID,
			bindingCount,
			summarizeMCPBindingAgents(bindingAgents),
		)
	}
	_, _ = s.recordMCPServerEvent(tenantID, userID, server, "server.deleted", "delete", "succeeded", "server_deleted", "MCP server 已删除。")
	if err := s.mcpStore.DeleteServer(serverID, tenantID); err != nil {
		return err
	}
	return nil
}

func (s *AgentService) TestMCPServer(ctx context.Context, tenantID, serverID, userID string) (*MCPServerTestResponse, error) {
	if _, err := s.mcpStore.GetServer(serverID, tenantID); err != nil {
		return nil, err
	}
	result, err := s.aiClient.TestMCPServer(ctx, tenantID, serverID)
	if err != nil {
		if server, getErr := s.GetMCPServer(tenantID, serverID); getErr == nil {
			event, _ := s.recordMCPServerEvent(tenantID, userID, server, "server.tested", "test", "failed", "connection_failed", "MCP server 连接测试失败。")
			server = prependMCPServerEvent(server, event)
		}
		return nil, err
	}
	server, err := s.GetMCPServer(tenantID, serverID)
	if err != nil {
		return nil, err
	}
	status := "succeeded"
	failureMode := "connection_healthy"
	summary := "MCP server 连接测试已完成。"
	if ok, exists := result["ok"].(bool); exists && !ok {
		status = "failed"
		failureMode = "connection_failed"
		summary = "MCP server 连接测试返回失败结果。"
	}
	event, _ := s.recordMCPServerEvent(tenantID, userID, server, "server.tested", "test", status, failureMode, summary)
	server = prependMCPServerEvent(server, event)
	return &MCPServerTestResponse{
		Result:       maskSensitiveObject(result, false),
		Server:       server,
		Connection:   server.Connection,
		Catalog:      server.Catalog,
		Availability: server.Availability,
	}, nil
}

func (s *AgentService) RefreshMCPServerTools(tenantID, serverID, userID string) (*MCPServerRefreshResponse, error) {
	if _, err := s.mcpStore.GetServer(serverID, tenantID); err != nil {
		return nil, err
	}
	items, err := s.aiClient.RefreshMCPServerTools(context.Background(), tenantID, serverID)
	if err != nil {
		if server, getErr := s.GetMCPServer(tenantID, serverID); getErr == nil {
			_, _ = s.recordMCPServerEvent(tenantID, userID, server, "catalog.refreshed", "refresh", "failed", "refresh_failed", "MCP catalog 刷新失败。")
		}
		return nil, err
	}
	for _, item := range items {
		item.InputSchema = maskSensitiveJSONRaw(item.InputSchema, false)
		item.Metadata = maskSensitiveJSONRaw(item.Metadata, false)
	}
	server, err := s.GetMCPServer(tenantID, serverID)
	if err != nil {
		return nil, err
	}
	refreshFailureMode := "catalog_ready"
	refreshSummary := fmt.Sprintf("MCP catalog 已刷新，共发现 %d 个工具。", len(items))
	if len(items) == 0 {
		refreshFailureMode = "catalog_empty"
		refreshSummary = "MCP catalog 已刷新，但未发现任何工具。"
	}
	event, _ := s.recordMCPServerEvent(tenantID, userID, server, "catalog.refreshed", "refresh", "succeeded", refreshFailureMode, refreshSummary)
	server = prependMCPServerEvent(server, event)
	return &MCPServerRefreshResponse{
		Tools:        items,
		Total:        len(items),
		Server:       server,
		Connection:   server.Connection,
		Catalog:      server.Catalog,
		Availability: server.Availability,
	}, nil
}

func (s *AgentService) RunMCPServerBulkAction(tenantID, userID string, req *MCPServerBulkActionRequest) (*MCPServerBulkActionResponse, error) {
	action := strings.TrimSpace(strings.ToLower(req.Action))
	if action == "" {
		return nil, errors.New("action is required")
	}

	serverIDs := normalizeServerIDs(req.ServerIDs)
	if len(serverIDs) == 0 {
		return nil, errors.New("server_ids is required")
	}

	groupBy := normalizeMCPBulkGroupBy(req.GroupBy)
	maxBatchSize := req.MaxBatchSize
	if maxBatchSize <= 0 {
		maxBatchSize = len(serverIDs)
	}
	if maxBatchSize <= 0 {
		maxBatchSize = 1
	}
	retryFailed := req.RetryFailed
	if retryFailed < 0 {
		retryFailed = 0
	}

	orderedBy := "impact_and_recovery"
	previewOnly := req.PreviewOnly
	candidates := make([]mcpBulkServerCandidate, 0, len(serverIDs))
	for index, serverID := range serverIDs {
		server, err := s.GetMCPServer(tenantID, serverID)
		if err != nil {
			return nil, err
		}
		candidates = append(candidates, mcpBulkServerCandidate{
			server: server,
			order:  index,
		})
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		return compareMCPBulkCandidates(candidates[i], candidates[j])
	})

	recommendations := make([]*MCPServerBulkActionRecommendation, 0, len(candidates))
	for index, candidate := range candidates {
		recommendations = append(recommendations, buildMCPBulkRecommendation(candidate.server, action, index+1))
	}
	generatedAt := time.Now().UTC()
	preview, previewPayload, err := buildMCPBulkPreview(action, true, groupBy, maxBatchSize, retryFailed, generatedAt, candidates, recommendations)
	if err != nil {
		return nil, err
	}

	if previewOnly {
		_, _ = s.recordMCPBulkActionAuditEvent(
			tenantID,
			userID,
			"preview",
			preview,
			nil,
			"preview_generated",
			"MCP 批量治理预演已生成。",
		)
		governance, err := s.GetMCPGovernance(tenantID, "", "", "", "", 0)
		if err != nil {
			return nil, err
		}
		return &MCPServerBulkActionResponse{
			Action:  action,
			Results: []*MCPServerBulkActionResult{},
			Total:   len(candidates),
			Success: 0,
			Failed:  0,
			Summary: governance.Summary,
			Execution: &MCPServerBulkActionExecution{
				GroupBy:       groupBy,
				MaxBatchSize:  maxBatchSize,
				RetryFailed:   retryFailed,
				SelectedCount: len(candidates),
				GroupCount:    countMCPBulkGroups(candidates, groupBy),
				PreviewOnly:   true,
				OrderedBy:     orderedBy,
			},
			Preview: preview,
		}, nil
	}

	if preview.RequiresConfirmation && !req.Confirmed {
		return nil, errors.New("bulk action requires confirmed=true after preview review")
	}
	if strings.TrimSpace(req.PreviewToken) == "" {
		return nil, errors.New("preview_token is required for bulk execution")
	}
	tokenPayload, err := decodeMCPBulkPreviewToken(req.PreviewToken)
	if err != nil {
		return nil, err
	}
	if err := validateMCPBulkPreviewToken(tokenPayload, previewPayload, action, groupBy, maxBatchSize, retryFailed, serverIDs); err != nil {
		return nil, err
	}
	driftedServers := detectMCPBulkPreviewDrift(tokenPayload, candidates)
	if len(driftedServers) > 0 {
		_, _ = s.recordMCPBulkActionAuditEvent(
			tenantID,
			userID,
			"execute",
			preview,
			driftedServers,
			"preview_state_drift",
			"MCP 批量治理执行前检测到 server 状态漂移，已阻止继续执行。",
		)
		return nil, fmt.Errorf("preview state drift detected for %s; regenerate preview before execution", strings.Join(driftedServers, ", "))
	}

	groupedServerIDs := map[string][]*database.MCPServer{}
	groupOrder := make([]string, 0)
	for _, candidate := range candidates {
		server := candidate.server
		groupKey := buildMCPBulkGroupKey(server, groupBy)
		if _, exists := groupedServerIDs[groupKey]; !exists {
			groupOrder = append(groupOrder, groupKey)
		}
		groupedServerIDs[groupKey] = append(groupedServerIDs[groupKey], server)
	}

	results := make([]*MCPServerBulkActionResult, 0, len(serverIDs))
	groups := make([]*MCPServerBulkActionGroup, 0, len(groupOrder))
	success := 0
	failed := 0

	for _, groupKey := range groupOrder {
		groupServers := groupedServerIDs[groupKey]
		group := &MCPServerBulkActionGroup{
			Key:     groupKey,
			Label:   buildMCPBulkGroupLabel(groupKey, groupBy, groupServers),
			Results: make([]*MCPServerBulkActionResult, 0, len(groupServers)),
		}
		for start := 0; start < len(groupServers); start += maxBatchSize {
			end := start + maxBatchSize
			if end > len(groupServers) {
				end = len(groupServers)
			}
			batch := groupServers[start:end]
			for _, server := range batch {
				result := s.runSingleMCPBulkAction(tenantID, userID, action, server)
				result.GroupKey = groupKey
				for attempt := 0; !result.OK && attempt < retryFailed; attempt++ {
					refreshedServer, err := s.GetMCPServer(tenantID, server.ID)
					if err == nil {
						server = refreshedServer
					}
					result = s.runSingleMCPBulkAction(tenantID, userID, action, server)
					result.GroupKey = groupKey
					result.Attempts = attempt + 2
				}
				if result.Attempts == 0 {
					result.Attempts = 1
				}
				group.Total++
				if result.OK {
					group.Success++
					success++
				} else {
					group.Failed++
					failed++
				}
				group.Results = append(group.Results, result)
				results = append(results, result)
			}
		}
		groups = append(groups, group)
	}

	governance, err := s.GetMCPGovernance(tenantID, "", "", "", "", 0)
	if err != nil {
		return nil, err
	}
	followUp := buildMCPBulkFollowUpPlan(results, nil)
	completedPreview, _, err := buildMCPBulkPreview(action, false, groupBy, maxBatchSize, retryFailed, generatedAt, candidates, recommendations)
	if err != nil {
		return nil, err
	}
	_, _ = s.recordMCPBulkActionAuditEvent(
		tenantID,
		userID,
		"execute",
		completedPreview,
		nil,
		"bulk_action_executed",
		fmt.Sprintf("MCP 批量治理已执行，成功 %d 个，失败 %d 个。", success, failed),
	)

	return &MCPServerBulkActionResponse{
		Action:  action,
		Results: results,
		Total:   len(results),
		Success: success,
		Failed:  failed,
		Summary: governance.Summary,
		Execution: &MCPServerBulkActionExecution{
			GroupBy:       groupBy,
			MaxBatchSize:  maxBatchSize,
			RetryFailed:   retryFailed,
			SelectedCount: len(serverIDs),
			GroupCount:    len(groups),
			PreviewOnly:   false,
			OrderedBy:     orderedBy,
		},
		Groups:   groups,
		Preview:  completedPreview,
		FollowUp: followUp,
	}, nil
}

func (s *AgentService) runSingleMCPBulkAction(tenantID, userID, action string, server *database.MCPServer) *MCPServerBulkActionResult {
	result := &MCPServerBulkActionResult{
		Action: action,
	}
	if server != nil {
		result.ServerID = server.ID
		result.ServerName = server.Name
		if server.Recovery != nil {
			result.FailureMode = strings.TrimSpace(server.Recovery.FailureMode)
			result.RecoveryStatus = strings.TrimSpace(server.Recovery.Status)
			result.SuggestedFollowUps = cloneRecoveryActions(server.Recovery.Actions, action)
			result.RecommendedPriority = highestRecoveryPriority(server.Recovery.Actions)
			if server.Recovery.Impact != nil {
				result.ImpactSummary = strings.TrimSpace(server.Recovery.Impact.Summary)
			}
		}
	}
	serverID := result.ServerID

	switch action {
	case "test":
		response, err := s.TestMCPServer(context.Background(), tenantID, serverID, userID)
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			result.SuggestedFollowUps = appendMCPBulkFailureFollowUps(server, action, result.SuggestedFollowUps)
			return result
		}
		result.OK = true
		if response.Connection != nil && strings.TrimSpace(response.Connection.Summary) != "" {
			result.Message = response.Connection.Summary
		} else {
			result.Message = "连接测试已完成"
		}
		result.Server = response.Server
		result = updateMCPBulkResultFromServer(result, response.Server, action)
	case "refresh":
		response, err := s.RefreshMCPServerTools(tenantID, serverID, userID)
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			result.SuggestedFollowUps = appendMCPBulkFailureFollowUps(server, action, result.SuggestedFollowUps)
			return result
		}
		result.OK = true
		result.Message = fmt.Sprintf("已刷新 %d 个工具", response.Total)
		result.Server = response.Server
		result = updateMCPBulkResultFromServer(result, response.Server, action)
	case "enable":
		currentServer := server
		if currentServer == nil {
			var err error
			currentServer, err = s.GetMCPServer(tenantID, serverID)
			if err != nil {
				result.OK = false
				result.Message = err.Error()
				return result
			}
		}
		updated, err := s.UpdateMCPServer(tenantID, userID, serverID, &MCPServerUpsertRequest{
			Name:      currentServer.Name,
			Transport: currentServer.Transport,
			Endpoint:  currentServer.Endpoint,
			Command:   currentServer.Command,
			Args:      currentServer.Args,
			Env:       currentServer.Env,
			Metadata:  currentServer.Metadata,
			Status:    "active",
		})
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			result.SuggestedFollowUps = appendMCPBulkFailureFollowUps(currentServer, action, result.SuggestedFollowUps)
			return result
		}
		event, _ := s.recordMCPServerEvent(tenantID, userID, updated, "server.updated", "enable", "succeeded", "server_enabled", "MCP server 已重新启用。")
		updated = prependMCPServerEvent(updated, event)
		result.OK = true
		result.Message = "已重新启用"
		result.Server = updated
		result = updateMCPBulkResultFromServer(result, updated, action)
	default:
		result.OK = false
		result.Message = fmt.Sprintf("unsupported action %s", action)
	}

	return result
}

func normalizeMCPBulkGroupBy(raw string) string {
	value := strings.TrimSpace(strings.ToLower(raw))
	switch value {
	case "", "none":
		return "none"
	case "status", "transport", "failure_mode":
		return value
	default:
		return "none"
	}
}

func buildMCPBulkGroupKey(server *database.MCPServer, groupBy string) string {
	if server == nil {
		return "unknown"
	}
	switch groupBy {
	case "status":
		return firstNonEmpty(strings.TrimSpace(server.Status), "unknown")
	case "transport":
		return firstNonEmpty(strings.TrimSpace(server.Transport), "unknown")
	case "failure_mode":
		if server.Recovery != nil {
			return firstNonEmpty(strings.TrimSpace(server.Recovery.FailureMode), "none")
		}
		return "none"
	default:
		return "all"
	}
}

func buildMCPBulkGroupLabel(groupKey, groupBy string, servers []*database.MCPServer) string {
	impactCount := 0
	activeImpactCount := 0
	for _, server := range servers {
		if server == nil || server.Recovery == nil || server.Recovery.Impact == nil {
			continue
		}
		impactCount += server.Recovery.Impact.AgentCount
		activeImpactCount += server.Recovery.Impact.ActiveAgentCount
	}
	impactSuffix := ""
	if impactCount > 0 {
		impactSuffix = fmt.Sprintf(" · 影响 %d 个 agent（active %d）", impactCount, activeImpactCount)
	}
	switch groupBy {
	case "status":
		return fmt.Sprintf("按状态分组: %s%s", groupKey, impactSuffix)
	case "transport":
		return fmt.Sprintf("按 transport 分组: %s%s", groupKey, impactSuffix)
	case "failure_mode":
		return fmt.Sprintf("按故障模式分组: %s%s", groupKey, impactSuffix)
	default:
		if impactSuffix != "" {
			return fmt.Sprintf("全部选中服务器%s", impactSuffix)
		}
		return "全部选中服务器"
	}
}

func countMCPBulkGroups(candidates []mcpBulkServerCandidate, groupBy string) int {
	if len(candidates) == 0 {
		return 0
	}
	seen := map[string]struct{}{}
	for _, candidate := range candidates {
		key := buildMCPBulkGroupKey(candidate.server, groupBy)
		seen[key] = struct{}{}
	}
	return len(seen)
}

func compareMCPBulkCandidates(left, right mcpBulkServerCandidate) bool {
	leftScore := scoreMCPBulkServer(left.server)
	rightScore := scoreMCPBulkServer(right.server)
	if leftScore != rightScore {
		return leftScore > rightScore
	}
	leftPriority := scoreMCPRecoveryPriority(left.server)
	rightPriority := scoreMCPRecoveryPriority(right.server)
	if leftPriority != rightPriority {
		return leftPriority > rightPriority
	}
	return left.order < right.order
}

func scoreMCPBulkServer(server *database.MCPServer) int {
	if server == nil {
		return 0
	}
	score := 0
	if server.Recovery != nil {
		score += 100 * scoreMCPRecoveryStatus(server.Recovery.Status)
		score += 25 * scoreMCPRecoveryPriority(server)
		if server.Recovery.Impact != nil {
			score += server.Recovery.Impact.ActiveAgentCount * 10
			score += server.Recovery.Impact.AgentCount * 4
		}
	}
	if server.Catalog != nil && server.Catalog.IsStale {
		score += 20
	}
	if server.Connection != nil && server.Connection.Status == "untested" {
		score += 10
	}
	return score
}

func scoreMCPRecoveryStatus(status string) int {
	switch strings.TrimSpace(status) {
	case "blocked":
		return 6
	case "needs_catalog":
		return 5
	case "disabled":
		return 4
	case "stale":
		return 3
	case "verify":
		return 2
	case "healthy":
		return 0
	default:
		return 1
	}
}

func scoreMCPRecoveryPriority(server *database.MCPServer) int {
	if server == nil || server.Recovery == nil {
		return 0
	}
	return priorityWeight(highestRecoveryPriority(server.Recovery.Actions))
}

func priorityWeight(priority string) int {
	switch strings.TrimSpace(strings.ToLower(priority)) {
	case "critical":
		return 4
	case "high":
		return 3
	case "medium":
		return 2
	case "low":
		return 1
	default:
		return 0
	}
}

func highestRecoveryPriority(actions []*database.MCPRecoveryAction) string {
	best := ""
	bestWeight := 0
	for _, action := range actions {
		if action == nil {
			continue
		}
		weight := priorityWeight(action.Priority)
		if weight > bestWeight {
			bestWeight = weight
			best = strings.TrimSpace(strings.ToLower(action.Priority))
		}
	}
	return best
}

func buildMCPBulkRecommendation(server *database.MCPServer, action string, order int) *MCPServerBulkActionRecommendation {
	recommendation := &MCPServerBulkActionRecommendation{
		Order:              order,
		Action:             action,
		Priority:           "medium",
		SuggestedFollowUps: []*database.MCPRecoveryAction{},
	}
	if server == nil {
		return recommendation
	}
	recommendation.ServerID = server.ID
	recommendation.ServerName = server.Name
	if server.Recovery != nil {
		recommendation.FailureMode = strings.TrimSpace(server.Recovery.FailureMode)
		recommendation.RecoveryStatus = strings.TrimSpace(server.Recovery.Status)
		recommendation.Priority = firstNonEmpty(highestRecoveryPriority(server.Recovery.Actions), "medium")
		recommendation.SuggestedFollowUps = cloneRecoveryActions(server.Recovery.Actions, action)
		if server.Recovery.Impact != nil {
			recommendation.ImpactedAgents = server.Recovery.Impact.AgentCount
			recommendation.ActiveImpactedAgents = server.Recovery.Impact.ActiveAgentCount
			recommendation.Reason = strings.TrimSpace(server.Recovery.Impact.Summary)
		}
		if strings.TrimSpace(server.Recovery.Summary) != "" {
			if recommendation.Reason != "" {
				recommendation.Reason = fmt.Sprintf("%s %s", server.Recovery.Summary, recommendation.Reason)
			} else {
				recommendation.Reason = strings.TrimSpace(server.Recovery.Summary)
			}
		}
	}
	if recommendation.Reason == "" {
		recommendation.Reason = fmt.Sprintf("建议优先处理 %s。", firstNonEmpty(server.Name, server.ID))
	}
	return recommendation
}

func buildMCPBulkPreview(
	action string,
	previewOnly bool,
	groupBy string,
	maxBatchSize int,
	retryFailed int,
	generatedAt time.Time,
	candidates []mcpBulkServerCandidate,
	recommendations []*MCPServerBulkActionRecommendation,
) (*MCPServerBulkActionPreview, *mcpBulkPreviewTokenPayload, error) {
	selectedServerIDs := make([]string, 0, len(candidates))
	snapshots := make([]*mcpBulkPreviewStateSnapshot, 0, len(candidates))
	for _, candidate := range candidates {
		if candidate.server == nil {
			continue
		}
		selectedServerIDs = append(selectedServerIDs, candidate.server.ID)
		snapshots = append(snapshots, &mcpBulkPreviewStateSnapshot{
			ServerID:   candidate.server.ID,
			ServerName: candidate.server.Name,
			Signature:  signatureForMCPBulkPreviewServer(candidate.server),
		})
	}

	preview := &MCPServerBulkActionPreview{
		Action:               action,
		PreviewOnly:          previewOnly,
		OrderedBy:            "impact_and_recovery",
		RiskSummary:          "当前批量治理未发现显著风险。",
		RequiresConfirmation: false,
		GeneratedAt:          &generatedAt,
		ExpiresAt:            timePtr(generatedAt.Add(mcpBulkPreviewTTL)),
		SelectedServerIDs:    selectedServerIDs,
		Recommendations:      recommendations,
	}

	totalAgents := 0
	activeAgents := 0
	highRiskCount := 0
	for _, recommendation := range recommendations {
		if recommendation == nil {
			continue
		}
		totalAgents += recommendation.ImpactedAgents
		activeAgents += recommendation.ActiveImpactedAgents
		if priorityWeight(recommendation.Priority) >= 3 {
			highRiskCount++
		}
	}

	preview.RequiresConfirmation = highRiskCount > 0 || activeAgents > 0
	preview.RiskSummary = fmt.Sprintf(
		"本次批量%s将按影响面和恢复严重度排序处理 %d 个 server，覆盖 %d 个已绑定 agent，其中 %d 个处于 active 状态。",
		action,
		len(recommendations),
		totalAgents,
		activeAgents,
	)
	if preview.RequiresConfirmation {
		preview.ConfirmationMessage = "建议先核对排序靠前的阻塞项与高影响 server，再执行批量恢复。"
	}

	payload := &mcpBulkPreviewTokenPayload{
		Action:               action,
		GroupBy:              groupBy,
		MaxBatchSize:         maxBatchSize,
		RetryFailed:          retryFailed,
		GeneratedAt:          generatedAt,
		ConfirmedRequired:    preview.RequiresConfirmation,
		SelectedServerIDs:    selectedServerIDs,
		ServerStateSnapshots: snapshots,
	}
	token, err := encodeMCPBulkPreviewToken(payload)
	if err != nil {
		return nil, nil, err
	}
	preview.PreviewToken = token
	return preview, payload, nil
}

func buildMCPBulkFollowUpPlan(results []*MCPServerBulkActionResult, driftedServerIDs []string) *MCPServerBulkFollowUpPlan {
	stages := make(map[string]*MCPServerBulkFollowUpStage)
	failedServerIDs := make([]string, 0)
	recommendedActions := make([]string, 0, 6)
	compensationActions := make([]string, 0, 4)
	rollbackActions := make([]string, 0, 4)
	manualReviewReason := ""
	requiresManualReview := false
	failedActiveImpactCount := 0

	ensureStage := func(key, label, priority string) *MCPServerBulkFollowUpStage {
		if existing, ok := stages[key]; ok {
			return existing
		}
		stage := &MCPServerBulkFollowUpStage{
			Key:      key,
			Label:    label,
			Priority: priority,
		}
		stages[key] = stage
		return stage
	}

	for _, result := range results {
		if result == nil {
			continue
		}
		if !result.OK {
			failedServerIDs = append(failedServerIDs, result.ServerID)
			if strings.Contains(result.ImpactSummary, "active") || strings.Contains(result.ImpactSummary, "已绑定 agent") {
				failedActiveImpactCount++
			}
		}
		switch strings.TrimSpace(result.RecoveryStatus) {
		case "blocked":
			stage := ensureStage("blocked", "阻塞项处理", "high")
			stage.Count++
		case "needs_catalog":
			stage := ensureStage("needs_catalog", "Catalog 重建", "high")
			stage.Count++
		case "stale":
			stage := ensureStage("stale", "Catalog 收敛", "medium")
			stage.Count++
		case "verify":
			stage := ensureStage("verify", "连接复核", "medium")
			stage.Count++
		case "disabled":
			stage := ensureStage("disabled", "启用恢复", "medium")
			stage.Count++
		}
		for _, action := range result.SuggestedFollowUps {
			if action == nil {
				continue
			}
			switch strings.TrimSpace(action.Type) {
			case "test":
				recommendedActions = append(recommendedActions, "优先对仍失败或 blocked 的 server 重新执行连接测试，并确认失败模式是否已经变化。")
				compensationActions = append(compensationActions, "把失败 server 重新分组为连接复核批次，先确认连接已恢复再继续 catalog 收敛。")
			case "refresh":
				recommendedActions = append(recommendedActions, "对连接已恢复但 catalog 仍为空或过期的 server 继续刷新 Catalog，确认工具快照已经收敛。")
				compensationActions = append(compensationActions, "对 refresh 失败但连接已恢复的 server 单独重跑 catalog 刷新，避免阻塞整个治理批次。")
			case "enable":
				recommendedActions = append(recommendedActions, "对仍处于 disabled 的 server 先恢复启用，再进入连接测试与 catalog 刷新。")
				rollbackActions = append(rollbackActions, "若 enable 后立即出现更高风险失败，可临时重新置为 disabled 并通知受影响 agent 维护窗口。")
			}
		}
		if result.OK && strings.TrimSpace(result.Action) == "enable" && strings.TrimSpace(result.RecoveryStatus) == "blocked" {
			rollbackActions = append(rollbackActions, "已启用但仍 blocked 的 server 应考虑回退到 disabled，避免继续扩大不可用影响面。")
		}
	}

	stageList := make([]*MCPServerBulkFollowUpStage, 0, len(stages))
	for _, stage := range stages {
		if stage == nil {
			continue
		}
		switch stage.Key {
		case "blocked":
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 处于阻塞恢复态，应优先处理连接失败或不可达问题。", stage.Count)
		case "needs_catalog":
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 缺少可用 catalog，需要继续刷新或重建工具快照。", stage.Count)
		case "stale":
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 的 catalog 处于 stale 状态，需要继续收敛缓存。", stage.Count)
		case "verify":
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 需要继续做连接复核。", stage.Count)
		case "disabled":
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 处于 disabled 状态。", stage.Count)
		default:
			stage.Summary = fmt.Sprintf("仍有 %d 个 server 需要后续治理。", stage.Count)
		}
		stageList = append(stageList, stage)
	}
	sort.SliceStable(stageList, func(i, j int) bool {
		left := priorityWeight(stageList[i].Priority)
		right := priorityWeight(stageList[j].Priority)
		if left != right {
			return left > right
		}
		if stageList[i].Count != stageList[j].Count {
			return stageList[i].Count > stageList[j].Count
		}
		return stageList[i].Key < stageList[j].Key
	})

	failedServerIDs = uniqueNonEmptyStrings(failedServerIDs)
	driftedServerIDs = uniqueNonEmptyStrings(driftedServerIDs)
	recommendedActions = uniqueNonEmptyStrings(recommendedActions)

	status := "settled"
	summary := "本次批量治理已完成，当前没有额外后续编排压力。"
	switch {
	case len(driftedServerIDs) > 0:
		status = "drifted"
		summary = fmt.Sprintf("有 %d 个 server 在预演和执行之间发生状态漂移，需重新生成预演后再执行。", len(driftedServerIDs))
		recommendedActions = append([]string{"先重新生成批量预演，确认状态签名已经更新，再继续正式执行。"}, recommendedActions...)
		requiresManualReview = true
		manualReviewReason = "执行前检测到 preview state drift，需人工确认最新状态后再发起新批次。"
	case len(failedServerIDs) > 0:
		status = "needs_follow_up"
		summary = fmt.Sprintf("本次批量治理后仍有 %d 个 server 执行失败，需要继续做补救和状态收敛。", len(failedServerIDs))
		if failedActiveImpactCount > 0 {
			requiresManualReview = true
			manualReviewReason = "失败结果仍影响 active agent，建议人工确认批量补救顺序和维护窗口。"
		}
	default:
		for _, stage := range stageList {
			if stage == nil || stage.Count == 0 {
				continue
			}
			status = "needs_follow_up"
			summary = fmt.Sprintf("本次批量治理已执行完成，但仍有 %d 类恢复阶段需要继续收口。", len(stageList))
			break
		}
	}
	if len(recommendedActions) == 0 && status == "settled" {
		recommendedActions = append(recommendedActions, "继续观察跨页面刷新后的治理摘要，确认状态已经稳定收敛。")
	}
	if len(compensationActions) == 0 && len(failedServerIDs) > 0 {
		compensationActions = append(compensationActions, "把失败 server 拆出独立补救批次，避免继续沿用同一批次参数盲目重试。")
	}
	if len(rollbackActions) == 0 && status == "needs_follow_up" {
		rollbackActions = append(rollbackActions, "若批量恢复导致风险继续放大，可对高风险 server 暂停暴露并回到单机治理模式。")
	}

	return &MCPServerBulkFollowUpPlan{
		Status:               status,
		Summary:              summary,
		RecommendedActions:   uniqueNonEmptyStrings(recommendedActions),
		FailedServerIDs:      failedServerIDs,
		DriftedServerIDs:     driftedServerIDs,
		RecoveryStageCounts:  stageList,
		RequiresManualReview: requiresManualReview,
		ManualReviewReason:   strings.TrimSpace(manualReviewReason),
		CompensationActions:  uniqueNonEmptyStrings(compensationActions),
		RollbackActions:      uniqueNonEmptyStrings(rollbackActions),
	}
}

func encodeMCPBulkPreviewToken(payload *mcpBulkPreviewTokenPayload) (string, error) {
	if payload == nil {
		return "", errors.New("preview payload is required")
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("failed to encode mcp bulk preview token: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(encoded), nil
}

func decodeMCPBulkPreviewToken(raw string) (*mcpBulkPreviewTokenPayload, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil, errors.New("preview token is required")
	}
	decoded, err := base64.RawURLEncoding.DecodeString(trimmed)
	if err != nil {
		return nil, errors.New("invalid preview token")
	}
	payload := &mcpBulkPreviewTokenPayload{}
	if err := json.Unmarshal(decoded, payload); err != nil {
		return nil, errors.New("invalid preview token payload")
	}
	return payload, nil
}

func validateMCPBulkPreviewToken(
	tokenPayload *mcpBulkPreviewTokenPayload,
	currentPayload *mcpBulkPreviewTokenPayload,
	action string,
	groupBy string,
	maxBatchSize int,
	retryFailed int,
	serverIDs []string,
) error {
	if tokenPayload == nil || currentPayload == nil {
		return errors.New("preview token payload is required")
	}
	if time.Since(tokenPayload.GeneratedAt) > mcpBulkPreviewTTL || tokenPayload.GeneratedAt.After(time.Now().UTC().Add(1*time.Minute)) {
		return errors.New("preview token expired; regenerate preview before execution")
	}
	if tokenPayload.Action != action || tokenPayload.GroupBy != groupBy || tokenPayload.MaxBatchSize != maxBatchSize || tokenPayload.RetryFailed != retryFailed {
		return errors.New("preview token does not match current bulk action parameters")
	}
	if !sameStringSet(tokenPayload.SelectedServerIDs, serverIDs) || !sameStringSet(currentPayload.SelectedServerIDs, serverIDs) {
		return errors.New("preview token does not match selected server ids")
	}
	return nil
}

func detectMCPBulkPreviewDrift(
	tokenPayload *mcpBulkPreviewTokenPayload,
	candidates []mcpBulkServerCandidate,
) []string {
	if tokenPayload == nil {
		return nil
	}
	expected := map[string]string{}
	names := map[string]string{}
	for _, snapshot := range tokenPayload.ServerStateSnapshots {
		if snapshot == nil || strings.TrimSpace(snapshot.ServerID) == "" {
			continue
		}
		expected[snapshot.ServerID] = snapshot.Signature
		names[snapshot.ServerID] = snapshot.ServerName
	}
	drifted := make([]string, 0)
	for _, candidate := range candidates {
		if candidate.server == nil {
			continue
		}
		signature := signatureForMCPBulkPreviewServer(candidate.server)
		if expected[candidate.server.ID] != signature {
			driftName := firstNonEmpty(names[candidate.server.ID], candidate.server.Name)
			drifted = append(drifted, firstNonEmpty(driftName, candidate.server.ID))
		}
	}
	return drifted
}

func signatureForMCPBulkPreviewServer(server *database.MCPServer) string {
	if server == nil {
		return ""
	}
	payload := map[string]any{
		"id":           server.ID,
		"status":       server.Status,
		"updated_at":   server.UpdatedAt.UTC().Format(time.RFC3339Nano),
		"last_tested":  "",
		"last_error":   "",
		"connection":   "",
		"catalog":      "",
		"availability": "",
		"recovery":     "",
	}
	if server.LastTestedAt != nil {
		payload["last_tested"] = server.LastTestedAt.UTC().Format(time.RFC3339Nano)
	}
	if server.LastError != nil {
		payload["last_error"] = strings.TrimSpace(*server.LastError)
	}
	if server.Connection != nil {
		payload["connection"] = server.Connection.Status
	}
	if server.Catalog != nil {
		payload["catalog"] = fmt.Sprintf("%s:%d:%v", server.Catalog.Status, server.Catalog.ToolCount, server.Catalog.IsStale)
	}
	if server.Availability != nil {
		payload["availability"] = fmt.Sprintf("%s:%v:%s", server.Availability.Status, server.Availability.Bindable, server.Availability.Reason)
	}
	if server.Recovery != nil {
		payload["recovery"] = fmt.Sprintf("%s:%s:%v", server.Recovery.Status, server.Recovery.FailureMode, server.Recovery.Recoverable)
	}
	encoded, _ := json.Marshal(payload)
	sum := sha256.Sum256(encoded)
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func sameStringSet(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	leftSet := map[string]int{}
	for _, item := range left {
		leftSet[strings.TrimSpace(item)]++
	}
	for _, item := range right {
		trimmed := strings.TrimSpace(item)
		if leftSet[trimmed] <= 0 {
			return false
		}
		leftSet[trimmed]--
	}
	for _, count := range leftSet {
		if count != 0 {
			return false
		}
	}
	return true
}

func cloneRecoveryActions(actions []*database.MCPRecoveryAction, currentAction string) []*database.MCPRecoveryAction {
	if len(actions) == 0 {
		return []*database.MCPRecoveryAction{}
	}
	cloned := make([]*database.MCPRecoveryAction, 0, len(actions))
	for _, action := range actions {
		if action == nil || strings.TrimSpace(action.Type) == "" {
			continue
		}
		if strings.EqualFold(strings.TrimSpace(action.Type), strings.TrimSpace(currentAction)) {
			continue
		}
		cloned = append(cloned, &database.MCPRecoveryAction{
			Type:        action.Type,
			Label:       action.Label,
			Description: action.Description,
			Priority:    action.Priority,
		})
	}
	return cloned
}

func appendMCPBulkFailureFollowUps(
	server *database.MCPServer,
	action string,
	existing []*database.MCPRecoveryAction,
) []*database.MCPRecoveryAction {
	actions := append([]*database.MCPRecoveryAction{}, existing...)
	if server == nil || server.Recovery == nil {
		return actions
	}
	if len(actions) > 0 {
		return actions
	}
	return cloneRecoveryActions(server.Recovery.Actions, action)
}

func updateMCPBulkResultFromServer(
	result *MCPServerBulkActionResult,
	server *database.MCPServer,
	currentAction string,
) *MCPServerBulkActionResult {
	if result == nil || server == nil {
		return result
	}
	result.Server = server
	result.ServerID = server.ID
	result.ServerName = server.Name
	if server.Recovery != nil {
		result.FailureMode = strings.TrimSpace(server.Recovery.FailureMode)
		result.RecoveryStatus = strings.TrimSpace(server.Recovery.Status)
		result.SuggestedFollowUps = cloneRecoveryActions(server.Recovery.Actions, currentAction)
		result.RecommendedPriority = firstNonEmpty(highestRecoveryPriority(server.Recovery.Actions), result.RecommendedPriority)
		if server.Recovery.Impact != nil {
			result.ImpactSummary = strings.TrimSpace(server.Recovery.Impact.Summary)
		}
	}
	return result
}

func (s *AgentService) UpdateAgentMCPServers(tenantID, agentID string, req *UpdateAgentMCPServersRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	serverIDs := normalizeServerIDs(req.ServerIDs)
	for _, serverID := range serverIDs {
		server, err := s.mcpStore.GetServer(serverID, tenantID)
		if err != nil {
			return err
		}
		if server.Status != "active" {
			return fmt.Errorf("mcp server %s is disabled", serverID)
		}
		tools, err := s.mcpStore.ListServerTools(serverID)
		if err != nil {
			return err
		}
		if len(tools) == 0 {
			return fmt.Errorf("mcp server %s has no cached tools; run refresh tools before binding it to an agent", serverID)
		}
	}
	return s.mcpStore.ReplaceAgentMCPBindings(agentID, serverIDs)
}

func (s *AgentService) UpdateAgentKnowledgeBases(tenantID, userID, agentID string, req *UpdateAgentKnowledgeBasesRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	return s.agentStore.ReplaceAgentKnowledgeBindings(agentID, tenantID, userID, req.KnowledgeBaseIDs)
}

func (s *AgentService) ListSubagentDefinitions(tenantID string, includeArchived bool) ([]*database.SubagentDefinition, error) {
	items, err := s.subagentStore.ListSubagentDefinitions(tenantID, includeArchived)
	if err != nil {
		return nil, err
	}
	for _, item := range items {
		if _, err := s.hydrateSubagentDefinition(item); err != nil {
			return nil, err
		}
	}
	return items, nil
}

func (s *AgentService) GetSubagentDefinition(tenantID, subagentID string) (*database.SubagentDefinition, error) {
	item, err := s.subagentStore.GetSubagentDefinition(subagentID, tenantID)
	if err != nil {
		return nil, err
	}
	return s.hydrateSubagentDefinition(item)
}

func (s *AgentService) GetSubagentControlPlane(tenantID, userRole, subagentID string) (*database.SubagentControlPlane, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	controlPlane, err := s.subagentStore.GetSubagentControlPlane(subagentID, tenantID)
	if err != nil {
		return nil, err
	}
	if _, err := s.hydrateSubagentDefinition(controlPlane.Definition); err != nil {
		return nil, err
	}
	return enrichSubagentControlPlaneGovernance(controlPlane), nil
}

func (s *AgentService) GetSubagentGovernance(
	tenantID string,
	userRole string,
	filters *database.SubagentPublicationEventFilters,
) (*SubagentGovernanceResponse, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	if s.subagentStore == nil {
		return &SubagentGovernanceResponse{
			Events:  []*database.SubagentPublicationEvent{},
			Summary: buildSubagentTenantGovernanceSummary(nil, nil, filters),
			Total:   0,
			Limit:   20,
			Offset:  0,
		}, nil
	}
	page, err := s.subagentStore.ListTenantSubagentPublicationEvents(tenantID, filters)
	if err != nil {
		return nil, err
	}
	controlPlanes, err := s.listSubagentControlPlanesForGovernance(tenantID)
	if err != nil {
		return nil, err
	}
	summary := buildSubagentTenantGovernanceSummary(controlPlanes, page.Items, page.Filters)
	return &SubagentGovernanceResponse{
		Events:  page.Items,
		Summary: summary,
		Total:   page.Total,
		Limit:   page.Filters.Limit,
		Offset:  page.Filters.Offset,
	}, nil
}

func (s *AgentService) listSubagentControlPlanesForGovernance(tenantID string) ([]*database.SubagentControlPlane, error) {
	definitions, err := s.subagentStore.ListSubagentDefinitions(tenantID, true)
	if err != nil {
		return nil, err
	}
	controlPlanes := make([]*database.SubagentControlPlane, 0, len(definitions))
	for _, definition := range definitions {
		if definition == nil || strings.TrimSpace(definition.ID) == "" {
			continue
		}
		controlPlane, err := s.subagentStore.GetSubagentControlPlane(definition.ID, tenantID)
		if err != nil {
			if errors.Is(err, database.ErrSubagentDefinitionNotFound) {
				continue
			}
			return nil, err
		}
		if _, err := s.hydrateSubagentDefinition(controlPlane.Definition); err != nil {
			return nil, err
		}
		controlPlanes = append(controlPlanes, enrichSubagentControlPlaneGovernance(controlPlane))
	}
	return controlPlanes, nil
}

func (s *AgentService) CreateSubagentDefinition(tenantID, userID, userRole string, req *SubagentDefinitionUpsertRequest) (*database.SubagentDefinition, error) {
	def, err := s.buildSubagentDefinitionForWrite(tenantID, userID, userRole, "", req)
	if err != nil {
		return nil, err
	}
	created, err := s.subagentStore.CreateSubagentDefinition(def)
	if err != nil {
		return nil, err
	}
	return s.hydrateSubagentDefinition(created)
}

func (s *AgentService) UpdateSubagentDefinition(tenantID, userID, userRole, subagentID string, req *SubagentDefinitionUpsertRequest) (*database.SubagentDefinition, error) {
	def, err := s.buildSubagentDefinitionForWrite(tenantID, userID, userRole, subagentID, req)
	if err != nil {
		return nil, err
	}
	updated, err := s.subagentStore.UpdateSubagentDefinition(def)
	if err != nil {
		return nil, err
	}
	return s.hydrateSubagentDefinition(updated)
}

func (s *AgentService) DeleteSubagentDefinition(tenantID, userRole, subagentID string) error {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return err
	}
	return s.subagentStore.DeleteSubagentDefinition(subagentID, tenantID)
}

func (s *AgentService) CreateSubagentVersion(
	tenantID,
	userID,
	userRole,
	subagentID string,
	req *SubagentVersionCreateRequest,
) (*database.SubagentControlPlane, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	definition, err := s.GetSubagentDefinition(tenantID, subagentID)
	if err != nil {
		return nil, err
	}

	publicationState, err := s.subagentStore.GetSubagentPublicationState(subagentID, tenantID)
	if err != nil && !errors.Is(err, database.ErrSubagentPublicationNotFound) {
		return nil, err
	}
	publication := &database.SubagentPublication{
		DefinitionID: subagentID,
		TenantID:     subagentPublicationTenant(definition),
		Visibility:   defaultString(strings.TrimSpace(req.PublicationScope), definition.PublicationScope),
		Status:       defaultString(strings.TrimSpace(req.PublicationStatus), definition.Status),
		Metadata:     database.NormalizeJSONRawForExport(req.PublicationMetadata, `{}`),
		UpdatedBy:    stringPtr(userID),
	}
	if publicationState != nil {
		if strings.TrimSpace(req.PublicationScope) == "" {
			publication.Visibility = publicationState.PublicationScope
		}
		if strings.TrimSpace(req.PublicationStatus) == "" {
			publication.Status = publicationState.Status
		}
		if len(req.PublicationMetadata) == 0 {
			publication.Metadata = publicationState.Metadata
		}
	}

	version, err := s.subagentStore.CreateSubagentVersion(subagentID, tenantID, &database.SubagentDefinitionVersion{
		LifecycleStatus:    defaultString(strings.TrimSpace(req.LifecycleStatus), "draft"),
		SystemPrompt:       req.SystemPrompt,
		Model:              strings.TrimSpace(req.Model),
		Config:             database.NormalizeJSONRawForExport(req.Config, `{}`),
		Metadata:           database.NormalizeJSONRawForExport(req.Metadata, `{}`),
		OutputSchema:       database.NormalizeJSONRawForExport(req.OutputSchema, `{}`),
		HandoffInputSchema: database.NormalizeJSONRawForExport(req.HandoffInputSchema, `{}`),
		ToolAllowlist:      database.NormalizeJSONRawForExport(req.ToolAllowlist, `[]`),
		SkillAllowlist:     database.NormalizeJSONRawForExport(req.SkillAllowlist, `[]`),
		MCPAllowlist:       database.NormalizeJSONRawForExport(req.MCPAllowlist, `[]`),
		KnowledgePolicy:    database.NormalizeJSONRawForExport(req.KnowledgePolicy, `{}`),
		ReviewPolicy:       database.NormalizeJSONRawForExport(req.ReviewPolicy, `{}`),
		RuntimePolicy:      database.NormalizeJSONRawForExport(req.RuntimePolicy, `{}`),
		CreatedBy:          stringPtr(userID),
		UpdatedBy:          stringPtr(userID),
	}, publication, req.Publish)
	if err != nil {
		return nil, err
	}
	if req.Publish && version != nil {
		definition.VersionID = version.ID
		definition.VersionNumber = version.VersionNumber
	}
	return s.GetSubagentControlPlane(tenantID, userRole, subagentID)
}

func (s *AgentService) UpdateSubagentPublication(
	tenantID,
	userID,
	userRole,
	subagentID string,
	req *SubagentPublicationUpdateRequest,
) (*database.SubagentControlPlane, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	definition, err := s.GetSubagentDefinition(tenantID, subagentID)
	if err != nil {
		return nil, err
	}
	controlPlane, err := s.GetSubagentControlPlane(tenantID, userRole, subagentID)
	if err != nil {
		return nil, err
	}
	currentPublication, err := s.subagentStore.GetSubagentPublicationState(subagentID, tenantID)
	if err != nil && !errors.Is(err, database.ErrSubagentPublicationNotFound) {
		return nil, err
	}
	versionID := strings.TrimSpace(req.VersionID)
	if versionID == "" && currentPublication != nil {
		versionID = currentPublication.VersionID
	}
	if versionID == "" {
		return nil, errors.New("version_id is required")
	}
	var targetVersion *database.SubagentDefinitionVersion
	for _, version := range controlPlane.Versions {
		if version != nil && version.ID == versionID {
			targetVersion = version
			break
		}
	}
	if targetVersion == nil {
		return nil, fmt.Errorf("subagent version %s not found", versionID)
	}
	targetScope := defaultString(strings.TrimSpace(req.PublicationScope), definition.PublicationScope)
	targetStatus := defaultString(strings.TrimSpace(req.Status), definition.Status)
	preview := buildSubagentPublicationChangePreview(controlPlane, targetVersion, targetScope, targetStatus)
	if preview == nil {
		return nil, errors.New("failed to build subagent publication preview")
	}
	if err := validateSubagentPublicationGovernanceInputs(preview, req); err != nil {
		return nil, err
	}
	controlPlane = enrichSubagentControlPlaneGovernance(controlPlane)
	if controlPlane.Governance != nil {
		controlPlane.Governance.NextPublicationPreview = preview
	}
	if req.PreviewOnly {
		if event, err := s.recordSubagentPublicationEvent(tenantID, userID, controlPlane, currentPublication, req, preview, "previewed"); err == nil {
			controlPlane = prependSubagentPublicationEvent(controlPlane, event)
		}
		return controlPlane, nil
	}
	if preview.RequiresConfirmation && !req.Confirmed {
		return nil, errors.New("publication change requires confirmed=true after preview review")
	}

	publication := &database.SubagentPublication{
		DefinitionID: subagentID,
		VersionID:    versionID,
		TenantID:     subagentPublicationTenant(definition),
		Visibility:   targetScope,
		Status:       targetStatus,
		Metadata:     database.NormalizeJSONRawForExport(req.PublicationMetadata, `{}`),
		UpdatedBy:    stringPtr(userID),
	}
	if currentPublication != nil {
		if strings.TrimSpace(req.PublicationScope) == "" {
			publication.Visibility = currentPublication.PublicationScope
		}
		if strings.TrimSpace(req.Status) == "" {
			publication.Status = currentPublication.Status
		}
		if len(req.PublicationMetadata) == 0 {
			publication.Metadata = currentPublication.Metadata
		}
	}

	if _, err := s.subagentStore.UpdateSubagentPublication(subagentID, tenantID, publication); err != nil {
		return nil, err
	}
	updatedControlPlane, err := s.GetSubagentControlPlane(tenantID, userRole, subagentID)
	if err != nil {
		return nil, err
	}
	if event, err := s.recordSubagentPublicationEvent(tenantID, userID, updatedControlPlane, currentPublication, req, preview, "executed"); err == nil {
		updatedControlPlane = prependSubagentPublicationEvent(updatedControlPlane, event)
	}
	return updatedControlPlane, nil
}

func (s *AgentService) FreezeSubagentMetadataAliases(
	tenantID,
	userID,
	userRole string,
	req *SubagentMetadataAliasFreezeRequest,
) (*SubagentGovernanceResponse, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	if req == nil {
		req = &SubagentMetadataAliasFreezeRequest{}
	}

	controlPlanes, err := s.listSubagentControlPlanesForGovernance(tenantID)
	if err != nil {
		return nil, err
	}
	preview := buildSubagentMetadataAliasFreezePreview(controlPlanes, req)
	if preview == nil {
		return nil, errors.New("failed to build metadata alias freeze preview")
	}

	if req.PreviewOnly {
		if events, eventErr := s.recordSubagentMetadataAliasFreezeEvent(tenantID, userID, preview, 0, "previewed"); eventErr == nil && len(events) > 0 {
			summary := buildSubagentTenantGovernanceSummary(controlPlanes, events, &database.SubagentPublicationEventFilters{Limit: 20, Offset: 0})
			return &SubagentGovernanceResponse{
				Events:                     events,
				Summary:                    summary,
				MetadataAliasFreezePreview: preview,
				Total:                      len(events),
				Limit:                      20,
				Offset:                     0,
			}, nil
		}
		return &SubagentGovernanceResponse{
			Events:                     []*database.SubagentPublicationEvent{},
			Summary:                    buildSubagentTenantGovernanceSummary(controlPlanes, nil, &database.SubagentPublicationEventFilters{Limit: 20, Offset: 0}),
			MetadataAliasFreezePreview: preview,
			Total:                      0,
			Limit:                      20,
			Offset:                     0,
		}, nil
	}

	if !preview.Executable {
		return nil, errors.New(firstNonEmpty(preview.BlockedReason, "metadata alias freeze is currently blocked"))
	}
	if preview.RequiresConfirmation && !req.Confirmed {
		return nil, errors.New("metadata alias freeze requires confirmed=true after preview review")
	}

	if _, err := s.subagentStore.CanonicalizeSubagentMetadataAliases(preview.DefinitionIDs, tenantID, stringPtr(userID)); err != nil {
		return nil, err
	}

	updatedControlPlanes, err := s.listSubagentControlPlanesForGovernance(tenantID)
	if err != nil {
		return nil, err
	}
	events, total, filters, err := s.loadTenantGovernanceEventsWithRecordedFreezeEvent(tenantID, userID, updatedControlPlanes, preview)
	if err != nil {
		return nil, err
	}
	return &SubagentGovernanceResponse{
		Events:                     events,
		Summary:                    buildSubagentTenantGovernanceSummary(updatedControlPlanes, events, filters),
		MetadataAliasFreezePreview: buildSubagentMetadataAliasFreezePreview(updatedControlPlanes, req),
		Total:                      total,
		Limit:                      filters.Limit,
		Offset:                     filters.Offset,
	}, nil
}

func (s *AgentService) CreateSubagentTestRun(
	ctx context.Context,
	tenantID,
	userID,
	userRole,
	subagentID string,
	req *SubagentTestRunRequest,
) (*database.AgentRun, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	controlPlane, err := s.GetSubagentControlPlane(tenantID, userRole, subagentID)
	if err != nil {
		return nil, err
	}
	if controlPlane.Definition == nil {
		return nil, database.ErrSubagentDefinitionNotFound
	}

	requestedVersionID := strings.TrimSpace(req.VersionID)
	var selectedVersion *database.SubagentDefinitionVersion
	if requestedVersionID != "" {
		for _, version := range controlPlane.Versions {
			if version != nil && version.ID == requestedVersionID {
				selectedVersion = version
				break
			}
		}
		if selectedVersion == nil {
			return nil, fmt.Errorf("subagent version %s not found", requestedVersionID)
		}
	} else if controlPlane.Publication != nil {
		for _, version := range controlPlane.Versions {
			if version != nil && version.ID == controlPlane.Publication.VersionID {
				selectedVersion = version
				break
			}
		}
	}
	if selectedVersion == nil && len(controlPlane.Versions) > 0 {
		selectedVersion = controlPlane.Versions[0]
	}
	if selectedVersion == nil {
		return nil, errors.New("subagent has no version to test")
	}

	hostAgentID := strings.TrimSpace(req.AgentDefinitionID)
	if hostAgentID == "" {
		hostAgentID = strings.TrimSpace(controlPlane.Definition.HostAgentDefinitionID)
	}
	if hostAgentID == "" {
		return nil, errors.New("agent_definition_id is required for test run")
	}
	hostAgent, err := s.agentStore.GetAgentDefinition(hostAgentID, tenantID)
	if err != nil {
		return nil, err
	}
	if hostAgent.Status != "active" {
		return nil, fmt.Errorf("host agent definition %s is not active", hostAgentID)
	}

	sessionID := strings.TrimSpace(req.SessionID)
	if err := s.ensureRunSession(tenantID, userID, sessionID); err != nil {
		return nil, err
	}

	publicationState := controlPlane.Publication
	if publicationState != nil && publicationState.VersionID != selectedVersion.ID {
		publicationState = nil
	}
	managedSubagentPayload := s.buildManagedSubagentRunMetadata(controlPlane.Definition, selectedVersion, publicationState)
	metadata := map[string]any{}
	for key, value := range req.Metadata {
		metadata[key] = value
	}
	metadata["managed_subagent"] = managedSubagentPayload
	metadata["managed_subagent_test"] = map[string]any{
		"subagent_definition_id": controlPlane.Definition.ID,
		"version_id":             selectedVersion.ID,
		"publication_id":         managedSubagentPayload["publication_id"],
		"triggered_by":           "admin_console",
	}

	autoStart := true
	if req.AutoStart != nil {
		autoStart = *req.AutoStart
	}
	return s.aiClient.CreateAgentRun(ctx, &grpc.AgentRunCreateRequest{
		AgentDefinitionID: hostAgentID,
		TenantID:          tenantID,
		UserID:            userID,
		SessionID:         sessionID,
		Input:             req.Input,
		Metadata:          metadata,
		AutoStart:         autoStart,
	})
}

func (s *AgentService) UpdateAgentSubagents(tenantID, userID, agentID string, req *UpdateAgentSubagentsRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	publicationIDs := normalizeServerIDs(req.SubagentIDs)
	published, err := s.subagentStore.ListPublishedSubagentsByPublicationIDs(tenantID, publicationIDs)
	if err != nil {
		return err
	}

	publicationsByID := make(map[string]*database.SubagentDefinition, len(published))
	for _, item := range published {
		publicationsByID[item.PublicationID] = item
	}

	for _, publicationID := range publicationIDs {
		subagent, ok := publicationsByID[publicationID]
		if !ok {
			return fmt.Errorf("subagent publication %s not found or not visible to this tenant", publicationID)
		}
		hydrated, err := s.hydrateSubagentDefinition(subagent)
		if err != nil {
			return err
		}
		if hydrated.Status != "active" {
			return fmt.Errorf("subagent publication %s is not active", publicationID)
		}
		if strings.TrimSpace(hydrated.HostAgentDefinitionID) != "" && hydrated.HostAgentDefinitionID == agentID {
			return fmt.Errorf("subagent publication %s cannot delegate back to the same agent definition", publicationID)
		}
	}

	if err := s.subagentStore.ReplaceAgentSubagentAuthorizations(agentID, publicationIDs, stringPtr(userID)); err != nil {
		return err
	}
	return nil
}

func (s *AgentService) loadSkillFromDirectory(path string) (*database.Skill, error) {
	slug := filepath.Base(path)
	name := slug
	version := "1"
	description := ""

	if skillYAML, err := os.ReadFile(filepath.Join(path, "skill.yaml")); err == nil {
		for _, line := range strings.Split(string(skillYAML), "\n") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) != 2 {
				continue
			}
			key := strings.TrimSpace(parts[0])
			value := strings.Trim(strings.TrimSpace(parts[1]), `"'`)
			switch key {
			case "name":
				if value != "" {
					name = value
				}
			case "slug":
				if value != "" {
					slug = value
				}
			case "version":
				if value != "" {
					version = value
				}
			case "description":
				description = value
			}
		}
	}

	systemPrompt, _ := os.ReadFile(filepath.Join(path, "system_prompt.md"))
	outputSchema, err := os.ReadFile(filepath.Join(path, "output_schema.json"))
	if err != nil {
		outputSchema = []byte(`{}`)
	}
	toolAllowlist, err := os.ReadFile(filepath.Join(path, "tool_allowlist.json"))
	if err != nil {
		toolAllowlist = []byte(`[]`)
	}
	metadata, err := os.ReadFile(filepath.Join(path, "metadata.json"))
	if err != nil {
		metadata = []byte(`{}`)
	}

	skill := &database.Skill{
		Name:          name,
		Slug:          slug,
		Version:       version,
		Description:   description,
		RootPath:      path,
		SystemPrompt:  string(systemPrompt),
		OutputSchema:  outputSchema,
		ToolAllowlist: toolAllowlist,
		Metadata:      metadata,
	}
	return hydrateSkillContract(skill)
}

func (s *AgentService) ensureSystemSkillsSynced() error {
	if s.systemSkillsSynced {
		return nil
	}
	for _, slug := range systemSkillSlugs {
		path := filepath.Join(s.skillsRoot, slug)
		info, err := os.Stat(path)
		if err != nil {
			if errors.Is(err, os.ErrNotExist) {
				continue
			}
			return fmt.Errorf("failed to inspect system skill %s: %w", slug, err)
		}
		if !info.IsDir() {
			continue
		}
		skill, err := s.loadSkillFromDirectory(path)
		if err != nil {
			return err
		}
		if err := validateSkillGovernance(skill); err != nil {
			return err
		}
		if _, err := s.skillStore.UpsertSkill(skill); err != nil {
			return err
		}
	}
	s.systemSkillsSynced = true
	return nil
}

func (s *AgentService) validateAgentSkillSelection(tenantID string, skillIDs []string) error {
	if len(skillIDs) == 0 {
		return nil
	}
	items, err := s.skillStore.ListSkills(tenantID)
	if err != nil {
		return err
	}
	byID := make(map[string]*database.Skill, len(items))
	for _, item := range items {
		if item == nil || strings.TrimSpace(item.ID) == "" {
			continue
		}
		hydrated, err := hydrateSkillContract(item)
		if err != nil {
			return err
		}
		byID[item.ID] = hydrated
	}
	for _, skillID := range skillIDs {
		skillID = strings.TrimSpace(skillID)
		if skillID == "" {
			continue
		}
		skill, ok := byID[skillID]
		if !ok {
			return fmt.Errorf("skill %s not found", skillID)
		}
		if err := validateSkillGovernance(skill); err != nil {
			return err
		}
	}
	return nil
}

func (s *AgentService) fixedSkillIDs(tenantID string) ([]string, error) {
	items, err := s.skillStore.ListSkills(tenantID)
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(items))
	for _, item := range items {
		if item == nil || item.ID == "" || !isFixedSkill(item) {
			continue
		}
		ids = append(ids, item.ID)
	}
	return ids, nil
}

func stringPtr(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}

func timePtr(value time.Time) *time.Time {
	return &value
}

func subagentPublicationTenant(definition *database.SubagentDefinition) *string {
	if definition == nil {
		return nil
	}
	if strings.TrimSpace(definition.PublicationScope) == "system_global" {
		return nil
	}
	if tenantID := strings.TrimSpace(definition.PublicationTenantID); tenantID != "" {
		return stringPtr(tenantID)
	}
	if tenantID := strings.TrimSpace(definition.TenantID); tenantID != "" {
		return stringPtr(tenantID)
	}
	return nil
}

func appendSubagentGovernanceWarning(
	warnings []*database.SubagentGovernanceWarning,
	code, severity, message string,
) []*database.SubagentGovernanceWarning {
	return append(warnings, &database.SubagentGovernanceWarning{
		Code:     code,
		Severity: severity,
		Message:  message,
	})
}

func uniqueNonEmptyStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, exists := seen[trimmed]; exists {
			continue
		}
		seen[trimmed] = struct{}{}
		result = append(result, trimmed)
	}
	return result
}

func buildSubagentCompatibilityAgentsFromAuthorizations(authorizations []*database.SubagentAuthorizedAgent) []*database.SubagentPublicationImpactAgent {
	items := make([]*database.SubagentPublicationImpactAgent, 0, len(authorizations))
	for _, authorization := range authorizations {
		if authorization == nil {
			continue
		}
		items = append(items, &database.SubagentPublicationImpactAgent{
			AuthorizationID:     authorization.AuthorizationID,
			AgentDefinitionID:   authorization.AgentDefinitionID,
			AgentName:           authorization.AgentName,
			AgentStatus:         authorization.AgentStatus,
			AuthorizationStatus: authorization.Status,
		})
	}
	return items
}

func countActiveCompatibilityAgents(agents []*database.SubagentPublicationImpactAgent) int {
	activeCount := 0
	for _, agent := range agents {
		if agent == nil {
			continue
		}
		if strings.EqualFold(strings.TrimSpace(agent.AgentStatus), "active") {
			activeCount++
		}
	}
	return activeCount
}

func limitCompatibilityAgents(agents []*database.SubagentPublicationImpactAgent, limit int) []*database.SubagentPublicationImpactAgent {
	if len(agents) <= limit {
		return agents
	}
	return agents[:limit]
}

func metadataContainsLegacyHostAlias(raw json.RawMessage) bool {
	payload := normalizeJSONObject(raw)
	if len(payload) == 0 {
		return false
	}
	return strings.TrimSpace(stringValueFromMap(payload, "target_agent_definition_id")) != "" ||
		strings.TrimSpace(stringValueFromMap(payload, "agent_definition_id")) != ""
}

func buildSubagentMetadataAliasFreezeCandidates(controlPlanes []*database.SubagentControlPlane, definitionIDs []string) []*database.SubagentMetadataAliasFreezeCandidate {
	selectedIDs := map[string]struct{}{}
	for _, definitionID := range definitionIDs {
		trimmed := strings.TrimSpace(definitionID)
		if trimmed == "" {
			continue
		}
		selectedIDs[trimmed] = struct{}{}
	}

	candidates := make([]*database.SubagentMetadataAliasFreezeCandidate, 0)
	for _, controlPlane := range controlPlanes {
		if controlPlane == nil || controlPlane.Definition == nil {
			continue
		}
		definitionID := strings.TrimSpace(controlPlane.Definition.ID)
		if len(selectedIDs) > 0 {
			if _, ok := selectedIDs[definitionID]; !ok {
				continue
			}
		}
		if !metadataContainsLegacyHostAlias(controlPlane.Definition.Metadata) {
			continue
		}
		hostAgentDefinitionID, _, _ := extractSubagentRuntimeMetadata(controlPlane.Definition.Metadata)
		legacyAliasKey := ""
		legacyAliasValue := ""
		metadataPayload := normalizeJSONObject(controlPlane.Definition.Metadata)
		if value := strings.TrimSpace(stringValueFromMap(metadataPayload, "target_agent_definition_id")); value != "" {
			legacyAliasKey = "target_agent_definition_id"
			legacyAliasValue = value
		} else if value := strings.TrimSpace(stringValueFromMap(metadataPayload, "agent_definition_id")); value != "" {
			legacyAliasKey = "agent_definition_id"
			legacyAliasValue = value
		}

		candidate := &database.SubagentMetadataAliasFreezeCandidate{
			DefinitionID:               definitionID,
			DefinitionName:             strings.TrimSpace(controlPlane.Definition.Name),
			DefinitionStatus:           strings.TrimSpace(controlPlane.Definition.DefinitionStatus),
			HostAgentDefinitionID:      strings.TrimSpace(hostAgentDefinitionID),
			LegacyAliasKey:             legacyAliasKey,
			LegacyAliasValue:           legacyAliasValue,
			AuthorizationCount:         len(controlPlane.Authorizations),
			EnabledAuthorizationCount:  0,
			InactiveAuthorizationCount: 0,
		}
		for _, authorization := range controlPlane.Authorizations {
			if authorization == nil {
				continue
			}
			if strings.EqualFold(strings.TrimSpace(authorization.Status), "enabled") {
				candidate.EnabledAuthorizationCount++
			}
			if !strings.EqualFold(strings.TrimSpace(authorization.AgentStatus), "active") {
				candidate.InactiveAuthorizationCount++
			}
		}
		candidates = append(candidates, candidate)
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].EnabledAuthorizationCount != candidates[j].EnabledAuthorizationCount {
			return candidates[i].EnabledAuthorizationCount > candidates[j].EnabledAuthorizationCount
		}
		return candidates[i].DefinitionName < candidates[j].DefinitionName
	})
	return candidates
}

func buildSubagentMetadataAliasFreezePreview(controlPlanes []*database.SubagentControlPlane, req *SubagentMetadataAliasFreezeRequest) *database.SubagentMetadataAliasFreezePreview {
	scope := "tenant"
	if req != nil && strings.TrimSpace(req.Scope) != "" {
		scope = strings.TrimSpace(req.Scope)
	}
	if scope != "selection" {
		scope = "tenant"
	}

	definitionIDs := []string{}
	if req != nil {
		definitionIDs = req.DefinitionIDs
	}
	preview := &database.SubagentMetadataAliasFreezePreview{
		Executable:           false,
		RequiresConfirmation: false,
		Summary:              "当前没有需要冻结的 metadata alias。",
		Scope:                scope,
		DefinitionIDs:        []string{},
		RecommendedActions:   []string{},
		AffectedCapabilities: []*database.SubagentMetadataAliasFreezeCandidate{},
	}
	if scope == "selection" && len(normalizeServerIDs(definitionIDs)) == 0 {
		preview.BlockedReason = "当前还没有选中 capability，无法执行定向 metadata alias 冻结。"
		preview.Summary = "当前选中范围为空，尚未生成 metadata alias 冻结预演。"
		preview.RecommendedActions = append(preview.RecommendedActions, "先在左侧列表选择一个 capability，或切换到整个 tenant 范围后再执行冻结。")
		return preview
	}
	candidates := buildSubagentMetadataAliasFreezeCandidates(controlPlanes, definitionIDs)
	if len(candidates) == 0 {
		preview.RecommendedActions = append(preview.RecommendedActions, "当前 tenant 已没有残留 metadata alias，可以继续收口 host override 并准备删除旧 bridge。")
		return preview
	}

	preview.Executable = true
	preview.ImpactedCapabilityCount = len(candidates)
	preview.RequiresConfirmation = true
	preview.AffectedCapabilities = candidates
	for _, candidate := range candidates {
		preview.DefinitionIDs = append(preview.DefinitionIDs, candidate.DefinitionID)
		preview.AuthorizationCount += candidate.AuthorizationCount
		preview.EnabledAuthorizationCount += candidate.EnabledAuthorizationCount
		preview.InactiveAuthorizationCount += candidate.InactiveAuthorizationCount
	}

	targetLabel := "当前 tenant 内"
	if scope == "selection" {
		targetLabel = "当前选中范围内"
	}
	preview.Summary = fmt.Sprintf("%s有 %d 个 capability 仍残留 legacy metadata alias，可批量冻结为 canonical host_agent_definition_id。", targetLabel, preview.ImpactedCapabilityCount)
	preview.ConfirmationMessage = fmt.Sprintf("该操作会直接改写 %d 个 capability definition 的 metadata，移除 target/agent alias，但不会创建新版本或改动 publication。", preview.ImpactedCapabilityCount)
	preview.RecommendedActions = append(preview.RecommendedActions, "执行后重新检查 compatibility detail，确认 metadata alias 压力已经从 tenant 治理视图归零。")
	if preview.EnabledAuthorizationCount > 0 {
		preview.RecommendedActions = append(preview.RecommendedActions, fmt.Sprintf("当前仍有 %d 个 enabled authorization 依赖这些 capability，执行后应继续观察治理历史与运行时回归。", preview.EnabledAuthorizationCount))
	}
	if preview.InactiveAuthorizationCount > 0 {
		preview.RecommendedActions = append(preview.RecommendedActions, "存在 inactive host agent 授权，冻结 alias 后仍建议继续清理无效授权。")
	}
	return preview
}

func buildSubagentGovernanceSummary(controlPlane *database.SubagentControlPlane) *database.SubagentGovernanceSummary {
	if controlPlane == nil {
		return nil
	}

	summary := &database.SubagentGovernanceSummary{
		Warnings:             []*database.SubagentGovernanceWarning{},
		CompatibilityDetails: []*database.SubagentCompatibilityDetail{},
	}
	if controlPlane.Definition != nil {
		summary.HostAgentDefinitionID = strings.TrimSpace(controlPlane.Definition.HostAgentDefinitionID)
	}
	if len(controlPlane.Versions) > 0 && controlPlane.Versions[0] != nil {
		summary.LatestVersionNumber = controlPlane.Versions[0].VersionNumber
		if len(controlPlane.Versions) > 1 {
			summary.RollbackCandidateCount = len(controlPlane.Versions) - 1
			summary.HasRollbackCandidate = true
		}
	}
	if controlPlane.Publication != nil {
		summary.PublishedVersionNumber = controlPlane.Publication.VersionNumber
		summary.AuthorizationCount = controlPlane.Publication.AuthorizationCount
	}
	if summary.PublishedVersionNumber == 0 || summary.PublishedVersionNumber == summary.LatestVersionNumber {
		summary.IsPublishedVersionLatest = true
	}

	for _, authorization := range controlPlane.Authorizations {
		if authorization == nil {
			continue
		}
		if strings.EqualFold(authorization.Status, "enabled") {
			summary.EnabledAuthorizationCount++
		}
		if !strings.EqualFold(authorization.AgentStatus, "active") {
			summary.InactiveAuthorizationCount++
		}
	}

	if controlPlane.Definition != nil && metadataContainsLegacyHostAlias(controlPlane.Definition.Metadata) {
		agents := buildSubagentCompatibilityAgentsFromAuthorizations(controlPlane.Authorizations)
		summary.CompatibilityMode = true
		summary.CompatibilityDetails = append(summary.CompatibilityDetails, &database.SubagentCompatibilityDetail{
			Kind:                  "metadata_alias",
			Summary:               "definition metadata 里仍残留 legacy host alias，后续删除旧 bridge 前需要先完成数据迁移。",
			HostAgentDefinitionID: summary.HostAgentDefinitionID,
			ReferenceKey:          "target_agent_definition_id/agent_definition_id",
			ImpactedAgentCount:    len(agents),
			ActiveAgentCount:      countActiveCompatibilityAgents(agents),
			Agents:                limitCompatibilityAgents(agents, 6),
		})
	}
	if summary.CompatibilityMode {
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"metadata-alias-present",
			"warning",
			"definition metadata 中仍残留 legacy alias，删除旧桥后需要尽快完成 canonical 化收口。",
		)
	}
	if controlPlane.Publication == nil {
		summary.IsPublishedVersionLatest = false
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"publication-missing",
			"warning",
			"当前 definition 还没有 publication，运行时无法被授权给主 agent 使用。",
		)
	}
	if controlPlane.Publication != nil && summary.LatestVersionNumber > 0 && controlPlane.Publication.VersionNumber != summary.LatestVersionNumber {
		summary.IsPublishedVersionLatest = false
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"publication-not-latest",
			"info",
			fmt.Sprintf("当前发布停留在 v%d，最新 definition 版本已经到 v%d。", controlPlane.Publication.VersionNumber, summary.LatestVersionNumber),
		)
	}
	if summary.EnabledAuthorizationCount == 0 && controlPlane.Publication != nil && strings.EqualFold(controlPlane.Publication.Status, "active") {
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"authorization-empty",
			"info",
			"当前 publication 已激活，但还没有任何 host agent 授权使用它。",
		)
	}
	if summary.InactiveAuthorizationCount > 0 {
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"inactive-authorizations",
			"warning",
			fmt.Sprintf("存在 %d 个已授权 host agent 不是 active 状态，建议清理无效授权。", summary.InactiveAuthorizationCount),
		)
	}
	if controlPlane.Publication != nil && strings.EqualFold(controlPlane.Publication.Status, "archived") && summary.AuthorizationCount > 0 {
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"archived-publication-with-authorizations",
			"warning",
			"当前 publication 已归档，但仍保留授权记录；请确认是否已经完成影响面收口。",
		)
	}
	if controlPlane.Definition != nil && strings.TrimSpace(controlPlane.Definition.ID) != "" {
		metadataAliasPreview := buildSubagentMetadataAliasFreezePreview([]*database.SubagentControlPlane{controlPlane}, &SubagentMetadataAliasFreezeRequest{
			Scope:         "selection",
			DefinitionIDs: []string{controlPlane.Definition.ID},
		})
		summary.MetadataAliasFreezePreview = metadataAliasPreview
		summary.CanFreezeMetadataAliases = metadataAliasPreview != nil && metadataAliasPreview.Executable
	}
	summary.BridgeRemovalReadiness = buildSubagentBridgeRemovalReadiness(controlPlane, summary)
	return summary
}

func buildSubagentBridgeRemovalReadiness(
	controlPlane *database.SubagentControlPlane,
	summary *database.SubagentGovernanceSummary,
) *database.SubagentBridgeRemovalReadiness {
	if controlPlane == nil {
		return nil
	}
	if summary == nil {
		summary = &database.SubagentGovernanceSummary{}
	}

	checklist := make([]*database.SubagentBridgeRemovalChecklistItem, 0, 4)
	blockingIssueCount := 0
	pendingIssueCount := 0
	recommendedActions := make([]string, 0, 6)

	appendItem := func(item *database.SubagentBridgeRemovalChecklistItem) {
		if item == nil {
			return
		}
		checklist = append(checklist, item)
		if item.Blocking || item.Status == "blocked" {
			blockingIssueCount++
			recommendedActions = append(recommendedActions, item.RecommendedActions...)
			return
		}
		if item.Status != "ready" {
			pendingIssueCount++
			recommendedActions = append(recommendedActions, item.RecommendedActions...)
		}
	}

	metadataAliasPending := false
	for _, detail := range summary.CompatibilityDetails {
		if detail == nil {
			continue
		}
		if detail.Kind == "metadata_alias" {
			metadataAliasPending = true
			break
		}
	}
	metadataAliasItem := &database.SubagentBridgeRemovalChecklistItem{
		Key:      "metadata_aliases",
		Label:    "Metadata alias 冻结",
		Status:   "ready",
		Blocking: false,
		Summary:  "definition metadata 已不再残留 target/agent alias。",
	}
	if metadataAliasPending {
		metadataAliasItem.Status = "blocked"
		metadataAliasItem.Blocking = true
		metadataAliasItem.Summary = "definition metadata 中仍残留 legacy target/agent alias。"
		metadataAliasItem.RecommendedActions = append(metadataAliasItem.RecommendedActions, "先执行 metadata alias freeze，把历史 metadata 收口到 canonical host_agent_definition_id。")
	}
	appendItem(metadataAliasItem)

	publicationItem := &database.SubagentBridgeRemovalChecklistItem{
		Key:      "publication_ready",
		Label:    "Publication 承接能力",
		Status:   "ready",
		Blocking: false,
		Summary:  "当前已有 active publication 承接授权语义。",
	}
	switch {
	case controlPlane.Publication == nil:
		publicationItem.Status = "blocked"
		publicationItem.Blocking = true
		publicationItem.Summary = "当前还没有 publication，删除 bridge 后将没有正式承接面。"
		publicationItem.RecommendedActions = append(publicationItem.RecommendedActions, "先创建并激活 publication，再继续 bridge 收口。")
	case !strings.EqualFold(controlPlane.Publication.Status, "active"):
		publicationItem.Status = "blocked"
		publicationItem.Blocking = true
		publicationItem.Summary = fmt.Sprintf("当前 publication 状态为 %s，尚不适合作为 bridge 删除后的正式承接面。", firstNonEmpty(controlPlane.Publication.Status, "unknown"))
		publicationItem.RecommendedActions = append(publicationItem.RecommendedActions, "先把 publication 调整到 active，确认授权已经指向正式版本。")
	case !summary.IsPublishedVersionLatest:
		publicationItem.Status = "pending"
		publicationItem.Summary = fmt.Sprintf("当前发布停留在 v%d，最新版本为 v%d。", summary.PublishedVersionNumber, summary.LatestVersionNumber)
		publicationItem.RecommendedActions = append(publicationItem.RecommendedActions, "bridge 删除前建议先把 publication 追平到最新稳定版本，避免同时处理兼容迁移和版本偏差。")
	}
	appendItem(publicationItem)

	authorizationItem := &database.SubagentBridgeRemovalChecklistItem{
		Key:      "authorization_cleanup",
		Label:    "Authorization 收敛",
		Status:   "ready",
		Blocking: false,
		Summary:  "当前 authorization 状态已收敛，没有明显的无效授权残量。",
	}
	if summary.AuthorizationCount == 0 {
		authorizationItem.Status = "pending"
		authorizationItem.Summary = "当前 publication 尚未被任何 host agent 正式授权使用。"
		authorizationItem.RecommendedActions = append(authorizationItem.RecommendedActions, "至少确认一个正式 host agent 已通过 authorization 运行该 capability，再考虑删除 bridge。")
	} else if summary.InactiveAuthorizationCount > 0 {
		authorizationItem.Status = "pending"
		authorizationItem.Summary = fmt.Sprintf("仍有 %d 个 authorization 对应 inactive host agent。", summary.InactiveAuthorizationCount)
		authorizationItem.RecommendedActions = append(authorizationItem.RecommendedActions, "清理 inactive authorization，避免 bridge 删除后仍残留历史噪声。")
	}
	appendItem(authorizationItem)

	runtimeItem := &database.SubagentBridgeRemovalChecklistItem{
		Key:      "runtime_bridge_consumption",
		Label:    "Runtime 主链路",
		Status:   "ready",
		Blocking: false,
		Summary:  "runtime 主链路已停止消费旧 bridge，当前只走 publication/version/authorization。",
	}
	appendItem(runtimeItem)

	recommendedActions = uniqueNonEmptyStrings(recommendedActions)
	status := "ready"
	ready := true
	summaryText := "当前 capability 已满足删除旧 bridge 后的主要收口条件。"
	switch {
	case blockingIssueCount > 0:
		status = "blocked"
		ready = false
		summaryText = fmt.Sprintf("当前 capability 仍有 %d 项删桥后收口阻塞项。", blockingIssueCount)
	case pendingIssueCount > 0:
		status = "pending"
		ready = false
		summaryText = fmt.Sprintf("当前 capability 已清掉硬阻塞，但仍有 %d 项收尾动作。", pendingIssueCount)
	}

	if len(recommendedActions) == 0 {
		if ready {
			recommendedActions = append(recommendedActions, "可以进入删桥后的最终回归验证与文档对齐。")
		} else {
			recommendedActions = append(recommendedActions, "继续清理删桥后的残余 metadata alias、发布偏差和无效授权。")
		}
	}

	return &database.SubagentBridgeRemovalReadiness{
		Status:             status,
		Ready:              ready,
		BlockingIssueCount: blockingIssueCount,
		PendingIssueCount:  pendingIssueCount,
		Summary:            summaryText,
		RecommendedActions: recommendedActions,
		Checklist:          checklist,
	}
}

func buildSubagentTenantGovernanceSummary(
	controlPlanes []*database.SubagentControlPlane,
	events []*database.SubagentPublicationEvent,
	filters *database.SubagentPublicationEventFilters,
) *SubagentTenantGovernanceSummary {
	summary := &SubagentTenantGovernanceSummary{
		ActionTypeCounts: map[string]int{},
		EventStageCounts: map[string]int{},
		ChangeTypeCounts: map[string]int{},
		RiskLevelCounts:  map[string]int{},
		Filters:          filters,
	}
	for _, controlPlane := range controlPlanes {
		if controlPlane == nil {
			continue
		}
		governance := controlPlane.Governance
		if governance == nil {
			governance = buildSubagentGovernanceSummary(controlPlane)
		}
		summary.TotalCapabilities++
		if governance == nil {
			continue
		}
		if governance.CompatibilityMode {
			summary.CompatibilityCapabilities++
		}
		if strings.TrimSpace(governance.HostAgentDefinitionID) != "" {
			summary.HostOverrideCapabilities++
		}
		for _, detail := range governance.CompatibilityDetails {
			if detail == nil {
				continue
			}
			if detail.Kind == "metadata_alias" {
				summary.MetadataAliasCapabilities++
				break
			}
		}
		if controlPlane.Publication == nil {
			summary.PublicationMissingCount++
		}
		if !governance.IsPublishedVersionLatest {
			summary.PublicationNotLatestCount++
		}
		summary.AuthorizationCount += governance.AuthorizationCount
		summary.EnabledAuthorizationCount += governance.EnabledAuthorizationCount
		summary.InactiveAuthorizationCount += governance.InactiveAuthorizationCount
		if readiness := governance.BridgeRemovalReadiness; readiness != nil {
			if readiness.Ready {
				summary.BridgeRemovalReadyCapabilities++
			}
			summary.BridgeRemovalBlockedCount += readiness.BlockingIssueCount
			summary.BridgeRemovalPendingCount += readiness.PendingIssueCount
		}
	}

	for _, event := range events {
		if event == nil {
			continue
		}
		summary.RecentEventCount++
		actionType := firstNonEmpty(strings.TrimSpace(event.ActionType), "unknown")
		eventStage := firstNonEmpty(strings.TrimSpace(event.EventStage), "unknown")
		changeType := firstNonEmpty(strings.TrimSpace(event.ChangeType), "unknown")
		riskLevel := firstNonEmpty(strings.TrimSpace(event.RiskLevel), "unknown")
		summary.ActionTypeCounts[actionType]++
		summary.EventStageCounts[eventStage]++
		summary.ChangeTypeCounts[changeType]++
		summary.RiskLevelCounts[riskLevel]++
		if strings.EqualFold(riskLevel, "high") {
			summary.HighRiskEventCount++
		}
		if event.RequiresConfirmation {
			summary.ConfirmationRequiredEventCount++
		}
		if event.CompatibilityMode {
			summary.CompatibilityEventCount++
		}
	}
	return summary
}

func buildSubagentPublicationChangePreview(
	controlPlane *database.SubagentControlPlane,
	targetVersion *database.SubagentDefinitionVersion,
	targetScope string,
	targetStatus string,
) *database.SubagentPublicationChangePreview {
	if controlPlane == nil || targetVersion == nil {
		return nil
	}

	currentPublication := controlPlane.Publication
	preview := &database.SubagentPublicationChangePreview{
		ChangeType:           "initial_publish",
		RiskLevel:            "low",
		RequiresConfirmation: false,
		Current:              nil,
		Target: &database.SubagentPublicationChangeEndpoint{
			VersionID:           targetVersion.ID,
			VersionNumber:       targetVersion.VersionNumber,
			Status:              defaultString(strings.TrimSpace(targetStatus), "active"),
			PublicationScope:    defaultString(strings.TrimSpace(targetScope), "tenant"),
			PublicationTenantID: strings.TrimSpace(controlPlane.Definition.PublicationTenantID),
		},
		RecommendedActions: []string{},
		AffectedAgents:     []*database.SubagentPublicationImpactAgent{},
		CompatibilityMode:  controlPlane.Governance != nil && controlPlane.Governance.CompatibilityMode,
	}

	if currentPublication != nil {
		preview.Current = &database.SubagentPublicationChangeEndpoint{
			VersionID:           currentPublication.VersionID,
			VersionNumber:       currentPublication.VersionNumber,
			Status:              currentPublication.Status,
			PublicationScope:    currentPublication.PublicationScope,
			PublicationTenantID: currentPublication.TenantID,
		}
	}
	if !preview.CompatibilityMode && controlPlane.Definition != nil {
		preview.CompatibilityMode = strings.TrimSpace(controlPlane.Definition.HostAgentDefinitionID) != ""
	}

	switch {
	case currentPublication == nil:
		preview.ChangeType = "initial_publish"
	case currentPublication.VersionID != targetVersion.ID:
		if targetVersion.VersionNumber > currentPublication.VersionNumber {
			preview.ChangeType = "rollout"
		} else {
			preview.ChangeType = "rollback"
		}
	case !strings.EqualFold(currentPublication.Status, preview.Target.Status):
		preview.ChangeType = "status_change"
	case !strings.EqualFold(currentPublication.PublicationScope, preview.Target.PublicationScope):
		preview.ChangeType = "scope_change"
	default:
		preview.ChangeType = "metadata_update"
	}

	for _, authorization := range controlPlane.Authorizations {
		if authorization == nil {
			continue
		}
		preview.ImpactedAuthorizationCount++
		if strings.EqualFold(authorization.Status, "enabled") {
			preview.EnabledAuthorizationCount++
		} else {
			preview.InactiveAuthorizationCount++
		}
		if len(preview.AffectedAgents) < 6 {
			preview.AffectedAgents = append(preview.AffectedAgents, &database.SubagentPublicationImpactAgent{
				AuthorizationID:     authorization.AuthorizationID,
				AgentDefinitionID:   authorization.AgentDefinitionID,
				AgentName:           authorization.AgentName,
				AgentStatus:         authorization.AgentStatus,
				AuthorizationStatus: authorization.Status,
			})
		}
	}

	riskLevel := "low"
	requiresConfirmation := false
	recommendedActions := []string{}
	confirmationMessage := ""
	summary := "本次 publication 变更不会影响现有授权 agent。"

	if preview.EnabledAuthorizationCount > 0 {
		recommendedActions = append(recommendedActions, "先在控制台创建测试运行，确认目标版本行为和宿主 agent 兼容。")
	}
	if preview.CompatibilityMode {
		recommendedActions = append(recommendedActions, "当前 capability 仍存在 compatibility bridge，发布完成后应继续推进 legacy binding/metadata alias 到 authorization 的迁移。")
	}

	switch preview.ChangeType {
	case "initial_publish":
		summary = fmt.Sprintf("即将首次发布 v%d，当前还没有正式 publication。", targetVersion.VersionNumber)
		if preview.EnabledAuthorizationCount > 0 {
			riskLevel = "medium"
			requiresConfirmation = true
			summary = fmt.Sprintf("即将首次发布 v%d，并立即作用于 %d 个已启用授权。", targetVersion.VersionNumber, preview.EnabledAuthorizationCount)
		}
	case "rollout":
		summary = fmt.Sprintf("即将把 publication 从 v%d 切换到 v%d。", currentPublication.VersionNumber, targetVersion.VersionNumber)
		if preview.EnabledAuthorizationCount > 0 {
			riskLevel = "medium"
			requiresConfirmation = true
			summary = fmt.Sprintf("即将把 publication 从 v%d 切换到 v%d，影响 %d 个已启用授权。", currentPublication.VersionNumber, targetVersion.VersionNumber, preview.EnabledAuthorizationCount)
		}
	case "rollback":
		riskLevel = "high"
		requiresConfirmation = true
		summary = fmt.Sprintf("即将把 publication 从 v%d 回滚到 v%d。", currentPublication.VersionNumber, targetVersion.VersionNumber)
		if preview.EnabledAuthorizationCount > 0 {
			summary = fmt.Sprintf("即将把 publication 从 v%d 回滚到 v%d，影响 %d 个已启用授权。", currentPublication.VersionNumber, targetVersion.VersionNumber, preview.EnabledAuthorizationCount)
		}
		recommendedActions = append(recommendedActions, "回滚前确认变更原因、已知回归点和后续重新发布计划。")
	case "status_change":
		summary = fmt.Sprintf("即将把 publication 状态从 %s 调整为 %s。", firstNonEmpty(currentPublication.Status, "active"), preview.Target.Status)
		if strings.EqualFold(preview.Target.Status, "archived") || strings.EqualFold(preview.Target.Status, "disabled") {
			riskLevel = "high"
			requiresConfirmation = true
			recommendedActions = append(recommendedActions, "归档或停用会影响现有授权与历史绑定兜底，请先确认影响面已完成收口。")
			if preview.EnabledAuthorizationCount > 0 {
				summary = fmt.Sprintf("即将把 publication 状态从 %s 调整为 %s，影响 %d 个已启用授权。", firstNonEmpty(currentPublication.Status, "active"), preview.Target.Status, preview.EnabledAuthorizationCount)
			}
		}
	case "scope_change":
		riskLevel = "medium"
		requiresConfirmation = preview.EnabledAuthorizationCount > 0
		summary = fmt.Sprintf("即将把 publication scope 从 %s 调整为 %s。", firstNonEmpty(currentPublication.PublicationScope, "tenant"), preview.Target.PublicationScope)
		recommendedActions = append(recommendedActions, "调整 scope 前确认当前 tenant/全局可见性是否符合授权预期。")
	default:
		if preview.EnabledAuthorizationCount > 0 {
			summary = fmt.Sprintf("即将更新当前 publication 元数据，当前有 %d 个已启用授权会继续沿用该 publication。", preview.EnabledAuthorizationCount)
		} else {
			summary = "即将更新当前 publication 元数据，不涉及版本切换。"
		}
	}

	if preview.EnabledAuthorizationCount >= 3 && riskLevel == "medium" {
		riskLevel = "high"
	}
	if preview.CompatibilityMode && riskLevel == "low" {
		riskLevel = "medium"
	}
	if preview.ChangeType == "rollback" || strings.EqualFold(preview.Target.Status, "archived") {
		confirmationMessage = "该操作属于高风险发布治理动作，必须确认已评估授权影响面、回滚后果和兼容层状态。"
	} else if requiresConfirmation {
		confirmationMessage = "该操作会影响现有授权 agent，确认前请先核对版本差异、测试运行结果和发布范围。"
	}

	if len(recommendedActions) == 0 {
		recommendedActions = append(recommendedActions, "本次变更风险较低，但仍建议在发布后观察授权 agent 的运行结果与审计链路。")
	}

	preview.RiskLevel = riskLevel
	preview.RequiresConfirmation = requiresConfirmation
	preview.Summary = summary
	preview.ConfirmationMessage = confirmationMessage
	preview.RecommendedActions = recommendedActions
	return preview
}

func trimJSONStringField(raw string) string {
	return strings.TrimSpace(raw)
}

func normalizeSubagentPublicationGovernanceMetadata(raw json.RawMessage) json.RawMessage {
	return database.NormalizeJSONRawForExport(raw, `{}`)
}

func validateSubagentPublicationGovernanceInputs(
	preview *database.SubagentPublicationChangePreview,
	req *SubagentPublicationUpdateRequest,
) error {
	if preview == nil || req == nil {
		return nil
	}
	changeReason := trimJSONStringField(req.ChangeReason)
	rollbackRecoveryPlan := trimJSONStringField(req.RollbackRecoveryPlan)
	if preview.RequiresConfirmation && changeReason == "" {
		return errors.New("change_reason is required for publication changes that require confirmation")
	}
	if (preview.ChangeType == "rollback" || strings.EqualFold(preview.Target.Status, "archived")) && rollbackRecoveryPlan == "" {
		return errors.New("rollback_recovery_plan is required for rollback or archived publication changes")
	}
	return nil
}

func marshalJSONOrFallback(value any, fallback string) json.RawMessage {
	encoded, err := json.Marshal(value)
	if err != nil {
		return json.RawMessage(fallback)
	}
	return database.NormalizeJSONRawForExport(encoded, fallback)
}

func inferSubagentPublicationActionType(preview *database.SubagentPublicationChangePreview) string {
	if preview == nil {
		return "publication_change"
	}
	switch preview.ChangeType {
	case "initial_publish":
		return "publish"
	case "rollout":
		return "rollout"
	case "rollback":
		return "rollback"
	case "status_change":
		return "status_change"
	case "scope_change":
		return "scope_change"
	default:
		return "metadata_update"
	}
}

func buildSubagentPublicationEvent(
	tenantID string,
	userID string,
	definitionID string,
	publicationID string,
	eventStage string,
	preview *database.SubagentPublicationChangePreview,
	currentPublication *database.SubagentPublicationState,
	req *SubagentPublicationUpdateRequest,
) *database.SubagentPublicationEvent {
	if preview == nil {
		return nil
	}
	normalizedStage := strings.TrimSpace(eventStage)
	if normalizedStage == "" {
		normalizedStage = "executed"
	}
	event := &database.SubagentPublicationEvent{
		TenantID:                   tenantID,
		DefinitionID:               definitionID,
		PublicationID:              strings.TrimSpace(publicationID),
		EventStage:                 normalizedStage,
		ActionType:                 inferSubagentPublicationActionType(preview),
		ChangeType:                 preview.ChangeType,
		RiskLevel:                  preview.RiskLevel,
		RequiresConfirmation:       preview.RequiresConfirmation,
		Confirmed:                  req != nil && req.Confirmed,
		ImpactedAuthorizationCount: preview.ImpactedAuthorizationCount,
		EnabledAuthorizationCount:  preview.EnabledAuthorizationCount,
		InactiveAuthorizationCount: preview.InactiveAuthorizationCount,
		CompatibilityMode:          preview.CompatibilityMode,
		Summary:                    strings.TrimSpace(preview.Summary),
		RecommendedActions:         marshalJSONOrFallback(preview.RecommendedActions, `[]`),
		AffectedAgents:             marshalJSONOrFallback(preview.AffectedAgents, `[]`),
		Metadata:                   normalizeSubagentPublicationGovernanceMetadata(nil),
		ActorUserID:                stringPtr(strings.TrimSpace(userID)),
	}
	if preview.Target != nil {
		event.VersionID = strings.TrimSpace(preview.Target.VersionID)
		event.VersionNumber = preview.Target.VersionNumber
		event.PublicationScope = strings.TrimSpace(preview.Target.PublicationScope)
		event.Status = strings.TrimSpace(preview.Target.Status)
	}
	if preview.Current != nil {
		event.PreviousVersionID = strings.TrimSpace(preview.Current.VersionID)
		event.PreviousVersionNumber = preview.Current.VersionNumber
		event.PreviousPublicationScope = strings.TrimSpace(preview.Current.PublicationScope)
		event.PreviousStatus = strings.TrimSpace(preview.Current.Status)
	}
	if currentPublication != nil {
		if event.PreviousVersionID == "" {
			event.PreviousVersionID = strings.TrimSpace(currentPublication.VersionID)
			event.PreviousVersionNumber = currentPublication.VersionNumber
		}
		if event.PreviousPublicationScope == "" {
			event.PreviousPublicationScope = strings.TrimSpace(currentPublication.PublicationScope)
		}
		if event.PreviousStatus == "" {
			event.PreviousStatus = strings.TrimSpace(currentPublication.Status)
		}
		if event.PublicationID == "" {
			event.PublicationID = strings.TrimSpace(currentPublication.ID)
		}
	}
	if req != nil {
		event.ChangeReason = trimJSONStringField(req.ChangeReason)
		event.ChangeNotes = trimJSONStringField(req.ChangeNotes)
		event.RollbackRecoveryPlan = trimJSONStringField(req.RollbackRecoveryPlan)
		event.Metadata = normalizeSubagentPublicationGovernanceMetadata(req.GovernanceMetadata)
	}
	if event.PublicationScope == "" {
		event.PublicationScope = "tenant"
	}
	if event.PreviousPublicationScope == "" {
		event.PreviousPublicationScope = event.PublicationScope
	}
	if event.Status == "" {
		event.Status = "active"
	}
	if event.PreviousStatus == "" {
		event.PreviousStatus = event.Status
	}
	return event
}

func buildSubagentMetadataAliasFreezeEvent(
	tenantID string,
	userID string,
	preview *database.SubagentMetadataAliasFreezePreview,
	candidate *database.SubagentMetadataAliasFreezeCandidate,
	frozenCount int,
	eventStage string,
) *database.SubagentPublicationEvent {
	if preview == nil || candidate == nil {
		return nil
	}
	normalizedStage := strings.TrimSpace(eventStage)
	if normalizedStage == "" {
		normalizedStage = "executed"
	}
	riskLevel := "low"
	if preview.EnabledAuthorizationCount > 0 {
		riskLevel = "medium"
	}
	if preview.EnabledAuthorizationCount >= 3 || preview.ImpactedCapabilityCount >= 3 {
		riskLevel = "high"
	}
	summary := strings.TrimSpace(preview.Summary)
	if normalizedStage == "executed" {
		summary = fmt.Sprintf("已冻结 %d 个 capability 的 metadata alias，legacy target/agent fallback 已收口到 canonical host_agent_definition_id。", frozenCount)
	}
	metadata := map[string]any{
		"scope":                   preview.Scope,
		"definition_ids":          preview.DefinitionIDs,
		"frozen_capability_count": frozenCount,
		"affected_capabilities":   preview.AffectedCapabilities,
		"legacy_alias_key":        candidate.LegacyAliasKey,
		"legacy_alias_value":      candidate.LegacyAliasValue,
	}
	if preview.BlockedReason != "" {
		metadata["blocked_reason"] = preview.BlockedReason
	}
	return &database.SubagentPublicationEvent{
		TenantID:                   tenantID,
		DefinitionID:               candidate.DefinitionID,
		EventStage:                 normalizedStage,
		ActionType:                 "metadata_alias_freeze",
		ChangeType:                 "metadata_alias_freeze",
		RiskLevel:                  riskLevel,
		RequiresConfirmation:       preview.RequiresConfirmation,
		Confirmed:                  normalizedStage == "executed",
		ImpactedAuthorizationCount: preview.AuthorizationCount,
		EnabledAuthorizationCount:  preview.EnabledAuthorizationCount,
		InactiveAuthorizationCount: preview.InactiveAuthorizationCount,
		CompatibilityMode:          true,
		Summary:                    summary,
		ChangeReason:               "metadata alias freeze",
		RecommendedActions:         marshalJSONOrFallback(preview.RecommendedActions, `[]`),
		AffectedAgents:             marshalJSONOrFallback([]*database.SubagentPublicationImpactAgent{}, `[]`),
		Metadata:                   marshalJSONOrFallback(metadata, `{}`),
		ActorUserID:                stringPtr(strings.TrimSpace(userID)),
	}
}

func prependSubagentPublicationEvent(controlPlane *database.SubagentControlPlane, event *database.SubagentPublicationEvent) *database.SubagentControlPlane {
	if controlPlane == nil || event == nil {
		return controlPlane
	}
	items := make([]*database.SubagentPublicationEvent, 0, len(controlPlane.Events)+1)
	items = append(items, event)
	for _, existing := range controlPlane.Events {
		if existing == nil || existing.ID == event.ID {
			continue
		}
		items = append(items, existing)
		if len(items) >= 12 {
			break
		}
	}
	controlPlane.Events = items
	return controlPlane
}

func (s *AgentService) recordSubagentPublicationEvent(
	tenantID string,
	userID string,
	controlPlane *database.SubagentControlPlane,
	currentPublication *database.SubagentPublicationState,
	req *SubagentPublicationUpdateRequest,
	preview *database.SubagentPublicationChangePreview,
	eventStage string,
) (*database.SubagentPublicationEvent, error) {
	if s.subagentStore == nil || controlPlane == nil || controlPlane.Definition == nil {
		return nil, nil
	}
	event := buildSubagentPublicationEvent(
		tenantID,
		userID,
		controlPlane.Definition.ID,
		func() string {
			if controlPlane.Publication != nil {
				return controlPlane.Publication.ID
			}
			if currentPublication != nil {
				return currentPublication.ID
			}
			return ""
		}(),
		eventStage,
		preview,
		currentPublication,
		req,
	)
	if event == nil {
		return nil, nil
	}
	return s.subagentStore.AppendSubagentPublicationEvent(event)
}

func (s *AgentService) recordSubagentMetadataAliasFreezeEvent(
	tenantID string,
	userID string,
	preview *database.SubagentMetadataAliasFreezePreview,
	frozenCount int,
	eventStage string,
) ([]*database.SubagentPublicationEvent, error) {
	if s.subagentStore == nil {
		return nil, nil
	}
	events := make([]*database.SubagentPublicationEvent, 0, len(preview.AffectedCapabilities))
	for _, candidate := range preview.AffectedCapabilities {
		event := buildSubagentMetadataAliasFreezeEvent(tenantID, userID, preview, candidate, frozenCount, eventStage)
		if event == nil {
			continue
		}
		recorded, err := s.subagentStore.AppendSubagentPublicationEvent(event)
		if err != nil {
			return nil, err
		}
		events = append(events, recorded)
	}
	return events, nil
}

func (s *AgentService) loadTenantGovernanceEventsWithRecordedFreezeEvent(
	tenantID string,
	userID string,
	controlPlanes []*database.SubagentControlPlane,
	preview *database.SubagentMetadataAliasFreezePreview,
) ([]*database.SubagentPublicationEvent, int, *database.SubagentPublicationEventFilters, error) {
	filters := &database.SubagentPublicationEventFilters{Limit: 20, Offset: 0}
	recordedEvents, eventErr := s.recordSubagentMetadataAliasFreezeEvent(tenantID, userID, preview, len(preview.DefinitionIDs), "executed")
	page, err := s.subagentStore.ListTenantSubagentPublicationEvents(tenantID, filters)
	if err != nil {
		return nil, 0, nil, err
	}
	events := page.Items
	if eventErr == nil && len(recordedEvents) > 0 {
		for index := len(recordedEvents) - 1; index >= 0; index-- {
			recordedEvent := recordedEvents[index]
			found := false
			for _, item := range events {
				if item != nil && item.ID == recordedEvent.ID {
					found = true
					break
				}
			}
			if !found {
				events = append([]*database.SubagentPublicationEvent{recordedEvent}, events...)
			}
		}
	}
	return events, page.Total, page.Filters, nil
}

func enrichSubagentControlPlaneGovernance(controlPlane *database.SubagentControlPlane) *database.SubagentControlPlane {
	if controlPlane == nil {
		return nil
	}
	controlPlane.Governance = buildSubagentGovernanceSummary(controlPlane)
	if controlPlane.Governance == nil || controlPlane.Definition == nil || len(controlPlane.Versions) == 0 || controlPlane.Versions[0] == nil {
		return controlPlane
	}
	targetVersion := controlPlane.Versions[0]
	targetScope := controlPlane.Definition.PublicationScope
	targetStatus := controlPlane.Definition.Status
	if controlPlane.Publication != nil {
		targetScope = firstNonEmpty(controlPlane.Publication.PublicationScope, targetScope)
		targetStatus = firstNonEmpty(controlPlane.Publication.Status, targetStatus)
	}
	controlPlane.Governance.NextPublicationPreview = buildSubagentPublicationChangePreview(
		controlPlane,
		targetVersion,
		targetScope,
		targetStatus,
	)
	return controlPlane
}

func (s *AgentService) buildSubagentDefinitionForWrite(tenantID, userID, userRole, subagentID string, req *SubagentDefinitionUpsertRequest) (*database.SubagentDefinition, error) {
	if err := ensureSubagentAdminRole(userRole); err != nil {
		return nil, err
	}
	name := strings.TrimSpace(req.Name)
	if name == "" {
		return nil, errors.New("name is required")
	}

	metadata, err := mergeSubagentMetadata(
		database.NormalizeJSONRawForExport(req.Metadata, `{}`),
		strings.TrimSpace(req.Slug),
		strings.TrimSpace(req.HostAgentDefinitionID),
		strings.TrimSpace(req.HandoffPrompt),
	)
	if err != nil {
		return nil, err
	}
	hostAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(metadata)
	if err != nil {
		return nil, err
	}
	if hostAgentDefinitionID != "" {
		targetAgent, err := s.agentStore.GetAgentDefinition(hostAgentDefinitionID, tenantID)
		if err != nil {
			return nil, fmt.Errorf("host agent definition %s not found", hostAgentDefinitionID)
		}
		if targetAgent.Status != "active" {
			return nil, fmt.Errorf("host agent definition %s is not active", hostAgentDefinitionID)
		}
	}

	def := &database.SubagentDefinition{
		ID:                 subagentID,
		TenantID:           tenantID,
		Name:               name,
		Description:        strings.TrimSpace(req.Description),
		SystemPrompt:       req.SystemPrompt,
		Model:              strings.TrimSpace(req.Model),
		Status:             defaultString(strings.TrimSpace(req.Status), "active"),
		DefinitionStatus:   defaultString(strings.TrimSpace(req.DefinitionStatus), "active"),
		LifecycleStatus:    defaultString(strings.TrimSpace(req.LifecycleStatus), "active"),
		PublicationScope:   defaultString(strings.TrimSpace(req.PublicationScope), "tenant"),
		Config:             database.NormalizeJSONRawForExport(req.Config, `{}`),
		Metadata:           metadata,
		OutputSchema:       database.NormalizeJSONRawForExport(req.OutputSchema, `{}`),
		HandoffInputSchema: database.NormalizeJSONRawForExport(req.HandoffInputSchema, `{}`),
		ToolAllowlist:      database.NormalizeJSONRawForExport(req.ToolAllowlist, `[]`),
		SkillAllowlist:     database.NormalizeJSONRawForExport(req.SkillAllowlist, `[]`),
		MCPAllowlist:       database.NormalizeJSONRawForExport(req.MCPAllowlist, `[]`),
		KnowledgePolicy:    database.NormalizeJSONRawForExport(req.KnowledgePolicy, `{}`),
		ReviewPolicy:       database.NormalizeJSONRawForExport(req.ReviewPolicy, `{}`),
		RuntimePolicy:      database.NormalizeJSONRawForExport(req.RuntimePolicy, `{}`),
		PublicationMetadata: database.NormalizeJSONRawForExport(
			req.PublicationMetadata,
			`{}`,
		),
	}
	if strings.TrimSpace(subagentID) == "" {
		def.CreatedBy = stringPtr(userID)
	} else {
		def.UpdatedBy = stringPtr(userID)
	}
	def.PublicationTenantID = tenantID
	def.HostAgentDefinitionID = hostAgentDefinitionID
	def.HandoffPrompt = handoffPrompt
	return def, nil
}

func (s *AgentService) hydrateSubagentDefinition(definition *database.SubagentDefinition) (*database.SubagentDefinition, error) {
	if definition == nil {
		return nil, nil
	}
	hostAgentDefinitionID, handoffPrompt, err := extractSubagentRuntimeMetadata(definition.Metadata)
	if err != nil {
		return nil, err
	}
	definition.HostAgentDefinitionID = hostAgentDefinitionID
	definition.HandoffPrompt = handoffPrompt
	definition.Slug = extractSubagentSlug(definition.Metadata)
	if strings.TrimSpace(definition.PublicationScope) == "" {
		definition.PublicationScope = "tenant"
	}
	return definition, nil
}

func normalizeJSONObject(raw json.RawMessage) map[string]any {
	value, ok := parseJSONRaw(raw, `{}`).(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return value
}

func normalizeJSONStringList(raw json.RawMessage) []string {
	values, ok := parseJSONRaw(raw, `[]`).([]any)
	if !ok {
		return []string{}
	}
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		text := strings.TrimSpace(fmt.Sprintf("%v", value))
		if text == "" {
			continue
		}
		if _, exists := seen[text]; exists {
			continue
		}
		seen[text] = struct{}{}
		result = append(result, text)
	}
	return result
}

func (s *AgentService) buildManagedSubagentRunMetadata(
	definition *database.SubagentDefinition,
	version *database.SubagentDefinitionVersion,
	publication *database.SubagentPublicationState,
) map[string]any {
	definitionMetadata := normalizeJSONObject(definition.Metadata)
	versionMetadata := normalizeJSONObject(version.Metadata)
	publicationMetadata := map[string]any{}
	publicationID := ""
	if publication != nil {
		publicationMetadata = normalizeJSONObject(publication.Metadata)
		publicationID = publication.ID
	}

	mergedMetadata := make(map[string]any, len(definitionMetadata)+len(versionMetadata)+len(publicationMetadata)+4)
	for key, value := range definitionMetadata {
		mergedMetadata[key] = value
	}
	for key, value := range versionMetadata {
		mergedMetadata[key] = value
	}
	for key, value := range publicationMetadata {
		mergedMetadata[key] = value
	}
	mergedMetadata["version_number"] = version.VersionNumber
	if publication != nil {
		mergedMetadata["publication_status"] = publication.Status
		mergedMetadata["publication_scope"] = publication.PublicationScope
	}

	payload := map[string]any{
		"slug":                   definition.Slug,
		"name":                   definition.Name,
		"description":            definition.Description,
		"subagent_definition_id": definition.ID,
		"version_id":             version.ID,
		"system_prompt":          version.SystemPrompt,
		"model":                  version.Model,
		"config":                 normalizeJSONObject(version.Config),
		"output_schema":          normalizeJSONObject(version.OutputSchema),
		"handoff_input_schema":   normalizeJSONObject(version.HandoffInputSchema),
		"tool_allowlist":         normalizeJSONStringList(version.ToolAllowlist),
		"skill_allowlist":        normalizeJSONStringList(version.SkillAllowlist),
		"mcp_allowlist":          normalizeJSONStringList(version.MCPAllowlist),
		"knowledge_policy":       normalizeJSONObject(version.KnowledgePolicy),
		"review_policy":          normalizeJSONObject(version.ReviewPolicy),
		"runtime_policy":         normalizeJSONObject(version.RuntimePolicy),
		"metadata":               mergedMetadata,
	}
	if publicationID != "" {
		payload["publication_id"] = publicationID
	}
	if definition.HandoffPrompt != "" {
		payload["handoff_prompt"] = definition.HandoffPrompt
	}
	if definition.HostAgentDefinitionID != "" {
		payload["host_agent_definition_id"] = definition.HostAgentDefinitionID
	}
	return payload
}

func extractSubagentRuntimeMetadata(raw json.RawMessage) (string, string, error) {
	payload := map[string]any{}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			return "", "", fmt.Errorf("invalid subagent metadata: %w", err)
		}
	}
	hostAgentDefinitionID := strings.TrimSpace(stringValueFromMap(payload, "host_agent_definition_id"))
	if hostAgentDefinitionID == "" {
		hostAgentDefinitionID = strings.TrimSpace(stringValueFromMap(payload, "target_agent_definition_id"))
	}
	if hostAgentDefinitionID == "" {
		hostAgentDefinitionID = strings.TrimSpace(stringValueFromMap(payload, "agent_definition_id"))
	}
	handoffPrompt := strings.TrimSpace(stringValueFromMap(payload, "handoff_prompt"))
	return hostAgentDefinitionID, handoffPrompt, nil
}

func stringValueFromMap(payload map[string]any, key string) string {
	value, ok := payload[key]
	if !ok || value == nil {
		return ""
	}
	text, ok := value.(string)
	if !ok {
		return ""
	}
	return text
}

func mergeSubagentMetadata(raw json.RawMessage, slug, hostAgentDefinitionID, handoffPrompt string) (json.RawMessage, error) {
	payload := map[string]any{}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			return nil, fmt.Errorf("invalid subagent metadata: %w", err)
		}
	}
	canonicalHostAgentDefinitionID := strings.TrimSpace(hostAgentDefinitionID)
	if canonicalHostAgentDefinitionID == "" {
		canonicalHostAgentDefinitionID = strings.TrimSpace(stringValueFromMap(payload, "host_agent_definition_id"))
	}
	if canonicalHostAgentDefinitionID == "" {
		canonicalHostAgentDefinitionID = strings.TrimSpace(stringValueFromMap(payload, "target_agent_definition_id"))
	}
	if canonicalHostAgentDefinitionID == "" {
		canonicalHostAgentDefinitionID = strings.TrimSpace(stringValueFromMap(payload, "agent_definition_id"))
	}
	canonicalHandoffPrompt := strings.TrimSpace(handoffPrompt)
	if canonicalHandoffPrompt == "" {
		canonicalHandoffPrompt = strings.TrimSpace(stringValueFromMap(payload, "handoff_prompt"))
	}
	delete(payload, "target_agent_definition_id")
	delete(payload, "agent_definition_id")
	delete(payload, "host_agent_definition_id")
	delete(payload, "handoff_prompt")
	if slug != "" {
		payload["slug"] = slug
	}
	if canonicalHostAgentDefinitionID != "" {
		payload["host_agent_definition_id"] = canonicalHostAgentDefinitionID
	}
	if canonicalHandoffPrompt != "" {
		payload["handoff_prompt"] = canonicalHandoffPrompt
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to encode subagent metadata: %w", err)
	}
	return encoded, nil
}

func extractSubagentSlug(raw json.RawMessage) string {
	payload := map[string]any{}
	if len(raw) == 0 {
		return ""
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return ""
	}
	return strings.TrimSpace(stringValueFromMap(payload, "slug"))
}

func ensureSubagentAdminRole(role string) error {
	if strings.EqualFold(strings.TrimSpace(role), "admin") {
		return nil
	}
	return ErrAgentUnauthorized
}

func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func (s *AgentService) cancelActiveRuns(ctx context.Context, tenantID string, runRefs []*database.AgentRunReference) error {
	for _, runRef := range runRefs {
		if !runStatusNeedsCancellation(runRef) {
			continue
		}
		if _, err := s.aiClient.CancelAgentRun(ctx, runRef.ID, tenantID); err != nil {
			return fmt.Errorf("failed to cancel run %s before cleanup: %w", runRef.ID, err)
		}
	}
	return nil
}

func runStatusNeedsCancellation(runRef *database.AgentRunReference) bool {
	if runRef == nil {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(runRef.Status)) {
	case "queued", "running":
		return true
	default:
		return false
	}
}

func firstNonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func normalizeServerIDs(ids []string) []string {
	if len(ids) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(ids))
	result := make([]string, 0, len(ids))
	for _, id := range ids {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			continue
		}
		if _, exists := seen[trimmed]; exists {
			continue
		}
		seen[trimmed] = struct{}{}
		result = append(result, trimmed)
	}
	return result
}

func mergeFixedSkillIDs(skillIDs, fixedSkillIDs []string) []string {
	if len(skillIDs) == 0 && len(fixedSkillIDs) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(skillIDs)+len(fixedSkillIDs))
	result := make([]string, 0, len(skillIDs)+len(fixedSkillIDs))
	for _, skillID := range skillIDs {
		trimmed := strings.TrimSpace(skillID)
		if trimmed == "" {
			continue
		}
		if _, exists := seen[trimmed]; exists {
			continue
		}
		seen[trimmed] = struct{}{}
		result = append(result, trimmed)
	}
	for _, skillID := range fixedSkillIDs {
		trimmed := strings.TrimSpace(skillID)
		if trimmed == "" {
			continue
		}
		if _, exists := seen[trimmed]; exists {
			continue
		}
		seen[trimmed] = struct{}{}
		result = append(result, trimmed)
	}
	return result
}

func isFixedSkill(skill *database.Skill) bool {
	if skill == nil {
		return false
	}
	if strings.EqualFold(strings.TrimSpace(skill.Slug), fallbackFixedSkillSlug) {
		return true
	}
	metadata, ok := parseJSONRaw(skill.Metadata, `{}`).(map[string]any)
	if !ok {
		return false
	}
	switch value := metadata["fixed_binding"].(type) {
	case bool:
		return value
	case string:
		return strings.EqualFold(strings.TrimSpace(value), "true")
	default:
		return false
	}
}

func validateMCPServer(server *database.MCPServer) error {
	switch server.Transport {
	case "stdio":
		if strings.TrimSpace(server.Command) == "" {
			return errors.New("stdio transport requires command")
		}
	case "http", "sse":
		if strings.TrimSpace(server.Endpoint) == "" {
			return fmt.Errorf("%s transport requires endpoint", server.Transport)
		}
	default:
		return errors.New("unsupported transport")
	}
	if server.Status != "active" && server.Status != "disabled" {
		return errors.New("unsupported status")
	}
	return nil
}

func (s *AgentService) hydrateMCPServer(server *database.MCPServer) (*database.MCPServer, error) {
	if server == nil {
		return nil, nil
	}
	tools, err := s.mcpStore.ListServerTools(server.ID)
	if err != nil {
		return nil, err
	}
	for _, tool := range tools {
		tool.InputSchema = maskSensitiveJSONRaw(tool.InputSchema, false)
		tool.Metadata = maskSensitiveJSONRaw(tool.Metadata, false)
	}
	server.Tools = tools
	server.Args = maskSensitiveJSONRaw(server.Args, false)
	server.Env = maskSensitiveJSONRaw(server.Env, true)
	server.Metadata = maskSensitiveJSONRaw(server.Metadata, false)
	server.Connection = buildMCPConnectionSummary(server)
	server.Catalog = buildMCPCatalogSummary(server, tools, time.Now().UTC())
	server.Availability = buildMCPAvailabilitySummary(server, server.Connection, server.Catalog)
	bindingAgents, bindingCount, activeBindingCount, inactiveBindingCount, err := s.mcpStore.ListServerBindingAgents(server.ID, server.TenantID, 6)
	if err != nil {
		return nil, err
	}
	server.BindingUsage = buildMCPBindingUsageSummary(server, bindingAgents, bindingCount, activeBindingCount, inactiveBindingCount)
	server.Recovery = buildMCPRecoverySummary(server, server.Connection, server.Catalog, server.Availability, server.BindingUsage)
	server.SecurityScore = buildMCPSecurityScore(server, tools, time.Now().UTC())
	events, err := s.mcpStore.ListServerEvents(server.ID, server.TenantID, 12)
	if err != nil {
		return nil, err
	}
	server.Events = events
	return server, nil
}

func buildMCPConnectionSummary(server *database.MCPServer) *database.MCPConnection {
	if server == nil {
		return nil
	}

	summary := &database.MCPConnection{
		Status:   "untested",
		Summary:  "尚未执行连接测试。",
		TestedAt: server.LastTestedAt,
	}
	if server.LastError != nil && strings.TrimSpace(*server.LastError) != "" {
		summary.Error = strings.TrimSpace(*server.LastError)
	}

	switch {
	case server.Status != "active":
		summary.Status = "disabled"
		summary.Summary = "Server 已禁用，不会参与运行时调用。"
	case server.LastTestedAt == nil:
		summary.Status = "untested"
		summary.Summary = "尚未执行连接测试，当前健康状态未知。"
	case summary.Error != "":
		summary.Status = "degraded"
		summary.Summary = "最近一次连接测试失败，请先修复连接问题。"
	default:
		summary.Status = "healthy"
		summary.Summary = "最近一次连接测试通过。"
	}

	return summary
}

func buildMCPCatalogSummary(server *database.MCPServer, tools []*database.MCPServerTool, now time.Time) *database.MCPCatalog {
	if server == nil {
		return nil
	}

	summary := &database.MCPCatalog{
		Status:            "missing",
		Summary:           "尚未建立工具 catalog。",
		ToolCount:         len(tools),
		StaleAfterSeconds: int64(mcpCatalogStaleAfter.Seconds()),
		SampleTools:       make([]string, 0, minInt(len(tools), 5)),
	}

	var refreshedAt *time.Time
	for _, tool := range tools {
		if tool == nil {
			continue
		}
		if len(summary.SampleTools) < 5 && strings.TrimSpace(tool.ToolName) != "" {
			summary.SampleTools = append(summary.SampleTools, strings.TrimSpace(tool.ToolName))
		}
		if refreshedAt == nil || tool.DiscoveredAt.After(*refreshedAt) {
			refreshed := tool.DiscoveredAt.UTC()
			refreshedAt = &refreshed
		}
	}

	summary.RefreshedAt = refreshedAt

	if refreshedAt != nil {
		age := int64(now.UTC().Sub(*refreshedAt).Seconds())
		if age < 0 {
			age = 0
		}
		summary.AgeSeconds = &age
		summary.IsStale = now.UTC().Sub(*refreshedAt) > mcpCatalogStaleAfter
	}

	switch {
	case server.Status != "active":
		summary.Status = "disabled"
		summary.Summary = "Server 已禁用，catalog 不会参与 agent 工具发现。"
	case len(tools) == 0 && refreshedAt == nil && server.LastTestedAt == nil:
		summary.Status = "missing"
		summary.Summary = "还没有缓存工具，请先执行 Refresh Tools。"
	case len(tools) == 0:
		summary.Status = "empty"
		summary.Summary = "最近一次 catalog 刷新后没有发现可用工具。"
	case summary.IsStale:
		summary.Status = "stale"
		summary.Summary = "已存在缓存工具，但 catalog 已过期，建议重新刷新。"
	default:
		summary.Status = "ready"
		summary.Summary = fmt.Sprintf("当前已缓存 %d 个工具，可供 agent 直接发现。", len(tools))
	}

	return summary
}

func buildMCPAvailabilitySummary(
	server *database.MCPServer,
	connection *database.MCPConnection,
	catalog *database.MCPCatalog,
) *database.MCPAvailability {
	if server == nil {
		return nil
	}

	summary := &database.MCPAvailability{
		Status:   "unavailable",
		Summary:  "Server 当前还不能稳定提供给 agent 使用。",
		Bindable: false,
	}

	switch {
	case server.Status != "active":
		summary.Status = "disabled"
		summary.Summary = "Server 已禁用，不能绑定到 agent。"
		summary.Reason = "disabled"
	case catalog == nil || catalog.ToolCount == 0:
		summary.Status = "unavailable"
		summary.Summary = "还没有可供 agent 使用的缓存工具，请先刷新 catalog。"
		summary.Reason = "catalog_empty"
	case connection != nil && connection.Status == "degraded":
		summary.Status = "degraded"
		summary.Summary = "最近一次连接测试失败，建议修复后再交给 agent 使用。"
		summary.Reason = "connection_failed"
	case catalog != nil && catalog.IsStale:
		summary.Status = "warning"
		summary.Summary = "Server 可绑定，但 catalog 已过期，建议刷新后再投入生产。"
		summary.Bindable = true
		summary.Reason = "catalog_stale"
	case connection != nil && connection.Status == "untested":
		summary.Status = "warning"
		summary.Summary = "Server 已有缓存工具，但还未完成连接验证。"
		summary.Bindable = true
		summary.Reason = "connection_untested"
	default:
		summary.Status = "available"
		summary.Summary = "Server 已通过基础校验，可供 agent 使用。"
		summary.Bindable = true
		summary.Reason = "ready"
	}

	return summary
}

func buildMCPBindingUsageSummary(
	server *database.MCPServer,
	agents []*database.MCPBindingAgent,
	totalCount int,
	activeCount int,
	inactiveCount int,
) *database.MCPBindingUsage {
	summary := &database.MCPBindingUsage{
		AgentCount:         totalCount,
		ActiveAgentCount:   activeCount,
		InactiveAgentCount: inactiveCount,
		Summary:            "当前还没有 agent 绑定这个 server。",
		Agents:             make([]*database.MCPBindingAgent, 0, len(agents)),
	}

	for _, agent := range agents {
		if agent == nil {
			continue
		}
		status := strings.TrimSpace(agent.Status)
		if status == "" {
			status = "active"
		}
		summary.Agents = append(summary.Agents, &database.MCPBindingAgent{
			AgentID: strings.TrimSpace(agent.AgentID),
			Name:    strings.TrimSpace(agent.Name),
			Status:  status,
		})
	}

	if totalCount <= 0 {
		if server != nil && server.Status != "active" {
			summary.Summary = "Server 当前未被任何 agent 绑定。"
		}
		return summary
	}

	if moreCount := totalCount - len(summary.Agents); moreCount > 0 {
		summary.MoreCount = moreCount
	}

	if totalCount == 1 {
		summary.Summary = "当前有 1 个 agent 正在使用这个 server。"
		return summary
	}

	summary.Summary = fmt.Sprintf("当前有 %d 个 agent 正在使用这个 server。", totalCount)
	return summary
}

func buildMCPRecoverySummary(
	server *database.MCPServer,
	connection *database.MCPConnection,
	catalog *database.MCPCatalog,
	availability *database.MCPAvailability,
	bindingUsage *database.MCPBindingUsage,
) *database.MCPRecovery {
	if server == nil {
		return nil
	}

	recovery := &database.MCPRecovery{
		Status:      "healthy",
		Severity:    "info",
		Summary:     "当前不需要额外恢复操作。",
		FailureMode: "",
		Recoverable: false,
		Actions:     []*database.MCPRecoveryAction{},
		Impact:      buildMCPRecoveryImpact(bindingUsage),
	}

	addAction := func(actionType, label, description, priority string) {
		recovery.Actions = append(recovery.Actions, &database.MCPRecoveryAction{
			Type:        actionType,
			Label:       label,
			Description: description,
			Priority:    priority,
		})
	}

	switch {
	case server.Status != "active":
		recovery.Status = "disabled"
		recovery.Severity = "neutral"
		recovery.Summary = "Server 已禁用，恢复前需先确认是否重新启用并重新验证。"
		recovery.FailureMode = "server_disabled"
		recovery.Recoverable = true
		addAction("enable", "重新启用 Server", "确认配置仍然有效后重新启用。", "high")
		addAction("test", "测试连接", "启用后先验证连接，再决定是否刷新 catalog。", "medium")
		if catalog == nil || catalog.ToolCount == 0 || catalog.IsStale {
			addAction("refresh", "刷新 Catalog", "重新发现工具并更新缓存 snapshot。", "medium")
		}
	case availability != nil && availability.Reason == "connection_failed":
		recovery.Status = "blocked"
		recovery.Severity = "critical"
		recovery.Summary = "最近一次连接测试失败，需先恢复 server 连通性，再重新验证 catalog。"
		recovery.FailureMode = "connection_failed"
		recovery.Recoverable = true
		addAction("test", "重新测试连接", "修复 endpoint、命令、凭据或网络后重新测试。", "high")
		if catalog != nil && catalog.ToolCount > 0 {
			addAction("refresh", "连接恢复后刷新 Catalog", "连接恢复后重新发现工具，避免继续依赖旧 snapshot。", "medium")
		}
	case availability != nil && availability.Reason == "catalog_empty":
		recovery.Status = "needs_catalog"
		recovery.Severity = "high"
		recovery.Summary = "当前没有可供 agent 使用的缓存工具，需先建立或重建 catalog。"
		recovery.FailureMode = "catalog_empty"
		recovery.Recoverable = true
		if connection != nil && connection.Status == "untested" {
			addAction("test", "先测试连接", "确认 server 可达后再刷新 catalog，减少无效刷新。", "high")
		}
		addAction("refresh", "刷新 Catalog", "执行工具发现并写回最新缓存。", "high")
	case availability != nil && availability.Reason == "catalog_stale":
		recovery.Status = "stale"
		recovery.Severity = "medium"
		recovery.Summary = "当前仍能绑定，但缓存 catalog 已过期，建议尽快刷新，避免 agent 继续依赖旧工具快照。"
		recovery.FailureMode = "catalog_stale"
		recovery.Recoverable = true
		addAction("refresh", "刷新 Catalog", "更新工具快照并消除 stale 状态。", "high")
		if connection != nil && connection.Status != "healthy" {
			addAction("test", "补做连接测试", "刷新前补齐连通性验证，确认 stale 不是由失联导致。", "medium")
		}
	case availability != nil && availability.Reason == "connection_untested":
		recovery.Status = "verify"
		recovery.Severity = "medium"
		recovery.Summary = "已有缓存工具，但连接状态尚未验证，建议先补齐测试，避免把未知健康状态投入生产。"
		recovery.FailureMode = "connection_untested"
		recovery.Recoverable = true
		addAction("test", "测试连接", "建立健康基线并确认当前缓存工具仍可访问。", "high")
		if catalog != nil && catalog.IsStale {
			addAction("refresh", "必要时刷新 Catalog", "若工具已过期，再补做 refresh。", "medium")
		}
	default:
		recovery.Status = "healthy"
		recovery.Severity = "info"
		recovery.Summary = "连接、catalog 和可用性状态都已对齐，当前没有阻塞性恢复动作。"
		recovery.FailureMode = "none"
		recovery.Recoverable = false
	}

	return recovery
}

func buildMCPRecoveryImpact(bindingUsage *database.MCPBindingUsage) *database.MCPRecoveryImpact {
	if bindingUsage == nil {
		return &database.MCPRecoveryImpact{
			Summary: "当前没有 agent 受到影响。",
		}
	}

	impact := &database.MCPRecoveryImpact{
		AgentCount:         bindingUsage.AgentCount,
		ActiveAgentCount:   bindingUsage.ActiveAgentCount,
		InactiveAgentCount: bindingUsage.InactiveAgentCount,
	}

	switch {
	case impact.AgentCount <= 0:
		impact.Summary = "当前没有 agent 受到影响。"
	case impact.ActiveAgentCount > 0 && impact.InactiveAgentCount > 0:
		impact.Summary = fmt.Sprintf("当前影响 %d 个已绑定 agent，其中 %d 个处于 active 状态。", impact.AgentCount, impact.ActiveAgentCount)
	case impact.ActiveAgentCount > 0:
		impact.Summary = fmt.Sprintf("当前影响 %d 个已绑定 agent，且都处于 active 状态。", impact.AgentCount)
	default:
		impact.Summary = fmt.Sprintf("当前影响 %d 个已绑定 agent，但采样中没有 active agent。", impact.AgentCount)
	}

	return impact
}

func buildMCPSecurityScore(server *database.MCPServer, tools []*database.MCPServerTool, now time.Time) *database.MCPSecurityScore {
	if server == nil {
		return nil
	}

	breakdown := []*database.MCPSecurityBreakdown{
		buildMCPConnectionSecurityBreakdown(server),
		buildMCPCatalogSecurityBreakdown(server),
		buildMCPBindingSecurityBreakdown(server),
		buildMCPConfigurationSecurityBreakdown(server, tools),
		buildMCPAuditSecurityBreakdown(server),
	}

	score := 0
	maxScore := 0
	for _, item := range breakdown {
		if item == nil {
			continue
		}
		score += item.Score
		maxScore += item.MaxScore
	}
	if score < 0 {
		score = 0
	}
	if score > maxScore {
		score = maxScore
	}

	status := "healthy"
	riskLevel := "low"
	summary := "MCP server 安全基线良好。"
	switch {
	case score < 40:
		status = "critical"
		riskLevel = "critical"
		summary = "MCP server 存在关键治理风险，建议先阻断绑定并完成连接与 catalog 修复。"
	case score < 65:
		status = "warning"
		riskLevel = "high"
		summary = "MCP server 存在高风险项，投入生产前需要完成恢复动作。"
	case score < 85:
		status = "watch"
		riskLevel = "medium"
		summary = "MCP server 可用但需要持续治理，建议补齐验证或刷新。"
	}
	if server.Status != "active" {
		status = "disabled"
		riskLevel = "medium"
		summary = "MCP server 已禁用，重新启用前需要重新完成安全基线验证。"
	}

	evaluatedAt := now.UTC()
	return &database.MCPSecurityScore{
		Score:       score,
		MaxScore:    maxScore,
		Status:      status,
		RiskLevel:   riskLevel,
		Summary:     summary,
		EvaluatedAt: &evaluatedAt,
		Breakdown:   breakdown,
	}
}

func buildMCPConnectionSecurityBreakdown(server *database.MCPServer) *database.MCPSecurityBreakdown {
	item := &database.MCPSecurityBreakdown{
		Key:      "connection",
		Label:    "连接验证",
		MaxScore: 25,
		Status:   "healthy",
		Summary:  "最近连接验证通过。",
	}
	switch {
	case server.Status != "active":
		item.Score = 10
		item.Status = "disabled"
		item.Summary = "Server 已禁用，连接基线需要重新确认。"
	case server.Connection != nil && server.Connection.Status == "healthy":
		item.Score = 25
	case server.Connection != nil && server.Connection.Status == "untested":
		item.Score = 12
		item.Status = "warning"
		item.Summary = "尚未完成连接测试。"
	case server.Connection != nil && server.Connection.Status == "degraded":
		item.Score = 0
		item.Status = "critical"
		item.Summary = "最近连接测试失败。"
	default:
		item.Score = 8
		item.Status = "warning"
		item.Summary = "连接状态未知。"
	}
	return item
}

func buildMCPCatalogSecurityBreakdown(server *database.MCPServer) *database.MCPSecurityBreakdown {
	item := &database.MCPSecurityBreakdown{
		Key:      "catalog",
		Label:    "工具 Catalog",
		MaxScore: 25,
		Status:   "healthy",
		Summary:  "工具 catalog 已刷新且可用。",
	}
	switch {
	case server.Status != "active":
		item.Score = 10
		item.Status = "disabled"
		item.Summary = "Server 已禁用，catalog 不参与运行时发现。"
	case server.Catalog != nil && server.Catalog.ToolCount > 0 && !server.Catalog.IsStale:
		item.Score = 25
	case server.Catalog != nil && server.Catalog.ToolCount > 0 && server.Catalog.IsStale:
		item.Score = 14
		item.Status = "warning"
		item.Summary = "已有工具缓存，但 catalog 已过期。"
	case server.Catalog != nil && server.Catalog.Status == "empty":
		item.Score = 5
		item.Status = "critical"
		item.Summary = "最近 catalog 刷新未发现可用工具。"
	default:
		item.Score = 0
		item.Status = "critical"
		item.Summary = "尚未建立可用工具 catalog。"
	}
	return item
}

func buildMCPBindingSecurityBreakdown(server *database.MCPServer) *database.MCPSecurityBreakdown {
	item := &database.MCPSecurityBreakdown{
		Key:      "binding_impact",
		Label:    "绑定影响面",
		MaxScore: 20,
		Status:   "healthy",
		Summary:  "当前没有高影响绑定风险。",
	}
	if server.BindingUsage == nil || server.BindingUsage.AgentCount <= 0 {
		item.Score = 20
		item.Summary = "当前未绑定 agent，影响面较低。"
		return item
	}
	activeCount := server.BindingUsage.ActiveAgentCount
	if server.Recovery != nil && server.Recovery.Recoverable && server.Recovery.Status != "healthy" {
		switch {
		case activeCount >= 3:
			item.Score = 4
			item.Status = "critical"
			item.Summary = fmt.Sprintf("风险状态仍影响 %d 个 active agent。", activeCount)
		case activeCount > 0:
			item.Score = 10
			item.Status = "warning"
			item.Summary = fmt.Sprintf("风险状态仍影响 %d 个 active agent。", activeCount)
		default:
			item.Score = 14
			item.Status = "warning"
			item.Summary = "风险状态影响已绑定 agent，但当前采样中没有 active agent。"
		}
		return item
	}
	if activeCount >= 5 {
		item.Score = 16
		item.Status = "watch"
		item.Summary = fmt.Sprintf("已绑定 %d 个 active agent，需保持审计关注。", activeCount)
		return item
	}
	item.Score = 20
	item.Summary = server.BindingUsage.Summary
	return item
}

func buildMCPConfigurationSecurityBreakdown(server *database.MCPServer, tools []*database.MCPServerTool) *database.MCPSecurityBreakdown {
	item := &database.MCPSecurityBreakdown{
		Key:      "configuration",
		Label:    "配置暴露面",
		MaxScore: 15,
		Status:   "healthy",
		Summary:  "配置未发现明显高风险暴露面。",
		Score:    15,
	}

	penalty := 0
	reasons := make([]string, 0, 3)
	if strings.TrimSpace(server.Transport) == "stdio" {
		penalty += 3
		reasons = append(reasons, "stdio transport 需要运行本地命令")
	}
	if containsUnmaskedSensitiveRaw(server.Env) || containsUnmaskedSensitiveRaw(server.Metadata) {
		penalty += 6
		reasons = append(reasons, "配置中仍包含未脱敏敏感字段")
	}
	if strings.TrimSpace(server.Endpoint) != "" {
		if parsed, err := url.Parse(strings.TrimSpace(server.Endpoint)); err == nil && parsed.Scheme == "http" {
			penalty += 4
			reasons = append(reasons, "endpoint 使用明文 HTTP")
		}
	}
	if len(tools) > 30 {
		penalty += 2
		reasons = append(reasons, fmt.Sprintf("暴露工具数量较多（%d 个）", len(tools)))
	}

	item.Score -= penalty
	if item.Score < 0 {
		item.Score = 0
	}
	switch {
	case item.Score < 8:
		item.Status = "critical"
	case item.Score < item.MaxScore:
		item.Status = "warning"
	}
	if len(reasons) > 0 {
		item.Summary = strings.Join(reasons, "；") + "。"
	}
	return item
}

func buildMCPAuditSecurityBreakdown(server *database.MCPServer) *database.MCPSecurityBreakdown {
	item := &database.MCPSecurityBreakdown{
		Key:      "audit_trail",
		Label:    "调用审计",
		MaxScore: 15,
		Status:   "healthy",
		Summary:  "最近治理审计未发现失败趋势。",
		Score:    15,
	}
	failed := 0
	total := 0
	for _, event := range server.Events {
		if event == nil {
			continue
		}
		total++
		if strings.TrimSpace(event.Status) == "failed" {
			failed++
		}
	}
	if total == 0 {
		item.Score = 8
		item.Status = "warning"
		item.Summary = "尚未形成治理审计历史。"
		return item
	}
	if failed >= 3 {
		item.Score = 2
		item.Status = "critical"
		item.Summary = fmt.Sprintf("最近 %d 条治理事件中有 %d 条失败。", total, failed)
		return item
	}
	if failed > 0 {
		item.Score = 10
		item.Status = "warning"
		item.Summary = fmt.Sprintf("最近 %d 条治理事件中有 %d 条失败。", total, failed)
	}
	return item
}

func containsUnmaskedSensitiveRaw(raw json.RawMessage) bool {
	if len(raw) == 0 {
		return false
	}
	return containsUnmaskedSensitiveValue(parseJSONRaw(raw, `{}`), nil)
}

func containsUnmaskedSensitiveValue(value any, path []string) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, item := range typed {
			nextPath := append(path, key)
			if isSensitiveKey(key) || isSensitiveContainerKey(key) {
				if stringContainsUnmaskedSecret(item) {
					return true
				}
			}
			if containsUnmaskedSensitiveValue(item, nextPath) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if containsUnmaskedSensitiveValue(item, path) {
				return true
			}
		}
	}
	return false
}

func stringContainsUnmaskedSecret(value any) bool {
	switch typed := value.(type) {
	case string:
		trimmed := strings.TrimSpace(typed)
		return trimmed != "" && trimmed != maskedSecretValue
	case map[string]any:
		for _, item := range typed {
			if stringContainsUnmaskedSecret(item) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if stringContainsUnmaskedSecret(item) {
				return true
			}
		}
	}
	return false
}

func (s *AgentService) buildMCPGovernanceSummary(
	tenantID string,
	servers []*database.MCPServer,
	filters *MCPGovernanceEventFilters,
) (*MCPServerGovernanceSummary, error) {
	eventFilters := normalizeMCPGovernanceEventFilters(filters)
	recentEvents := make([]*database.MCPServerEvent, 0)
	if s.mcpStore != nil {
		items, err := s.mcpStore.ListTenantServerEvents(
			tenantID,
			eventFilters.ServerID,
			eventFilters.ActionType,
			eventFilters.Status,
			eventFilters.FailureMode,
			eventFilters.Limit,
		)
		if err != nil {
			return nil, err
		}
		recentEvents = items
	}

	summary := &MCPServerGovernanceSummary{
		TotalServers:       len(servers),
		LongStaleServers:   make([]*database.MCPServer, 0),
		RecoverableServers: make([]*database.MCPServer, 0),
		RecentEvents:       recentEvents,
		FailureModeCounts:  map[string]int{},
		ActionTypeCounts:   map[string]int{},
		EventStatusCounts:  map[string]int{},
		EventFilters:       eventFilters,
	}

	for _, server := range servers {
		if server == nil {
			continue
		}

		if server.Recovery != nil {
			failureMode := strings.TrimSpace(server.Recovery.FailureMode)
			if failureMode != "" && failureMode != "none" {
				summary.FailureModeCounts[failureMode]++
			}
			if server.Recovery.Recoverable && server.Recovery.Status != "healthy" {
				summary.RecoveringServers++
				summary.RecoverableServers = append(summary.RecoverableServers, server)
			}
			if server.Recovery.Status == "blocked" {
				summary.BlockedServers++
			}
		}

		if server.Catalog != nil {
			if server.Catalog.IsStale {
				summary.StaleServers++
				if server.Catalog.AgeSeconds != nil && *server.Catalog.AgeSeconds > int64((72*time.Hour).Seconds()) {
					summary.LongStaleServers = append(summary.LongStaleServers, server)
				}
			}
		}

		if server.Connection != nil && server.Connection.Status == "untested" {
			summary.UntestedServers++
		}

		if server.BindingUsage != nil {
			summary.ImpactedAgents += server.BindingUsage.AgentCount
			summary.ActiveImpactedAgents += server.BindingUsage.ActiveAgentCount
		}
	}

	for _, event := range recentEvents {
		if event == nil {
			continue
		}
		status := strings.TrimSpace(event.Status)
		if status != "" {
			summary.EventStatusCounts[status]++
		}
		actionType := strings.TrimSpace(event.ActionType)
		if actionType != "" {
			summary.ActionTypeCounts[actionType]++
		}
		failureMode := strings.TrimSpace(event.FailureMode)
		if failureMode != "" && failureMode != "none" {
			summary.FailureModeCounts[failureMode]++
		}
	}
	summary.RecentEventCount = len(recentEvents)

	return summary, nil
}

func normalizeMCPGovernanceEventFilters(filters *MCPGovernanceEventFilters) *MCPGovernanceEventFilters {
	if filters == nil {
		filters = &MCPGovernanceEventFilters{}
	}
	normalized := &MCPGovernanceEventFilters{
		ServerID:    strings.TrimSpace(filters.ServerID),
		ActionType:  strings.TrimSpace(strings.ToLower(filters.ActionType)),
		Status:      strings.TrimSpace(strings.ToLower(filters.Status)),
		FailureMode: strings.TrimSpace(strings.ToLower(filters.FailureMode)),
		Limit:       filters.Limit,
	}
	if normalized.Limit <= 0 {
		normalized.Limit = 40
	}
	if normalized.Limit > 200 {
		normalized.Limit = 200
	}
	return normalized
}

func (s *AgentService) recordMCPServerEvent(
	tenantID string,
	userID string,
	server *database.MCPServer,
	eventType string,
	actionType string,
	status string,
	failureMode string,
	summary string,
) (*database.MCPServerEvent, error) {
	if server == nil {
		return nil, nil
	}

	details := map[string]any{
		"server_status": server.Status,
	}
	if server.Connection != nil {
		details["connection"] = server.Connection
	}
	if server.Catalog != nil {
		details["catalog"] = server.Catalog
	}
	if server.Availability != nil {
		details["availability"] = server.Availability
	}
	if server.Recovery != nil {
		details["recovery"] = server.Recovery
	}
	if server.BindingUsage != nil {
		details["impact"] = server.BindingUsage
	}

	detailsRaw, err := json.Marshal(maskSensitiveObject(details, false))
	if err != nil {
		detailsRaw = json.RawMessage(`{}`)
	}

	var actorUserID *string
	if strings.TrimSpace(userID) != "" {
		actorUserID = stringPtr(userID)
	}

	return s.mcpStore.AppendServerEvent(&database.MCPServerEvent{
		TenantID:    tenantID,
		ServerID:    server.ID,
		ServerName:  server.Name,
		EventType:   eventType,
		ActionType:  actionType,
		Status:      status,
		FailureMode: failureMode,
		Summary:     summary,
		Details:     detailsRaw,
		ActorUserID: actorUserID,
	})
}

func (s *AgentService) recordMCPBulkActionAuditEvent(
	tenantID string,
	userID string,
	stage string,
	preview *MCPServerBulkActionPreview,
	driftedServers []string,
	failureMode string,
	summary string,
) (*database.MCPServerEvent, error) {
	if s.mcpStore == nil || preview == nil {
		return nil, nil
	}
	details := map[string]any{
		"stage":                 stage,
		"action":                preview.Action,
		"ordered_by":            preview.OrderedBy,
		"requires_confirmation": preview.RequiresConfirmation,
		"selected_server_ids":   preview.SelectedServerIDs,
		"risk_summary":          preview.RiskSummary,
		"drifted_servers":       driftedServers,
	}
	if preview.GeneratedAt != nil {
		details["generated_at"] = preview.GeneratedAt.Format(time.RFC3339Nano)
	}
	if preview.ExpiresAt != nil {
		details["expires_at"] = preview.ExpiresAt.Format(time.RFC3339Nano)
	}
	if len(preview.Recommendations) > 0 {
		details["recommendation_count"] = len(preview.Recommendations)
		details["top_recommendations"] = preview.Recommendations[:minInt(len(preview.Recommendations), 5)]
	}
	if strings.TrimSpace(preview.PreviewToken) != "" {
		details["preview_token_fingerprint"] = fingerprintSensitiveToken(preview.PreviewToken)
	}
	detailsRaw, err := json.Marshal(maskSensitiveObject(details, false))
	if err != nil {
		detailsRaw = json.RawMessage(`{}`)
	}

	status := "succeeded"
	if strings.TrimSpace(failureMode) == "preview_state_drift" {
		status = "failed"
	}
	var actorUserID *string
	if strings.TrimSpace(userID) != "" {
		actorUserID = stringPtr(userID)
	}

	return s.mcpStore.AppendServerEvent(&database.MCPServerEvent{
		TenantID:    tenantID,
		ServerName:  "tenant-wide MCP governance",
		EventType:   "bulk.governance",
		ActionType:  "bulk_" + strings.TrimSpace(stage),
		Status:      status,
		FailureMode: failureMode,
		Summary:     summary,
		Details:     detailsRaw,
		ActorUserID: actorUserID,
	})
}

func summarizeMCPBindingAgents(agents []*database.MCPBindingAgent) string {
	names := make([]string, 0, len(agents))
	for _, agent := range agents {
		if agent == nil {
			continue
		}
		name := strings.TrimSpace(agent.Name)
		if name == "" {
			name = strings.TrimSpace(agent.AgentID)
		}
		if name == "" {
			continue
		}
		names = append(names, name)
	}
	if len(names) == 0 {
		return "unknown agents"
	}
	return strings.Join(names, ", ")
}

func minInt(left, right int) int {
	if left < right {
		return left
	}
	return right
}

func fingerprintSensitiveToken(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(trimmed))
	return base64.RawURLEncoding.EncodeToString(sum[:8])
}

func mergeJSONRaw(current, incoming json.RawMessage, fallback string) json.RawMessage {
	if len(incoming) == 0 {
		return database.NormalizeJSONRawForExport(current, fallback)
	}
	return database.NormalizeJSONRawForExport(incoming, fallback)
}

func mergeMaskedSecretJSONRaw(current, incoming json.RawMessage, fallback string) json.RawMessage {
	if len(incoming) == 0 {
		return database.NormalizeJSONRawForExport(current, fallback)
	}
	return marshalJSONRaw(
		mergeMaskedSecretValue(parseJSONRaw(current, fallback), parseJSONRaw(incoming, fallback)),
		fallback,
	)
}

func parseJSONRaw(raw json.RawMessage, fallback string) any {
	if len(raw) == 0 {
		raw = json.RawMessage(fallback)
	}
	var value any
	if err := json.Unmarshal(raw, &value); err != nil {
		_ = json.Unmarshal([]byte(fallback), &value)
	}
	return value
}

func marshalJSONRaw(value any, fallback string) json.RawMessage {
	encoded, err := json.Marshal(value)
	if err != nil {
		return json.RawMessage(fallback)
	}
	return json.RawMessage(encoded)
}

func mergeMaskedSecretValue(current, incoming any) any {
	switch typed := incoming.(type) {
	case map[string]any:
		existing, _ := current.(map[string]any)
		result := make(map[string]any, len(typed))
		for key, value := range typed {
			result[key] = mergeMaskedSecretValue(existing[key], value)
		}
		return result
	case []any:
		existing, _ := current.([]any)
		result := make([]any, 0, len(typed))
		for index, value := range typed {
			var currentItem any
			if index < len(existing) {
				currentItem = existing[index]
			}
			result = append(result, mergeMaskedSecretValue(currentItem, value))
		}
		return result
	case string:
		if typed == maskedSecretValue && current != nil {
			return current
		}
		return typed
	default:
		return typed
	}
}

func maskSensitiveJSONRaw(raw json.RawMessage, forceMaskStrings bool) json.RawMessage {
	defaultJSON := `{}`
	parsed := parseJSONRaw(raw, defaultJSON)
	if _, isList := parsed.([]any); isList {
		defaultJSON = `[]`
	}
	return marshalJSONRaw(maskSensitiveValue(parsed, nil, forceMaskStrings), defaultJSON)
}

func maskSensitiveObject(value any, forceMaskStrings bool) map[string]any {
	masked, ok := maskSensitiveValue(value, nil, forceMaskStrings).(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return masked
}

func maskSensitiveValue(value any, path []string, forceMaskStrings bool) any {
	switch typed := value.(type) {
	case map[string]any:
		result := make(map[string]any, len(typed))
		for key, item := range typed {
			result[key] = maskSensitiveValue(item, append(path, key), forceMaskStrings || isSensitiveContainerKey(key))
		}
		return result
	case []any:
		result := make([]any, 0, len(typed))
		for _, item := range typed {
			result = append(result, maskSensitiveValue(item, path, forceMaskStrings))
		}
		return result
	case string:
		if typed == "" {
			return typed
		}
		if forceMaskStrings || pathHasSensitiveKey(path) {
			return maskedSecretValue
		}
		return maskSensitiveString(typed)
	default:
		return value
	}
}

func maskSensitiveString(text string) string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return text
	}

	sanitized := sanitizeEmbeddedURLSecrets(text)
	sanitized = bearerTokenPattern.ReplaceAllString(sanitized, "Bearer "+maskedSecretValue)
	sanitized = basicAuthPattern.ReplaceAllString(sanitized, "Basic "+maskedSecretValue)
	sanitized = sensitiveAssignmentPattern.ReplaceAllString(sanitized, "${1}"+maskedSecretValue)

	if looksLikeJSONObject(trimmed) || looksLikeJSONArray(trimmed) {
		var parsed any
		if err := json.Unmarshal([]byte(trimmed), &parsed); err == nil {
			masked := maskSensitiveValue(parsed, nil, false)
			if encoded, err := json.Marshal(masked); err == nil {
				return string(encoded)
			}
		}
	}
	return sanitized
}

func sanitizeEmbeddedURLSecrets(text string) string {
	if strings.TrimSpace(text) == "" {
		return text
	}
	var builder strings.Builder
	lastIndex := 0
	matches := regexp.MustCompile(`https?://[^\s"']+`).FindAllStringIndex(text, -1)
	if len(matches) == 0 {
		return text
	}
	for _, match := range matches {
		start := match[0]
		end := match[1]
		builder.WriteString(text[lastIndex:start])
		builder.WriteString(sanitizeURLString(text[start:end]))
		lastIndex = end
	}
	builder.WriteString(text[lastIndex:])
	return builder.String()
}

func sanitizeURLString(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	if parsed.User != nil {
		username := parsed.User.Username()
		if _, hasPassword := parsed.User.Password(); hasPassword || username != "" {
			parsed.User = nil
		}
	}
	query := parsed.Query()
	for key, values := range query {
		if !isSensitiveKey(key) {
			continue
		}
		for index := range values {
			values[index] = maskedSecretValue
		}
		query[key] = values
	}
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

func looksLikeJSONObject(text string) bool {
	return strings.HasPrefix(text, "{") && strings.HasSuffix(text, "}")
}

func looksLikeJSONArray(text string) bool {
	return strings.HasPrefix(text, "[") && strings.HasSuffix(text, "]")
}

func pathHasSensitiveKey(path []string) bool {
	for _, part := range path {
		if isSensitiveKey(part) || isSensitiveContainerKey(part) {
			return true
		}
	}
	return false
}

func isSensitiveContainerKey(key string) bool {
	switch strings.ToLower(strings.TrimSpace(key)) {
	case "env", "headers", "credentials", "auth":
		return true
	default:
		return false
	}
}

func isSensitiveKey(key string) bool {
	lowered := strings.ToLower(strings.TrimSpace(key))
	if strings.Contains(lowered, "fingerprint") || strings.Contains(lowered, "hash") || strings.Contains(lowered, "checksum") {
		return false
	}
	for _, token := range []string{
		"secret",
		"password",
		"passwd",
		"token",
		"api_key",
		"apikey",
		"access_key",
		"authorization",
		"cookie",
		"client_secret",
		"private_key",
		"bearer",
	} {
		if strings.Contains(lowered, token) {
			return true
		}
	}
	return false
}
