package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrSubagentDefinitionNotFound = errors.New("subagent definition not found")
var ErrSubagentPublicationNotFound = errors.New("subagent publication not found")

type SubagentDefinition struct {
	ID                      string          `json:"id"`
	TenantID                string          `json:"tenant_id"`
	Name                    string          `json:"name"`
	Description             string          `json:"description,omitempty"`
	Slug                    string          `json:"slug,omitempty"`
	SystemPrompt            string          `json:"system_prompt"`
	Model                   string          `json:"model,omitempty"`
	Status                  string          `json:"status"`
	DefinitionStatus        string          `json:"definition_status,omitempty"`
	LifecycleStatus         string          `json:"lifecycle_status,omitempty"`
	Config                  json.RawMessage `json:"config"`
	Metadata                json.RawMessage `json:"metadata"`
	OutputSchema            json.RawMessage `json:"output_schema,omitempty"`
	HandoffInputSchema      json.RawMessage `json:"handoff_input_schema,omitempty"`
	ToolAllowlist           json.RawMessage `json:"tool_allowlist,omitempty"`
	SkillAllowlist          json.RawMessage `json:"skill_allowlist,omitempty"`
	MCPAllowlist            json.RawMessage `json:"mcp_allowlist,omitempty"`
	KnowledgePolicy         json.RawMessage `json:"knowledge_policy,omitempty"`
	ReviewPolicy            json.RawMessage `json:"review_policy,omitempty"`
	RuntimePolicy           json.RawMessage `json:"runtime_policy,omitempty"`
	PublicationID           string          `json:"publication_id,omitempty"`
	PublicationScope        string          `json:"publication_scope,omitempty"`
	PublicationTenantID     string          `json:"publication_tenant_id,omitempty"`
	PublicationMetadata     json.RawMessage `json:"publication_metadata,omitempty"`
	VersionID               string          `json:"version_id,omitempty"`
	VersionNumber           int             `json:"version_number,omitempty"`
	HostAgentDefinitionID   string          `json:"host_agent_definition_id,omitempty"`
	HandoffPrompt           string          `json:"handoff_prompt,omitempty"`
	CreatedBy               *string         `json:"created_by,omitempty"`
	UpdatedBy               *string         `json:"updated_by,omitempty"`
	ArchivedAt              *time.Time      `json:"archived_at,omitempty"`
	CreatedAt               time.Time       `json:"created_at"`
	UpdatedAt               time.Time       `json:"updated_at"`
}

type SubagentDefinitionVersion struct {
	ID                 string          `json:"id"`
	DefinitionID       string          `json:"subagent_definition_id"`
	VersionNumber      int             `json:"version_number"`
	LifecycleStatus    string          `json:"lifecycle_status"`
	SystemPrompt       string          `json:"system_prompt"`
	Model              string          `json:"model,omitempty"`
	Config             json.RawMessage `json:"config"`
	Metadata           json.RawMessage `json:"metadata"`
	OutputSchema       json.RawMessage `json:"output_schema"`
	HandoffInputSchema json.RawMessage `json:"handoff_input_schema"`
	ToolAllowlist      json.RawMessage `json:"tool_allowlist"`
	SkillAllowlist     json.RawMessage `json:"skill_allowlist"`
	MCPAllowlist       json.RawMessage `json:"mcp_allowlist"`
	KnowledgePolicy    json.RawMessage `json:"knowledge_policy"`
	ReviewPolicy       json.RawMessage `json:"review_policy"`
	RuntimePolicy      json.RawMessage `json:"runtime_policy"`
	PublicationID      string          `json:"publication_id,omitempty"`
	PublicationStatus  string          `json:"publication_status,omitempty"`
	PublicationScope   string          `json:"publication_scope,omitempty"`
	IsPublished        bool            `json:"is_published"`
	CreatedBy          *string         `json:"created_by,omitempty"`
	UpdatedBy          *string         `json:"updated_by,omitempty"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
}

type SubagentPublication struct {
	ID           string
	DefinitionID string
	VersionID    string
	TenantID     *string
	Visibility   string
	Status       string
	Metadata     json.RawMessage
	CreatedBy    *string
	UpdatedBy    *string
}

type SubagentPublicationState struct {
	ID                 string          `json:"id"`
	DefinitionID       string          `json:"subagent_definition_id"`
	VersionID          string          `json:"version_id"`
	VersionNumber      int             `json:"version_number"`
	TenantID           string          `json:"tenant_id,omitempty"`
	PublicationScope   string          `json:"publication_scope"`
	Status             string          `json:"status"`
	Metadata           json.RawMessage `json:"metadata"`
	AuthorizationCount int             `json:"authorization_count"`
	CreatedBy          *string         `json:"created_by,omitempty"`
	UpdatedBy          *string         `json:"updated_by,omitempty"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
	ArchivedAt         *time.Time      `json:"archived_at,omitempty"`
}

type SubagentAuthorizedAgent struct {
	AuthorizationID   string          `json:"authorization_id"`
	PublicationID     string          `json:"publication_id"`
	Status            string          `json:"status"`
	Priority          int             `json:"priority"`
	AgentDefinitionID string          `json:"agent_definition_id"`
	AgentName         string          `json:"agent_name"`
	AgentStatus       string          `json:"agent_status"`
	BudgetPolicy      json.RawMessage `json:"budget_policy"`
	Metadata          json.RawMessage `json:"metadata"`
	CreatedAt         time.Time       `json:"created_at"`
	UpdatedAt         time.Time       `json:"updated_at"`
}

type SubagentPublicationChangeEndpoint struct {
	VersionID           string `json:"version_id,omitempty"`
	VersionNumber       int    `json:"version_number"`
	Status              string `json:"status,omitempty"`
	PublicationScope    string `json:"publication_scope,omitempty"`
	PublicationTenantID string `json:"publication_tenant_id,omitempty"`
}

type SubagentPublicationImpactAgent struct {
	AuthorizationID     string `json:"authorization_id,omitempty"`
	AgentDefinitionID   string `json:"agent_definition_id"`
	AgentName           string `json:"agent_name,omitempty"`
	AgentStatus         string `json:"agent_status,omitempty"`
	AuthorizationStatus string `json:"authorization_status,omitempty"`
}

type SubagentCompatibilityDetail struct {
	Kind                  string                            `json:"kind"`
	Summary               string                            `json:"summary"`
	HostAgentDefinitionID string                            `json:"host_agent_definition_id,omitempty"`
	ReferenceKey          string                            `json:"reference_key,omitempty"`
	ImpactedAgentCount    int                               `json:"impacted_agent_count"`
	ActiveAgentCount      int                               `json:"active_agent_count"`
	Agents                []*SubagentPublicationImpactAgent `json:"agents,omitempty"`
}

type SubagentPublicationChangePreview struct {
	ChangeType                 string                             `json:"change_type"`
	RiskLevel                  string                             `json:"risk_level"`
	RequiresConfirmation       bool                               `json:"requires_confirmation"`
	Summary                    string                             `json:"summary"`
	ConfirmationMessage        string                             `json:"confirmation_message,omitempty"`
	Current                    *SubagentPublicationChangeEndpoint `json:"current,omitempty"`
	Target                     *SubagentPublicationChangeEndpoint `json:"target"`
	ImpactedAuthorizationCount int                                `json:"impacted_authorization_count"`
	EnabledAuthorizationCount  int                                `json:"enabled_authorization_count"`
	InactiveAuthorizationCount int                                `json:"inactive_authorization_count"`
	CompatibilityMode          bool                               `json:"compatibility_mode"`
	RecommendedActions         []string                           `json:"recommended_actions"`
	AffectedAgents             []*SubagentPublicationImpactAgent  `json:"affected_agents"`
}

type SubagentMetadataAliasFreezeCandidate struct {
	DefinitionID               string `json:"definition_id"`
	DefinitionName             string `json:"definition_name,omitempty"`
	DefinitionStatus           string `json:"definition_status,omitempty"`
	HostAgentDefinitionID      string `json:"host_agent_definition_id,omitempty"`
	LegacyAliasKey             string `json:"legacy_alias_key,omitempty"`
	LegacyAliasValue           string `json:"legacy_alias_value,omitempty"`
	AuthorizationCount         int    `json:"authorization_count"`
	EnabledAuthorizationCount  int    `json:"enabled_authorization_count"`
	InactiveAuthorizationCount int    `json:"inactive_authorization_count"`
}

type SubagentMetadataAliasFreezePreview struct {
	Executable                 bool                                    `json:"executable"`
	RequiresConfirmation       bool                                    `json:"requires_confirmation"`
	Summary                    string                                  `json:"summary"`
	ConfirmationMessage        string                                  `json:"confirmation_message,omitempty"`
	BlockedReason              string                                  `json:"blocked_reason,omitempty"`
	Scope                      string                                  `json:"scope"`
	DefinitionIDs              []string                                `json:"definition_ids,omitempty"`
	ImpactedCapabilityCount    int                                     `json:"impacted_capability_count"`
	AuthorizationCount         int                                     `json:"authorization_count"`
	EnabledAuthorizationCount  int                                     `json:"enabled_authorization_count"`
	InactiveAuthorizationCount int                                     `json:"inactive_authorization_count"`
	RecommendedActions         []string                                `json:"recommended_actions"`
	AffectedCapabilities       []*SubagentMetadataAliasFreezeCandidate `json:"affected_capabilities"`
}

type SubagentMetadataAliasFreezeResult struct {
	DefinitionID          string          `json:"definition_id"`
	Metadata              json.RawMessage `json:"metadata"`
	HostAgentDefinitionID string          `json:"host_agent_definition_id,omitempty"`
	LegacyAliasKey        string          `json:"legacy_alias_key,omitempty"`
	LegacyAliasValue      string          `json:"legacy_alias_value,omitempty"`
}

type SubagentPublicationEvent struct {
	ID                         string                            `json:"id"`
	TenantID                   string                            `json:"tenant_id"`
	DefinitionID               string                            `json:"subagent_definition_id"`
	DefinitionName             string                            `json:"subagent_definition_name,omitempty"`
	DefinitionStatus           string                            `json:"subagent_definition_status,omitempty"`
	PublicationID              string                            `json:"publication_id,omitempty"`
	EventStage                 string                            `json:"event_stage"`
	ActionType                 string                            `json:"action_type"`
	ChangeType                 string                            `json:"change_type"`
	RiskLevel                  string                            `json:"risk_level"`
	RequiresConfirmation       bool                              `json:"requires_confirmation"`
	Confirmed                  bool                              `json:"confirmed"`
	VersionID                  string                            `json:"version_id,omitempty"`
	VersionNumber              int                               `json:"version_number"`
	PreviousVersionID          string                            `json:"previous_version_id,omitempty"`
	PreviousVersionNumber      int                               `json:"previous_version_number"`
	PublicationScope           string                            `json:"publication_scope,omitempty"`
	PreviousPublicationScope   string                            `json:"previous_publication_scope,omitempty"`
	Status                     string                            `json:"status,omitempty"`
	PreviousStatus             string                            `json:"previous_status,omitempty"`
	ImpactedAuthorizationCount int                               `json:"impacted_authorization_count"`
	EnabledAuthorizationCount  int                               `json:"enabled_authorization_count"`
	InactiveAuthorizationCount int                               `json:"inactive_authorization_count"`
	CompatibilityMode          bool                              `json:"compatibility_mode"`
	Summary                    string                            `json:"summary"`
	ChangeReason               string                            `json:"change_reason,omitempty"`
	ChangeNotes                string                            `json:"change_notes,omitempty"`
	RollbackRecoveryPlan       string                            `json:"rollback_recovery_plan,omitempty"`
	RecommendedActions         json.RawMessage                   `json:"recommended_actions"`
	AffectedAgents             json.RawMessage                   `json:"affected_agents"`
	Metadata                   json.RawMessage                   `json:"metadata"`
	ActorUserID                *string                           `json:"actor_user_id,omitempty"`
	ActorUserEmail             string                            `json:"actor_user_email,omitempty"`
	CreatedAt                  time.Time                         `json:"created_at"`
	RecommendedActionItems     []string                          `json:"-"`
	AffectedAgentItems         []*SubagentPublicationImpactAgent `json:"-"`
}

type SubagentPublicationEventFilters struct {
	DefinitionID      string `json:"definition_id,omitempty"`
	ActionType        string `json:"action_type,omitempty"`
	EventStage        string `json:"event_stage,omitempty"`
	ChangeType        string `json:"change_type,omitempty"`
	RiskLevel         string `json:"risk_level,omitempty"`
	CompatibilityMode string `json:"compatibility_mode,omitempty"`
	Limit             int    `json:"limit"`
	Offset            int    `json:"offset"`
}

type SubagentPublicationEventPage struct {
	Items   []*SubagentPublicationEvent      `json:"items"`
	Total   int                              `json:"total"`
	Filters *SubagentPublicationEventFilters `json:"filters"`
}

type SubagentControlPlane struct {
	Definition     *SubagentDefinition          `json:"definition"`
	Versions       []*SubagentDefinitionVersion `json:"versions"`
	Publication    *SubagentPublicationState    `json:"publication,omitempty"`
	Authorizations []*SubagentAuthorizedAgent   `json:"authorizations"`
	Events         []*SubagentPublicationEvent  `json:"events,omitempty"`
	Governance     *SubagentGovernanceSummary   `json:"governance,omitempty"`
}

type SubagentGovernanceWarning struct {
	Code     string `json:"code"`
	Severity string `json:"severity"`
	Message  string `json:"message"`
}

type SubagentBridgeRemovalChecklistItem struct {
	Key                string   `json:"key"`
	Label              string   `json:"label"`
	Status             string   `json:"status"`
	Blocking           bool     `json:"blocking"`
	Summary            string   `json:"summary"`
	RecommendedActions []string `json:"recommended_actions,omitempty"`
}

type SubagentBridgeRemovalReadiness struct {
	Status             string                                `json:"status"`
	Ready              bool                                  `json:"ready"`
	BlockingIssueCount int                                   `json:"blocking_issue_count"`
	PendingIssueCount  int                                   `json:"pending_issue_count"`
	Summary            string                                `json:"summary"`
	RecommendedActions []string                              `json:"recommended_actions"`
	Checklist          []*SubagentBridgeRemovalChecklistItem `json:"checklist,omitempty"`
}

type SubagentGovernanceSummary struct {
	CompatibilityMode          bool                               `json:"compatibility_mode"`
	HostAgentDefinitionID      string                             `json:"host_agent_definition_id,omitempty"`
	CanFreezeMetadataAliases   bool                               `json:"can_freeze_metadata_aliases"`
	CompatibilityDetails       []*SubagentCompatibilityDetail     `json:"compatibility_details,omitempty"`
	LatestVersionNumber        int                                `json:"latest_version_number"`
	PublishedVersionNumber     int                                `json:"published_version_number"`
	IsPublishedVersionLatest   bool                               `json:"is_published_version_latest"`
	AuthorizationCount         int                                `json:"authorization_count"`
	EnabledAuthorizationCount  int                                `json:"enabled_authorization_count"`
	InactiveAuthorizationCount int                                `json:"inactive_authorization_count"`
	RollbackCandidateCount     int                                `json:"rollback_candidate_count"`
	HasRollbackCandidate       bool                               `json:"has_rollback_candidate"`
	NextPublicationPreview     *SubagentPublicationChangePreview  `json:"next_publication_preview,omitempty"`
	MetadataAliasFreezePreview *SubagentMetadataAliasFreezePreview `json:"metadata_alias_freeze_preview,omitempty"`
	BridgeRemovalReadiness     *SubagentBridgeRemovalReadiness    `json:"bridge_removal_readiness,omitempty"`
	Warnings                   []*SubagentGovernanceWarning       `json:"warnings"`
}

type SubagentStore struct {
	pool *pgxpool.Pool
}

func NewSubagentStore(pool *pgxpool.Pool) *SubagentStore {
	return &SubagentStore{pool: pool}
}

type scanTarget interface {
	Scan(dest ...any) error
}

const managedSubagentSelect = `
	SELECT
		d.id,
		d.tenant_id,
		d.name,
		d.description,
		COALESCE(v.system_prompt, d.system_prompt) AS system_prompt,
		COALESCE(v.model, d.model) AS model,
		COALESCE(p.status, d.status) AS publication_status,
		d.status AS definition_status,
		COALESCE(v.lifecycle_status, 'draft') AS lifecycle_status,
		COALESCE(v.config, d.config) AS config,
		(COALESCE(d.metadata, '{}'::jsonb) || COALESCE(v.metadata, '{}'::jsonb) || COALESCE(p.metadata, '{}'::jsonb)) AS merged_metadata,
		COALESCE(v.output_schema, '{}'::jsonb) AS output_schema,
		COALESCE(v.handoff_input_schema, '{}'::jsonb) AS handoff_input_schema,
		COALESCE(v.tool_allowlist, '[]'::jsonb) AS tool_allowlist,
		COALESCE(v.skill_allowlist, '[]'::jsonb) AS skill_allowlist,
		COALESCE(v.mcp_allowlist, '[]'::jsonb) AS mcp_allowlist,
		COALESCE(v.knowledge_policy, '{}'::jsonb) AS knowledge_policy,
		COALESCE(v.review_policy, '{}'::jsonb) AS review_policy,
		COALESCE(v.runtime_policy, '{}'::jsonb) AS runtime_policy,
		COALESCE(p.id::text, '') AS publication_id,
		COALESCE(p.visibility, 'tenant') AS publication_scope,
		COALESCE(p.tenant_id::text, '') AS publication_tenant_id,
		COALESCE(p.metadata, '{}'::jsonb) AS publication_metadata,
		COALESCE(v.id::text, '') AS version_id,
		COALESCE(v.version_number, 0) AS version_number,
		d.created_by,
		d.updated_by,
		d.archived_at,
		d.created_at,
		d.updated_at
	FROM subagent_definitions d
	INNER JOIN subagent_publications p
		ON p.subagent_definition_id = d.id
	INNER JOIN subagent_definition_versions v
		ON v.id = p.version_id
`

func scanManagedSubagent(row scanTarget) (*SubagentDefinition, error) {
	item := &SubagentDefinition{}
	if err := row.Scan(
		&item.ID,
		&item.TenantID,
		&item.Name,
		&item.Description,
		&item.SystemPrompt,
		&item.Model,
		&item.Status,
		&item.DefinitionStatus,
		&item.LifecycleStatus,
		&item.Config,
		&item.Metadata,
		&item.OutputSchema,
		&item.HandoffInputSchema,
		&item.ToolAllowlist,
		&item.SkillAllowlist,
		&item.MCPAllowlist,
		&item.KnowledgePolicy,
		&item.ReviewPolicy,
		&item.RuntimePolicy,
		&item.PublicationID,
		&item.PublicationScope,
		&item.PublicationTenantID,
		&item.PublicationMetadata,
		&item.VersionID,
		&item.VersionNumber,
		&item.CreatedBy,
		&item.UpdatedBy,
		&item.ArchivedAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	); err != nil {
		return nil, err
	}
	return item, nil
}

func scanSubagentVersion(row scanTarget) (*SubagentDefinitionVersion, error) {
	item := &SubagentDefinitionVersion{}
	if err := row.Scan(
		&item.ID,
		&item.DefinitionID,
		&item.VersionNumber,
		&item.LifecycleStatus,
		&item.SystemPrompt,
		&item.Model,
		&item.Config,
		&item.Metadata,
		&item.OutputSchema,
		&item.HandoffInputSchema,
		&item.ToolAllowlist,
		&item.SkillAllowlist,
		&item.MCPAllowlist,
		&item.KnowledgePolicy,
		&item.ReviewPolicy,
		&item.RuntimePolicy,
		&item.PublicationID,
		&item.PublicationStatus,
		&item.PublicationScope,
		&item.IsPublished,
		&item.CreatedBy,
		&item.UpdatedBy,
		&item.CreatedAt,
		&item.UpdatedAt,
	); err != nil {
		return nil, err
	}
	return item, nil
}

func scanSubagentPublicationState(row scanTarget) (*SubagentPublicationState, error) {
	item := &SubagentPublicationState{}
	if err := row.Scan(
		&item.ID,
		&item.DefinitionID,
		&item.VersionID,
		&item.VersionNumber,
		&item.TenantID,
		&item.PublicationScope,
		&item.Status,
		&item.Metadata,
		&item.AuthorizationCount,
		&item.CreatedBy,
		&item.UpdatedBy,
		&item.CreatedAt,
		&item.UpdatedAt,
		&item.ArchivedAt,
	); err != nil {
		return nil, err
	}
	return item, nil
}

func scanSubagentAuthorizedAgent(row scanTarget) (*SubagentAuthorizedAgent, error) {
	item := &SubagentAuthorizedAgent{}
	if err := row.Scan(
		&item.AuthorizationID,
		&item.PublicationID,
		&item.Status,
		&item.Priority,
		&item.AgentDefinitionID,
		&item.AgentName,
		&item.AgentStatus,
		&item.BudgetPolicy,
		&item.Metadata,
		&item.CreatedAt,
		&item.UpdatedAt,
	); err != nil {
		return nil, err
	}
	return item, nil
}

func scanSubagentPublicationEvent(row scanTarget) (*SubagentPublicationEvent, error) {
	item := &SubagentPublicationEvent{}
	if err := row.Scan(
		&item.ID,
		&item.TenantID,
		&item.DefinitionID,
		&item.DefinitionName,
		&item.DefinitionStatus,
		&item.PublicationID,
		&item.EventStage,
		&item.ActionType,
		&item.ChangeType,
		&item.RiskLevel,
		&item.RequiresConfirmation,
		&item.Confirmed,
		&item.VersionID,
		&item.VersionNumber,
		&item.PreviousVersionID,
		&item.PreviousVersionNumber,
		&item.PublicationScope,
		&item.PreviousPublicationScope,
		&item.Status,
		&item.PreviousStatus,
		&item.ImpactedAuthorizationCount,
		&item.EnabledAuthorizationCount,
		&item.InactiveAuthorizationCount,
		&item.CompatibilityMode,
		&item.Summary,
		&item.ChangeReason,
		&item.ChangeNotes,
		&item.RollbackRecoveryPlan,
		&item.RecommendedActions,
		&item.AffectedAgents,
		&item.Metadata,
		&item.ActorUserID,
		&item.ActorUserEmail,
		&item.CreatedAt,
	); err != nil {
		return nil, err
	}
	if len(item.RecommendedActions) > 0 {
		_ = json.Unmarshal(item.RecommendedActions, &item.RecommendedActionItems)
	}
	if len(item.AffectedAgents) > 0 {
		_ = json.Unmarshal(item.AffectedAgents, &item.AffectedAgentItems)
	}
	return item, nil
}

func defaultSubagentDefinitionStatus(value string) string {
	if value == "" {
		return "active"
	}
	return value
}

func defaultSubagentLifecycleStatus(value string) string {
	if value == "" {
		return "active"
	}
	return value
}

func defaultSubagentPublicationScope(value string) string {
	if value == "" {
		return "tenant"
	}
	return value
}

func defaultSubagentPublicationStatus(value string) string {
	if value == "" {
		return "active"
	}
	return value
}

func stringValueOrEmpty(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func publicationTenantValue(tenantID, scope string) any {
	if defaultSubagentPublicationScope(scope) == "system_global" {
		return nil
	}
	return tenantID
}

func parseJSONComparable(raw json.RawMessage, fallback string) any {
	if len(raw) == 0 {
		raw = json.RawMessage(fallback)
	}
	var value any
	if err := json.Unmarshal(raw, &value); err != nil {
		_ = json.Unmarshal([]byte(fallback), &value)
	}
	return value
}

func jsonRawEqual(left, right json.RawMessage, fallback string) bool {
	return reflect.DeepEqual(parseJSONComparable(left, fallback), parseJSONComparable(right, fallback))
}

func normalizeSubagentMetadataAliases(raw json.RawMessage) (json.RawMessage, string, string, string, bool, error) {
	payload := map[string]any{}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			return nil, "", "", "", false, fmt.Errorf("invalid subagent metadata: %w", err)
		}
	}

	hostAgentDefinitionID := strings.TrimSpace(stringValueFromAnyMap(payload, "host_agent_definition_id"))
	legacyAliasKey := ""
	legacyAliasValue := ""
	if hostAgentDefinitionID == "" {
		if value := strings.TrimSpace(stringValueFromAnyMap(payload, "target_agent_definition_id")); value != "" {
			hostAgentDefinitionID = value
			legacyAliasKey = "target_agent_definition_id"
			legacyAliasValue = value
		}
	}
	if hostAgentDefinitionID == "" {
		if value := strings.TrimSpace(stringValueFromAnyMap(payload, "agent_definition_id")); value != "" {
			hostAgentDefinitionID = value
			legacyAliasKey = "agent_definition_id"
			legacyAliasValue = value
		}
	}
	if legacyAliasKey == "" {
		if value := strings.TrimSpace(stringValueFromAnyMap(payload, "target_agent_definition_id")); value != "" {
			legacyAliasKey = "target_agent_definition_id"
			legacyAliasValue = value
		} else if value := strings.TrimSpace(stringValueFromAnyMap(payload, "agent_definition_id")); value != "" {
			legacyAliasKey = "agent_definition_id"
			legacyAliasValue = value
		}
	}

	beforeCanonicalHost := strings.TrimSpace(stringValueFromAnyMap(payload, "host_agent_definition_id"))
	beforeLegacyTarget := strings.TrimSpace(stringValueFromAnyMap(payload, "target_agent_definition_id"))
	beforeLegacyAgent := strings.TrimSpace(stringValueFromAnyMap(payload, "agent_definition_id"))

	delete(payload, "target_agent_definition_id")
	delete(payload, "agent_definition_id")
	delete(payload, "host_agent_definition_id")
	if hostAgentDefinitionID != "" {
		payload["host_agent_definition_id"] = hostAgentDefinitionID
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, "", "", "", false, fmt.Errorf("failed to encode canonical subagent metadata: %w", err)
	}

	changed := beforeLegacyTarget != "" || beforeLegacyAgent != ""
	if !changed && beforeCanonicalHost != hostAgentDefinitionID {
		changed = true
	}
	return normalizeJSONRaw(encoded, `{}`), hostAgentDefinitionID, legacyAliasKey, legacyAliasValue, changed, nil
}

func stringValueFromAnyMap(payload map[string]any, key string) string {
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

func versionEquivalent(left *SubagentDefinitionVersion, right *SubagentDefinition) bool {
	if left == nil || right == nil {
		return false
	}
	return left.SystemPrompt == right.SystemPrompt &&
		left.Model == right.Model &&
		jsonRawEqual(left.Config, right.Config, `{}`) &&
		jsonRawEqual(left.Metadata, right.Metadata, `{}`) &&
		jsonRawEqual(left.OutputSchema, right.OutputSchema, `{}`) &&
		jsonRawEqual(left.HandoffInputSchema, right.HandoffInputSchema, `{}`) &&
		jsonRawEqual(left.ToolAllowlist, right.ToolAllowlist, `[]`) &&
		jsonRawEqual(left.SkillAllowlist, right.SkillAllowlist, `[]`) &&
		jsonRawEqual(left.MCPAllowlist, right.MCPAllowlist, `[]`) &&
		jsonRawEqual(left.KnowledgePolicy, right.KnowledgePolicy, `{}`) &&
		jsonRawEqual(left.ReviewPolicy, right.ReviewPolicy, `{}`) &&
		jsonRawEqual(left.RuntimePolicy, right.RuntimePolicy, `{}`)
}

func publicationEquivalent(left *SubagentPublicationState, right *SubagentDefinition, versionID string) bool {
	if left == nil || right == nil {
		return false
	}
	return left.VersionID == versionID &&
		left.Status == defaultSubagentPublicationStatus(right.Status) &&
		left.PublicationScope == defaultSubagentPublicationScope(right.PublicationScope) &&
		((left.TenantID == "" && publicationTenantValue(right.PublicationTenantID, right.PublicationScope) == nil) ||
			left.TenantID == right.createdPublicationTenantValue()) &&
		jsonRawEqual(left.Metadata, right.PublicationMetadata, `{}`)
}

func (s *SubagentStore) nextVersionNumberTx(ctx context.Context, tx pgx.Tx, definitionID string) (int, error) {
	var latest int
	err := tx.QueryRow(ctx, `
		SELECT COALESCE(MAX(version_number), 0)
		FROM subagent_definition_versions
		WHERE subagent_definition_id = $1
	`, definitionID).Scan(&latest)
	if err != nil {
		return 0, fmt.Errorf("failed to query latest subagent version number: %w", err)
	}
	return latest + 1, nil
}

func (s *SubagentStore) insertVersionTx(
	ctx context.Context,
	tx pgx.Tx,
	version *SubagentDefinitionVersion,
) (*SubagentDefinitionVersion, error) {
	row := &SubagentDefinitionVersion{}
	err := tx.QueryRow(ctx, `
		INSERT INTO subagent_definition_versions (
			subagent_definition_id, version_number, lifecycle_status, system_prompt, model,
			config, metadata, output_schema, handoff_input_schema, tool_allowlist,
			skill_allowlist, mcp_allowlist, knowledge_policy, review_policy, runtime_policy,
			created_by, updated_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $16)
		RETURNING id, subagent_definition_id, version_number, lifecycle_status, system_prompt, model,
		          config, metadata, output_schema, handoff_input_schema, tool_allowlist, skill_allowlist,
		          mcp_allowlist, knowledge_policy, review_policy, runtime_policy, created_by, updated_by,
		          created_at, updated_at
	`,
		version.DefinitionID,
		version.VersionNumber,
		defaultSubagentLifecycleStatus(version.LifecycleStatus),
		version.SystemPrompt,
		nullIfEmpty(version.Model),
		normalizeJSONRaw(version.Config, `{}`),
		normalizeJSONRaw(version.Metadata, `{}`),
		normalizeJSONRaw(version.OutputSchema, `{}`),
		normalizeJSONRaw(version.HandoffInputSchema, `{}`),
		normalizeJSONRaw(version.ToolAllowlist, `[]`),
		normalizeJSONRaw(version.SkillAllowlist, `[]`),
		normalizeJSONRaw(version.MCPAllowlist, `[]`),
		normalizeJSONRaw(version.KnowledgePolicy, `{}`),
		normalizeJSONRaw(version.ReviewPolicy, `{}`),
		normalizeJSONRaw(version.RuntimePolicy, `{}`),
		nullIfPointer(version.CreatedBy),
	).Scan(
		&row.ID,
		&row.DefinitionID,
		&row.VersionNumber,
		&row.LifecycleStatus,
		&row.SystemPrompt,
		&row.Model,
		&row.Config,
		&row.Metadata,
		&row.OutputSchema,
		&row.HandoffInputSchema,
		&row.ToolAllowlist,
		&row.SkillAllowlist,
		&row.MCPAllowlist,
		&row.KnowledgePolicy,
		&row.ReviewPolicy,
		&row.RuntimePolicy,
		&row.CreatedBy,
		&row.UpdatedBy,
		&row.CreatedAt,
		&row.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to insert subagent definition version: %w", err)
	}
	return row, nil
}

func (s *SubagentStore) upsertPublicationTx(
	ctx context.Context,
	tx pgx.Tx,
	publication *SubagentPublication,
) (*SubagentPublication, error) {
	scope := defaultSubagentPublicationScope(publication.Visibility)
	status := defaultSubagentPublicationStatus(publication.Status)
	tenantValue := publication.TenantID

	var existingID string
	err := tx.QueryRow(ctx, `
		SELECT id
		FROM subagent_publications
		WHERE subagent_definition_id = $1
		ORDER BY created_at DESC
		LIMIT 1
	`, publication.DefinitionID).Scan(&existingID)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return nil, fmt.Errorf("failed to lookup subagent publication: %w", err)
	}

	row := &SubagentPublication{}
	if existingID == "" {
		err = tx.QueryRow(ctx, `
			INSERT INTO subagent_publications (
				subagent_definition_id, version_id, tenant_id, visibility, status, metadata, created_by, updated_by
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
			RETURNING id, subagent_definition_id, version_id, tenant_id, visibility, status, metadata, created_by, updated_by
		`,
			publication.DefinitionID,
			publication.VersionID,
			tenantValue,
			scope,
			status,
			normalizeJSONRaw(publication.Metadata, `{}`),
			nullIfPointer(publication.CreatedBy),
		).Scan(
			&row.ID,
			&row.DefinitionID,
			&row.VersionID,
			&row.TenantID,
			&row.Visibility,
			&row.Status,
			&row.Metadata,
			&row.CreatedBy,
			&row.UpdatedBy,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to create subagent publication: %w", err)
		}
		return row, nil
	}

	err = tx.QueryRow(ctx, `
		UPDATE subagent_publications
		SET
			version_id = $2,
			tenant_id = $3,
			visibility = $4,
			status = $5,
			metadata = $6,
			updated_by = $7,
			archived_at = CASE WHEN $5 = 'archived' THEN now() ELSE NULL END
		WHERE id = $1
		RETURNING id, subagent_definition_id, version_id, tenant_id, visibility, status, metadata, created_by, updated_by
	`,
		existingID,
		publication.VersionID,
		tenantValue,
		scope,
		status,
		normalizeJSONRaw(publication.Metadata, `{}`),
		nullIfPointer(publication.UpdatedBy),
	).Scan(
		&row.ID,
		&row.DefinitionID,
		&row.VersionID,
		&row.TenantID,
		&row.Visibility,
		&row.Status,
		&row.Metadata,
		&row.CreatedBy,
		&row.UpdatedBy,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to update subagent publication: %w", err)
	}
	return row, nil
}

func (s *SubagentStore) assertSubagentDefinitionExistsTx(ctx context.Context, tx pgx.Tx, definitionID, tenantID string) error {
	var existingID string
	err := tx.QueryRow(ctx, `
		SELECT id
		FROM subagent_definitions
		WHERE id = $1 AND tenant_id = $2 AND status <> 'archived'
	`, definitionID, tenantID).Scan(&existingID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ErrSubagentDefinitionNotFound
		}
		return fmt.Errorf("failed to lookup subagent definition: %w", err)
	}
	return nil
}

func (s *SubagentStore) getCurrentVersionTx(ctx context.Context, tx pgx.Tx, definitionID, tenantID string) (*SubagentDefinitionVersion, error) {
	row := tx.QueryRow(ctx, `
		SELECT
			v.id,
			v.subagent_definition_id,
			v.version_number,
			v.lifecycle_status,
			v.system_prompt,
			COALESCE(v.model, '') AS model,
			v.config,
			v.metadata,
			v.output_schema,
			v.handoff_input_schema,
			v.tool_allowlist,
			v.skill_allowlist,
			v.mcp_allowlist,
			v.knowledge_policy,
			v.review_policy,
			v.runtime_policy,
			COALESCE(p.id::text, '') AS publication_id,
			COALESCE(p.status, '') AS publication_status,
			COALESCE(p.visibility, '') AS publication_scope,
			CASE WHEN p.version_id = v.id THEN true ELSE false END AS is_published,
			v.created_by,
			v.updated_by,
			v.created_at,
			v.updated_at
		FROM subagent_definitions d
		INNER JOIN subagent_publications p
			ON p.subagent_definition_id = d.id
		INNER JOIN subagent_definition_versions v
			ON v.id = p.version_id
		WHERE d.id = $1
		  AND d.tenant_id = $2
		ORDER BY p.updated_at DESC
		LIMIT 1
	`, definitionID, tenantID)
	item, err := scanSubagentVersion(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get current subagent version: %w", err)
	}
	return item, nil
}

func (s *SubagentStore) getPublicationStateTx(ctx context.Context, tx pgx.Tx, definitionID, tenantID string) (*SubagentPublicationState, error) {
	row := tx.QueryRow(ctx, `
		SELECT
			p.id,
			p.subagent_definition_id,
			p.version_id,
			COALESCE(v.version_number, 0) AS version_number,
			COALESCE(p.tenant_id::text, '') AS tenant_id,
			p.visibility,
			p.status,
			p.metadata,
			(
				SELECT COUNT(*)
				FROM agent_subagent_authorizations a
				WHERE a.publication_id = p.id
				  AND a.status = 'enabled'
			) AS authorization_count,
			p.created_by,
			p.updated_by,
			p.created_at,
			p.updated_at,
			p.archived_at
		FROM subagent_publications p
		INNER JOIN subagent_definitions d
			ON d.id = p.subagent_definition_id
		LEFT JOIN subagent_definition_versions v
			ON v.id = p.version_id
		WHERE p.subagent_definition_id = $1
		  AND d.tenant_id = $2
		ORDER BY p.updated_at DESC
		LIMIT 1
	`, definitionID, tenantID)
	item, err := scanSubagentPublicationState(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get subagent publication state: %w", err)
	}
	return item, nil
}

func (s *SubagentStore) disableSubagentAuthorizationsTx(ctx context.Context, tx pgx.Tx, definitionID string) error {
	if _, err := tx.Exec(ctx, `
		UPDATE agent_subagent_authorizations
		SET status = 'disabled'
		WHERE publication_id IN (
			SELECT id
			FROM subagent_publications
			WHERE subagent_definition_id = $1
		)
	`, definitionID); err != nil {
		return fmt.Errorf("failed to disable subagent authorizations: %w", err)
	}
	return nil
}

func (s *SubagentStore) CreateSubagentDefinition(def *SubagentDefinition) (*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	base := &SubagentDefinition{}
	err = tx.QueryRow(ctx, `
		INSERT INTO subagent_definitions (
			tenant_id, name, description, system_prompt, model, status,
			config, metadata, created_by, updated_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
		RETURNING id, tenant_id, name, description, system_prompt, model, status,
		          config, metadata, created_by, updated_by, archived_at, created_at, updated_at
	`,
		def.TenantID,
		def.Name,
		nullIfEmpty(def.Description),
		def.SystemPrompt,
		nullIfEmpty(def.Model),
		defaultSubagentDefinitionStatus(def.DefinitionStatus),
		normalizeJSONRaw(def.Config, `{}`),
		normalizeJSONRaw(def.Metadata, `{}`),
		nullIfPointer(def.CreatedBy),
	).Scan(
		&base.ID,
		&base.TenantID,
		&base.Name,
		&base.Description,
		&base.SystemPrompt,
		&base.Model,
		&base.DefinitionStatus,
		&base.Config,
		&base.Metadata,
		&base.CreatedBy,
		&base.UpdatedBy,
		&base.ArchivedAt,
		&base.CreatedAt,
		&base.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create subagent definition: %w", err)
	}

	version, err := s.insertVersionTx(ctx, tx, &SubagentDefinitionVersion{
		DefinitionID:       base.ID,
		VersionNumber:      1,
		LifecycleStatus:    def.LifecycleStatus,
		SystemPrompt:       def.SystemPrompt,
		Model:              def.Model,
		Config:             def.Config,
		Metadata:           def.Metadata,
		OutputSchema:       def.OutputSchema,
		HandoffInputSchema: def.HandoffInputSchema,
		ToolAllowlist:      def.ToolAllowlist,
		SkillAllowlist:     def.SkillAllowlist,
		MCPAllowlist:       def.MCPAllowlist,
		KnowledgePolicy:    def.KnowledgePolicy,
		ReviewPolicy:       def.ReviewPolicy,
		RuntimePolicy:      def.RuntimePolicy,
		CreatedBy:          def.CreatedBy,
	})
	if err != nil {
		return nil, err
	}

	if _, err := s.upsertPublicationTx(ctx, tx, &SubagentPublication{
		DefinitionID: base.ID,
		VersionID:    version.ID,
		TenantID:     def.createdPublicationTenant(),
		Visibility:   def.PublicationScope,
		Status:       def.Status,
		Metadata:     def.PublicationMetadata,
		CreatedBy:    def.CreatedBy,
	}); err != nil {
		return nil, err
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit managed subagent creation: %w", err)
	}

	return s.GetSubagentDefinition(base.ID, def.TenantID)
}

func (def *SubagentDefinition) createdPublicationTenant() *string {
	scope := defaultSubagentPublicationScope(def.PublicationScope)
	if scope == "system_global" {
		return nil
	}
	if def.PublicationTenantID != "" {
		return &def.PublicationTenantID
	}
	if def.TenantID == "" {
		return nil
	}
	return &def.TenantID
}

func (def *SubagentDefinition) createdPublicationTenantValue() string {
	tenantID := def.createdPublicationTenant()
	if tenantID == nil {
		return ""
	}
	return *tenantID
}

func (s *SubagentStore) UpdateSubagentDefinition(def *SubagentDefinition) (*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if err := s.assertSubagentDefinitionExistsTx(ctx, tx, def.ID, def.TenantID); err != nil {
		return nil, err
	}

	currentVersion, err := s.getCurrentVersionTx(ctx, tx, def.ID, def.TenantID)
	if err != nil {
		return nil, err
	}
	currentPublication, err := s.getPublicationStateTx(ctx, tx, def.ID, def.TenantID)
	if err != nil {
		return nil, err
	}

	err = tx.QueryRow(ctx, `
		UPDATE subagent_definitions
		SET
			name = $3,
			description = $4,
			system_prompt = $5,
			model = $6,
			status = $7,
			config = $8,
			metadata = $9,
			updated_by = $10,
			archived_at = CASE WHEN $7 = 'archived' THEN now() ELSE NULL END
		WHERE id = $1 AND tenant_id = $2
		RETURNING id
	`,
		def.ID,
		def.TenantID,
		def.Name,
		nullIfEmpty(def.Description),
		def.SystemPrompt,
		nullIfEmpty(def.Model),
		defaultSubagentDefinitionStatus(def.DefinitionStatus),
		normalizeJSONRaw(def.Config, `{}`),
		normalizeJSONRaw(def.Metadata, `{}`),
		nullIfPointer(def.UpdatedBy),
	).Scan(&def.ID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSubagentDefinitionNotFound
		}
		return nil, fmt.Errorf("failed to update subagent definition: %w", err)
	}

	publishVersionID := ""
	if currentVersion != nil {
		publishVersionID = currentVersion.ID
	}
	if !versionEquivalent(currentVersion, def) {
		nextVersion, err := s.nextVersionNumberTx(ctx, tx, def.ID)
		if err != nil {
			return nil, err
		}
		version, err := s.insertVersionTx(ctx, tx, &SubagentDefinitionVersion{
			DefinitionID:       def.ID,
			VersionNumber:      nextVersion,
			LifecycleStatus:    def.LifecycleStatus,
			SystemPrompt:       def.SystemPrompt,
			Model:              def.Model,
			Config:             def.Config,
			Metadata:           def.Metadata,
			OutputSchema:       def.OutputSchema,
			HandoffInputSchema: def.HandoffInputSchema,
			ToolAllowlist:      def.ToolAllowlist,
			SkillAllowlist:     def.SkillAllowlist,
			MCPAllowlist:       def.MCPAllowlist,
			KnowledgePolicy:    def.KnowledgePolicy,
			ReviewPolicy:       def.ReviewPolicy,
			RuntimePolicy:      def.RuntimePolicy,
			CreatedBy:          def.UpdatedBy,
		})
		if err != nil {
			return nil, err
		}
		publishVersionID = version.ID
	}
	if publishVersionID == "" {
		return nil, fmt.Errorf("failed to resolve publication version for subagent %s", def.ID)
	}

	if currentPublication == nil || !publicationEquivalent(currentPublication, def, publishVersionID) {
		if _, err := s.upsertPublicationTx(ctx, tx, &SubagentPublication{
			DefinitionID: def.ID,
			VersionID:    publishVersionID,
			TenantID:     def.createdPublicationTenant(),
			Visibility:   def.PublicationScope,
			Status:       def.Status,
			Metadata:     def.PublicationMetadata,
			UpdatedBy:    def.UpdatedBy,
		}); err != nil {
			return nil, err
		}
	}

	if defaultSubagentPublicationStatus(def.Status) == "archived" {
		if err := s.disableSubagentAuthorizationsTx(ctx, tx, def.ID); err != nil {
			return nil, err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit managed subagent update: %w", err)
	}

	return s.GetSubagentDefinition(def.ID, def.TenantID)
}

func (s *SubagentStore) GetSubagentDefinition(id, tenantID string) (*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := managedSubagentSelect + `
		WHERE d.id = $1
		  AND ((p.visibility = 'system_global') OR p.tenant_id = $2)
		ORDER BY p.updated_at DESC
		LIMIT 1
	`
	item, err := scanManagedSubagent(s.pool.QueryRow(ctx, query, id, tenantID))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSubagentDefinitionNotFound
		}
		return nil, fmt.Errorf("failed to get subagent definition: %w", err)
	}
	return item, nil
}

func (s *SubagentStore) ListSubagentDefinitions(tenantID string, includeArchived bool) ([]*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, managedSubagentSelect+`
		WHERE ((p.visibility = 'system_global') OR p.tenant_id = $1)
		  AND ($2 OR p.status <> 'archived')
		ORDER BY d.updated_at DESC, d.name ASC
	`, tenantID, includeArchived)
	if err != nil {
		return nil, fmt.Errorf("failed to list subagent definitions: %w", err)
	}
	defer rows.Close()

	var items []*SubagentDefinition
	for rows.Next() {
		item, err := scanManagedSubagent(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan managed subagent: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SubagentStore) ListPublishedSubagentsByPublicationIDs(tenantID string, publicationIDs []string) ([]*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	normalizedIDs := normalizeStringIDs(publicationIDs)
	if len(normalizedIDs) == 0 {
		return []*SubagentDefinition{}, nil
	}

	rows, err := s.pool.Query(ctx, managedSubagentSelect+`
		WHERE p.id = ANY($1)
		  AND ((p.visibility = 'system_global') OR p.tenant_id = $2)
		  AND p.status <> 'archived'
		ORDER BY d.updated_at DESC, d.name ASC
	`, normalizedIDs, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list subagent publications: %w", err)
	}
	defer rows.Close()

	var items []*SubagentDefinition
	for rows.Next() {
		item, err := scanManagedSubagent(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan subagent publication: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SubagentStore) ListSubagentVersions(definitionID, tenantID string) ([]*SubagentDefinitionVersion, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT
			v.id,
			v.subagent_definition_id,
			v.version_number,
			v.lifecycle_status,
			v.system_prompt,
			COALESCE(v.model, '') AS model,
			v.config,
			v.metadata,
			v.output_schema,
			v.handoff_input_schema,
			v.tool_allowlist,
			v.skill_allowlist,
			v.mcp_allowlist,
			v.knowledge_policy,
			v.review_policy,
			v.runtime_policy,
			COALESCE(p.id::text, '') AS publication_id,
			COALESCE(p.status, '') AS publication_status,
			COALESCE(p.visibility, '') AS publication_scope,
			CASE WHEN p.version_id = v.id THEN true ELSE false END AS is_published,
			v.created_by,
			v.updated_by,
			v.created_at,
			v.updated_at
		FROM subagent_definition_versions v
		INNER JOIN subagent_definitions d
			ON d.id = v.subagent_definition_id
		LEFT JOIN subagent_publications p
			ON p.subagent_definition_id = v.subagent_definition_id
		   AND p.version_id = v.id
		WHERE v.subagent_definition_id = $1
		  AND d.tenant_id = $2
		ORDER BY v.version_number DESC, v.created_at DESC
	`, definitionID, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list subagent versions: %w", err)
	}
	defer rows.Close()

	var items []*SubagentDefinitionVersion
	for rows.Next() {
		item, err := scanSubagentVersion(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan subagent version: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SubagentStore) ListSubagentAuthorizedAgents(definitionID, tenantID string) ([]*SubagentAuthorizedAgent, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT
			a.id,
			a.publication_id,
			a.status,
			a.priority,
			d.id,
			d.name,
			d.status,
			a.budget_policy,
			a.metadata,
			a.created_at,
			a.updated_at
		FROM agent_subagent_authorizations a
		INNER JOIN subagent_publications p
			ON p.id = a.publication_id
		INNER JOIN subagent_definitions s
			ON s.id = p.subagent_definition_id
		INNER JOIN agent_definitions d
			ON d.id = a.agent_definition_id
		WHERE p.subagent_definition_id = $1
		  AND s.tenant_id = $2
		ORDER BY
			CASE WHEN a.status = 'enabled' THEN 0 ELSE 1 END,
			a.priority ASC,
			d.name ASC
	`, definitionID, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list subagent authorizations: %w", err)
	}
	defer rows.Close()

	var items []*SubagentAuthorizedAgent
	for rows.Next() {
		item, err := scanSubagentAuthorizedAgent(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan subagent authorization: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SubagentStore) GetSubagentPublicationState(definitionID, tenantID string) (*SubagentPublicationState, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	item, err := scanSubagentPublicationState(s.pool.QueryRow(ctx, `
		SELECT
			p.id,
			p.subagent_definition_id,
			p.version_id,
			COALESCE(v.version_number, 0) AS version_number,
			COALESCE(p.tenant_id::text, '') AS tenant_id,
			p.visibility,
			p.status,
			p.metadata,
			(
				SELECT COUNT(*)
				FROM agent_subagent_authorizations a
				WHERE a.publication_id = p.id
				  AND a.status = 'enabled'
			) AS authorization_count,
			p.created_by,
			p.updated_by,
			p.created_at,
			p.updated_at,
			p.archived_at
		FROM subagent_publications p
		INNER JOIN subagent_definitions d
			ON d.id = p.subagent_definition_id
		LEFT JOIN subagent_definition_versions v
			ON v.id = p.version_id
		WHERE p.subagent_definition_id = $1
		  AND d.tenant_id = $2
		ORDER BY p.updated_at DESC
		LIMIT 1
	`, definitionID, tenantID))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSubagentPublicationNotFound
		}
		return nil, fmt.Errorf("failed to get subagent publication state: %w", err)
	}
	return item, nil
}

func (s *SubagentStore) GetSubagentControlPlane(definitionID, tenantID string) (*SubagentControlPlane, error) {
	definition, err := s.GetSubagentDefinition(definitionID, tenantID)
	if err != nil {
		return nil, err
	}
	versions, err := s.ListSubagentVersions(definitionID, tenantID)
	if err != nil {
		return nil, err
	}
	publication, err := s.GetSubagentPublicationState(definitionID, tenantID)
	if err != nil && !errors.Is(err, ErrSubagentPublicationNotFound) {
		return nil, err
	}
	authorizations, err := s.ListSubagentAuthorizedAgents(definitionID, tenantID)
	if err != nil {
		return nil, err
	}
	events, err := s.ListSubagentPublicationEvents(definitionID, tenantID, 12)
	if err != nil {
		return nil, err
	}
	return &SubagentControlPlane{
		Definition:     definition,
		Versions:       versions,
		Publication:    publication,
		Authorizations: authorizations,
		Events:         events,
	}, nil
}

func (s *SubagentStore) ListSubagentPublicationEvents(definitionID, tenantID string, limit int) ([]*SubagentPublicationEvent, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if limit <= 0 {
		limit = 20
	}

	rows, err := s.pool.Query(ctx, `
		SELECT
			e.id,
			e.tenant_id,
			e.subagent_definition_id,
			d.name AS subagent_definition_name,
			d.status AS subagent_definition_status,
			COALESCE(e.publication_id::text, '') AS publication_id,
			e.event_stage,
			e.action_type,
			e.change_type,
			e.risk_level,
			e.requires_confirmation,
			e.confirmed,
			COALESCE(e.version_id::text, '') AS version_id,
			e.version_number,
			COALESCE(e.previous_version_id::text, '') AS previous_version_id,
			e.previous_version_number,
			e.publication_scope,
			e.previous_publication_scope,
			e.status,
			e.previous_status,
			e.impacted_authorization_count,
			e.enabled_authorization_count,
			e.inactive_authorization_count,
			e.compatibility_mode,
			e.summary,
			e.change_reason,
			e.change_notes,
			e.rollback_recovery_plan,
			e.recommended_actions,
			e.affected_agents,
			e.metadata,
			e.actor_user_id,
			COALESCE(u.email, '') AS actor_user_email,
			e.created_at
		FROM subagent_publication_events e
		INNER JOIN subagent_definitions d
			ON d.id = e.subagent_definition_id
		LEFT JOIN users u
			ON u.id = e.actor_user_id
		WHERE e.subagent_definition_id = $1
		  AND d.tenant_id = $2
		ORDER BY e.created_at DESC
		LIMIT $3
	`, definitionID, tenantID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list subagent publication events: %w", err)
	}
	defer rows.Close()

	items := make([]*SubagentPublicationEvent, 0, limit)
	for rows.Next() {
		item, err := scanSubagentPublicationEvent(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan subagent publication event: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SubagentStore) ListTenantSubagentPublicationEvents(tenantID string, filters *SubagentPublicationEventFilters) (*SubagentPublicationEventPage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	normalized := normalizeSubagentPublicationEventFilters(filters)
	whereClauses := []string{"e.tenant_id = $1"}
	args := []any{tenantID}
	addStringFilter := func(column, value string) {
		if strings.TrimSpace(value) == "" {
			return
		}
		args = append(args, strings.TrimSpace(value))
		whereClauses = append(whereClauses, fmt.Sprintf("%s = $%d", column, len(args)))
	}
	addStringFilter("e.subagent_definition_id::text", normalized.DefinitionID)
	addStringFilter("e.action_type", normalized.ActionType)
	addStringFilter("e.event_stage", normalized.EventStage)
	addStringFilter("e.change_type", normalized.ChangeType)
	addStringFilter("e.risk_level", normalized.RiskLevel)
	if strings.TrimSpace(normalized.CompatibilityMode) != "" {
		args = append(args, strings.EqualFold(normalized.CompatibilityMode, "true"))
		whereClauses = append(whereClauses, fmt.Sprintf("e.compatibility_mode = $%d", len(args)))
	}
	whereSQL := strings.Join(whereClauses, " AND ")

	countQuery := fmt.Sprintf(`
		SELECT COUNT(*)
		FROM subagent_publication_events e
		INNER JOIN subagent_definitions d
			ON d.id = e.subagent_definition_id
		WHERE %s
		  AND d.tenant_id = $1
	`, whereSQL)
	var total int
	if err := s.pool.QueryRow(ctx, countQuery, args...).Scan(&total); err != nil {
		return nil, fmt.Errorf("failed to count tenant subagent publication events: %w", err)
	}

	queryArgs := append([]any{}, args...)
	queryArgs = append(queryArgs, normalized.Limit, normalized.Offset)
	limitPosition := len(queryArgs) - 1
	offsetPosition := len(queryArgs)
	query := fmt.Sprintf(`
		SELECT
			e.id,
			e.tenant_id,
			e.subagent_definition_id,
			d.name AS subagent_definition_name,
			d.status AS subagent_definition_status,
			COALESCE(e.publication_id::text, '') AS publication_id,
			e.event_stage,
			e.action_type,
			e.change_type,
			e.risk_level,
			e.requires_confirmation,
			e.confirmed,
			COALESCE(e.version_id::text, '') AS version_id,
			e.version_number,
			COALESCE(e.previous_version_id::text, '') AS previous_version_id,
			e.previous_version_number,
			e.publication_scope,
			e.previous_publication_scope,
			e.status,
			e.previous_status,
			e.impacted_authorization_count,
			e.enabled_authorization_count,
			e.inactive_authorization_count,
			e.compatibility_mode,
			e.summary,
			e.change_reason,
			e.change_notes,
			e.rollback_recovery_plan,
			e.recommended_actions,
			e.affected_agents,
			e.metadata,
			e.actor_user_id,
			COALESCE(u.email, '') AS actor_user_email,
			e.created_at
		FROM subagent_publication_events e
		INNER JOIN subagent_definitions d
			ON d.id = e.subagent_definition_id
		LEFT JOIN users u
			ON u.id = e.actor_user_id
		WHERE %s
		  AND d.tenant_id = $1
		ORDER BY e.created_at DESC
		LIMIT $%d OFFSET $%d
	`, whereSQL, limitPosition, offsetPosition)

	rows, err := s.pool.Query(ctx, query, queryArgs...)
	if err != nil {
		return nil, fmt.Errorf("failed to list tenant subagent publication events: %w", err)
	}
	defer rows.Close()

	items := make([]*SubagentPublicationEvent, 0, normalized.Limit)
	for rows.Next() {
		item, err := scanSubagentPublicationEvent(rows)
		if err != nil {
			return nil, fmt.Errorf("failed to scan tenant subagent publication event: %w", err)
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return &SubagentPublicationEventPage{
		Items:   items,
		Total:   total,
		Filters: normalized,
	}, nil
}

func normalizeSubagentPublicationEventFilters(filters *SubagentPublicationEventFilters) *SubagentPublicationEventFilters {
	normalized := &SubagentPublicationEventFilters{}
	if filters != nil {
		normalized.DefinitionID = strings.TrimSpace(filters.DefinitionID)
		normalized.ActionType = strings.TrimSpace(filters.ActionType)
		normalized.EventStage = strings.TrimSpace(filters.EventStage)
		normalized.ChangeType = strings.TrimSpace(filters.ChangeType)
		normalized.RiskLevel = strings.TrimSpace(filters.RiskLevel)
		compatibilityMode := strings.ToLower(strings.TrimSpace(filters.CompatibilityMode))
		if compatibilityMode == "true" || compatibilityMode == "false" {
			normalized.CompatibilityMode = compatibilityMode
		}
		normalized.Limit = filters.Limit
		normalized.Offset = filters.Offset
	}
	if normalized.Limit <= 0 {
		normalized.Limit = 20
	}
	if normalized.Limit > 100 {
		normalized.Limit = 100
	}
	if normalized.Offset < 0 {
		normalized.Offset = 0
	}
	return normalized
}

func (s *SubagentStore) AppendSubagentPublicationEvent(event *SubagentPublicationEvent) (*SubagentPublicationEvent, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := s.pool.QueryRow(ctx, `
		INSERT INTO subagent_publication_events (
			tenant_id,
			subagent_definition_id,
			publication_id,
			event_stage,
			action_type,
			change_type,
			risk_level,
			requires_confirmation,
			confirmed,
			version_id,
			version_number,
			previous_version_id,
			previous_version_number,
			publication_scope,
			previous_publication_scope,
			status,
			previous_status,
			impacted_authorization_count,
			enabled_authorization_count,
			inactive_authorization_count,
			compatibility_mode,
			summary,
			change_reason,
			change_notes,
			rollback_recovery_plan,
			recommended_actions,
			affected_agents,
			metadata,
			actor_user_id
		)
		VALUES (
			$1, $2, NULLIF($3, '')::uuid, $4, $5, $6, $7, $8, $9,
			NULLIF($10, '')::uuid, $11, NULLIF($12, '')::uuid, $13, $14, $15, $16, $17,
			$18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, NULLIF($29, '')::uuid
		)
		RETURNING
			id,
			tenant_id,
			subagent_definition_id,
			'' AS subagent_definition_name,
			'' AS subagent_definition_status,
			COALESCE(publication_id::text, '') AS publication_id,
			event_stage,
			action_type,
			change_type,
			risk_level,
			requires_confirmation,
			confirmed,
			COALESCE(version_id::text, '') AS version_id,
			version_number,
			COALESCE(previous_version_id::text, '') AS previous_version_id,
			previous_version_number,
			publication_scope,
			previous_publication_scope,
			status,
			previous_status,
			impacted_authorization_count,
			enabled_authorization_count,
			inactive_authorization_count,
			compatibility_mode,
			summary,
			change_reason,
			change_notes,
			rollback_recovery_plan,
			recommended_actions,
			affected_agents,
			metadata,
			actor_user_id,
			'' AS actor_user_email,
			created_at
	`,
		event.TenantID,
		event.DefinitionID,
		event.PublicationID,
		event.EventStage,
		event.ActionType,
		event.ChangeType,
		event.RiskLevel,
		event.RequiresConfirmation,
		event.Confirmed,
		event.VersionID,
		event.VersionNumber,
		event.PreviousVersionID,
		event.PreviousVersionNumber,
		defaultSubagentPublicationScope(event.PublicationScope),
		defaultSubagentPublicationScope(event.PreviousPublicationScope),
		defaultSubagentPublicationStatus(event.Status),
		defaultSubagentPublicationStatus(event.PreviousStatus),
		event.ImpactedAuthorizationCount,
		event.EnabledAuthorizationCount,
		event.InactiveAuthorizationCount,
		event.CompatibilityMode,
		event.Summary,
		event.ChangeReason,
		event.ChangeNotes,
		event.RollbackRecoveryPlan,
		NormalizeJSONRawForExport(event.RecommendedActions, `[]`),
		NormalizeJSONRawForExport(event.AffectedAgents, `[]`),
		NormalizeJSONRawForExport(event.Metadata, `{}`),
		stringValueOrEmpty(event.ActorUserID),
	)
	item, err := scanSubagentPublicationEvent(row)
	if err != nil {
		return nil, fmt.Errorf("failed to append subagent publication event: %w", err)
	}
	return item, nil
}

func (s *SubagentStore) CreateSubagentVersion(
	definitionID,
	tenantID string,
	version *SubagentDefinitionVersion,
	publication *SubagentPublication,
	publish bool,
) (*SubagentDefinitionVersion, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if err := s.assertSubagentDefinitionExistsTx(ctx, tx, definitionID, tenantID); err != nil {
		return nil, err
	}
	nextVersion, err := s.nextVersionNumberTx(ctx, tx, definitionID)
	if err != nil {
		return nil, err
	}
	created, err := s.insertVersionTx(ctx, tx, &SubagentDefinitionVersion{
		DefinitionID:       definitionID,
		VersionNumber:      nextVersion,
		LifecycleStatus:    version.LifecycleStatus,
		SystemPrompt:       version.SystemPrompt,
		Model:              version.Model,
		Config:             version.Config,
		Metadata:           version.Metadata,
		OutputSchema:       version.OutputSchema,
		HandoffInputSchema: version.HandoffInputSchema,
		ToolAllowlist:      version.ToolAllowlist,
		SkillAllowlist:     version.SkillAllowlist,
		MCPAllowlist:       version.MCPAllowlist,
		KnowledgePolicy:    version.KnowledgePolicy,
		ReviewPolicy:       version.ReviewPolicy,
		RuntimePolicy:      version.RuntimePolicy,
		CreatedBy:          version.CreatedBy,
		UpdatedBy:          version.UpdatedBy,
	})
	if err != nil {
		return nil, err
	}

	if publish {
		if _, err := s.upsertPublicationTx(ctx, tx, &SubagentPublication{
			DefinitionID: definitionID,
			VersionID:    created.ID,
			TenantID:     publication.TenantID,
			Visibility:   publication.Visibility,
			Status:       publication.Status,
			Metadata:     publication.Metadata,
			CreatedBy:    version.CreatedBy,
			UpdatedBy:    version.UpdatedBy,
		}); err != nil {
			return nil, err
		}
		created.IsPublished = true
		created.PublicationStatus = defaultSubagentPublicationStatus(publication.Status)
		created.PublicationScope = defaultSubagentPublicationScope(publication.Visibility)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit subagent version creation: %w", err)
	}

	return created, nil
}

func (s *SubagentStore) UpdateSubagentPublication(
	definitionID,
	tenantID string,
	publication *SubagentPublication,
) (*SubagentPublicationState, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if err := s.assertSubagentDefinitionExistsTx(ctx, tx, definitionID, tenantID); err != nil {
		return nil, err
	}

	var versionExists bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM subagent_definition_versions
			WHERE id = $1
			  AND subagent_definition_id = $2
		)
	`, publication.VersionID, definitionID).Scan(&versionExists); err != nil {
		return nil, fmt.Errorf("failed to validate subagent publication version: %w", err)
	}
	if !versionExists {
		return nil, ErrSubagentPublicationNotFound
	}

	if _, err := s.upsertPublicationTx(ctx, tx, publication); err != nil {
		return nil, err
	}

	if defaultSubagentPublicationStatus(publication.Status) == "archived" {
		if err := s.disableSubagentAuthorizationsTx(ctx, tx, definitionID); err != nil {
			return nil, err
		}
	}

	item, err := s.getPublicationStateTx(ctx, tx, definitionID, tenantID)
	if err != nil {
		return nil, err
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit subagent publication update: %w", err)
	}

	return item, nil
}

func (s *SubagentStore) DeleteSubagentDefinition(id, tenantID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	result, err := tx.Exec(ctx, `
		UPDATE subagent_definitions
		SET
			status = 'archived',
			archived_at = now()
		WHERE id = $1 AND tenant_id = $2
	`, id, tenantID)
	if err != nil {
		return fmt.Errorf("failed to archive subagent definition: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrSubagentDefinitionNotFound
	}

	if _, err := tx.Exec(ctx, `
		UPDATE subagent_publications
		SET
			status = 'archived',
			archived_at = now()
		WHERE subagent_definition_id = $1
	`, id); err != nil {
		return fmt.Errorf("failed to archive subagent publications: %w", err)
	}

	if _, err := tx.Exec(ctx, `
		UPDATE agent_subagent_authorizations
		SET status = 'disabled'
		WHERE publication_id IN (
			SELECT id
			FROM subagent_publications
			WHERE subagent_definition_id = $1
		)
	`, id); err != nil {
		return fmt.Errorf("failed to disable subagent authorizations: %w", err)
	}

	return tx.Commit(ctx)
}

func (s *SubagentStore) ReplaceAgentSubagentAuthorizations(agentID string, publicationIDs []string, updatedBy *string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	normalizedIDs := normalizeStringIDs(publicationIDs)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `
		DELETE FROM agent_subagent_authorizations
		WHERE agent_definition_id = $1
	`, agentID); err != nil {
		return fmt.Errorf("failed to clear agent subagent authorizations: %w", err)
	}

	for _, publicationID := range normalizedIDs {
		if _, err := tx.Exec(ctx, `
			INSERT INTO agent_subagent_authorizations (
				agent_definition_id, publication_id, status, priority, budget_policy, metadata, created_by, updated_by
			)
			VALUES ($1, $2, 'enabled', 100, '{}'::jsonb, '{}'::jsonb, $3, $3)
		`, agentID, publicationID, nullIfPointer(updatedBy)); err != nil {
			return fmt.Errorf("failed to authorize subagent publication %s: %w", publicationID, err)
		}
	}

	return tx.Commit(ctx)
}

func (s *SubagentStore) ListAgentSubagentAuthorizationPublicationIDs(agentID string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT publication_id
		FROM agent_subagent_authorizations
		WHERE agent_definition_id = $1
		  AND status = 'enabled'
		ORDER BY created_at ASC
	`, agentID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent subagent authorizations: %w", err)
	}
	defer rows.Close()

	var publicationIDs []string
	for rows.Next() {
		var publicationID string
		if err := rows.Scan(&publicationID); err != nil {
			return nil, fmt.Errorf("failed to scan agent subagent authorization: %w", err)
		}
		publicationIDs = append(publicationIDs, publicationID)
	}
	return publicationIDs, rows.Err()
}

func (s *SubagentStore) CanonicalizeSubagentMetadataAliases(definitionIDs []string, tenantID string, updatedBy *string) ([]*SubagentMetadataAliasFreezeResult, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	normalizedIDs := normalizeStringIDs(definitionIDs)
	if len(normalizedIDs) == 0 {
		return []*SubagentMetadataAliasFreezeResult{}, nil
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	rows, err := tx.Query(ctx, `
		SELECT id, metadata
		FROM subagent_definitions
		WHERE tenant_id = $1
		  AND status <> 'archived'
		  AND id = ANY($2)
		FOR UPDATE
	`, tenantID, normalizedIDs)
	if err != nil {
		return nil, fmt.Errorf("failed to load subagent definitions for metadata alias freeze: %w", err)
	}
	defer rows.Close()

	found := make(map[string]json.RawMessage, len(normalizedIDs))
	for rows.Next() {
		var definitionID string
		var metadata json.RawMessage
		if err := rows.Scan(&definitionID, &metadata); err != nil {
			return nil, fmt.Errorf("failed to scan subagent metadata candidate: %w", err)
		}
		found[definitionID] = metadata
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("failed to iterate subagent metadata candidates: %w", err)
	}

	results := make([]*SubagentMetadataAliasFreezeResult, 0, len(normalizedIDs))
	for _, definitionID := range normalizedIDs {
		raw, ok := found[definitionID]
		if !ok {
			return nil, ErrSubagentDefinitionNotFound
		}
		metadata, hostAgentDefinitionID, legacyAliasKey, legacyAliasValue, changed, err := normalizeSubagentMetadataAliases(raw)
		if err != nil {
			return nil, err
		}
		if !changed {
			continue
		}
		if _, err := tx.Exec(ctx, `
			UPDATE subagent_definitions
			SET
				metadata = $3,
				updated_by = $4,
				updated_at = now()
			WHERE id = $1 AND tenant_id = $2
		`, definitionID, tenantID, metadata, nullIfPointer(updatedBy)); err != nil {
			return nil, fmt.Errorf("failed to canonicalize subagent metadata aliases for %s: %w", definitionID, err)
		}
		results = append(results, &SubagentMetadataAliasFreezeResult{
			DefinitionID:          definitionID,
			Metadata:              metadata,
			HostAgentDefinitionID: hostAgentDefinitionID,
			LegacyAliasKey:        legacyAliasKey,
			LegacyAliasValue:      legacyAliasValue,
		})
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit metadata alias freeze: %w", err)
	}
	return results, nil
}
