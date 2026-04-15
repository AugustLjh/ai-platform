package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
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
)

var systemSkillSlugs = []string{
	"implementation-planner",
	"engineering",
}

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
	VersionID           string          `json:"version_id"`
	PublicationScope    string          `json:"publication_scope"`
	Status              string          `json:"status"`
	PublicationMetadata json.RawMessage `json:"publication_metadata"`
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

type MCPServerBulkActionRequest struct {
	ServerIDs    []string `json:"server_ids"`
	Action       string   `json:"action"`
	GroupBy      string   `json:"group_by,omitempty"`
	MaxBatchSize int      `json:"max_batch_size,omitempty"`
	RetryFailed  int      `json:"retry_failed,omitempty"`
}

type MCPServerBulkActionResult struct {
	ServerID string              `json:"server_id"`
	Action   string              `json:"action"`
	OK       bool                `json:"ok"`
	Message  string              `json:"message"`
	Server   *database.MCPServer `json:"server,omitempty"`
	Attempts int                 `json:"attempts,omitempty"`
	GroupKey string              `json:"group_key,omitempty"`
}

type MCPServerBulkActionExecution struct {
	GroupBy       string `json:"group_by"`
	MaxBatchSize  int    `json:"max_batch_size"`
	RetryFailed   int    `json:"retry_failed"`
	SelectedCount int    `json:"selected_count"`
	GroupCount    int    `json:"group_count"`
}

type MCPServerBulkActionGroup struct {
	Key     string                       `json:"key"`
	Label   string                       `json:"label"`
	Total   int                          `json:"total"`
	Success int                          `json:"success"`
	Failed  int                          `json:"failed"`
	Results []*MCPServerBulkActionResult `json:"results"`
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

func (s *AgentService) ListAvailableTools(ctx context.Context, tenantID, agentDefinitionID string) ([]*AgentToolSpec, error) {
	items, err := s.aiClient.ListAgentTools(ctx, tenantID, agentDefinitionID)
	if err != nil {
		return nil, err
	}

	result := make([]*AgentToolSpec, 0, len(items))
	for _, item := range items {
		spec := item
		result = append(result, &AgentToolSpec{
			Name:        spec.Name,
			Description: spec.Description,
			InputSchema: spec.InputSchema,
			Kind:        spec.Kind,
			Metadata:    spec.Metadata,
		})
	}
	return result, nil
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
	return s.skillStore.ReplaceAgentSkillBindings(agentID, mergeFixedSkillIDs(req.SkillIDs, fixedSkillIDs))
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

	groupedServerIDs := map[string][]string{}
	groupOrder := make([]string, 0)
	for _, serverID := range serverIDs {
		server, err := s.GetMCPServer(tenantID, serverID)
		if err != nil {
			return nil, err
		}
		groupKey := buildMCPBulkGroupKey(server, groupBy)
		if _, exists := groupedServerIDs[groupKey]; !exists {
			groupOrder = append(groupOrder, groupKey)
		}
		groupedServerIDs[groupKey] = append(groupedServerIDs[groupKey], serverID)
	}

	results := make([]*MCPServerBulkActionResult, 0, len(serverIDs))
	groups := make([]*MCPServerBulkActionGroup, 0, len(groupOrder))
	success := 0
	failed := 0

	for _, groupKey := range groupOrder {
		groupServerIDs := groupedServerIDs[groupKey]
		group := &MCPServerBulkActionGroup{
			Key:     groupKey,
			Label:   buildMCPBulkGroupLabel(groupKey, groupBy),
			Results: make([]*MCPServerBulkActionResult, 0, len(groupServerIDs)),
		}
		for start := 0; start < len(groupServerIDs); start += maxBatchSize {
			end := start + maxBatchSize
			if end > len(groupServerIDs) {
				end = len(groupServerIDs)
			}
			batch := groupServerIDs[start:end]
			for _, serverID := range batch {
				result := s.runSingleMCPBulkAction(tenantID, userID, action, serverID)
				result.GroupKey = groupKey
				for attempt := 0; !result.OK && attempt < retryFailed; attempt++ {
					result = s.runSingleMCPBulkAction(tenantID, userID, action, serverID)
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
		},
		Groups: groups,
	}, nil
}

func (s *AgentService) runSingleMCPBulkAction(tenantID, userID, action, serverID string) *MCPServerBulkActionResult {
	result := &MCPServerBulkActionResult{
		ServerID: serverID,
		Action:   action,
	}

	switch action {
	case "test":
		response, err := s.TestMCPServer(context.Background(), tenantID, serverID, userID)
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			return result
		}
		result.OK = true
		if response.Connection != nil && strings.TrimSpace(response.Connection.Summary) != "" {
			result.Message = response.Connection.Summary
		} else {
			result.Message = "连接测试已完成"
		}
		result.Server = response.Server
	case "refresh":
		response, err := s.RefreshMCPServerTools(tenantID, serverID, userID)
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			return result
		}
		result.OK = true
		result.Message = fmt.Sprintf("已刷新 %d 个工具", response.Total)
		result.Server = response.Server
	case "enable":
		server, err := s.GetMCPServer(tenantID, serverID)
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			return result
		}
		updated, err := s.UpdateMCPServer(tenantID, userID, serverID, &MCPServerUpsertRequest{
			Name:      server.Name,
			Transport: server.Transport,
			Endpoint:  server.Endpoint,
			Command:   server.Command,
			Args:      server.Args,
			Env:       server.Env,
			Metadata:  server.Metadata,
			Status:    "active",
		})
		if err != nil {
			result.OK = false
			result.Message = err.Error()
			return result
		}
		event, _ := s.recordMCPServerEvent(tenantID, userID, updated, "server.updated", "enable", "succeeded", "server_enabled", "MCP server 已重新启用。")
		updated = prependMCPServerEvent(updated, event)
		result.OK = true
		result.Message = "已重新启用"
		result.Server = updated
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

func buildMCPBulkGroupLabel(groupKey, groupBy string) string {
	switch groupBy {
	case "status":
		return fmt.Sprintf("按状态分组: %s", groupKey)
	case "transport":
		return fmt.Sprintf("按 transport 分组: %s", groupKey)
	case "failure_mode":
		return fmt.Sprintf("按故障模式分组: %s", groupKey)
	default:
		return "全部选中服务器"
	}
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
	controlPlane.Governance = buildSubagentGovernanceSummary(controlPlane)
	return controlPlane, nil
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

	publication := &database.SubagentPublication{
		DefinitionID: subagentID,
		VersionID:    versionID,
		TenantID:     subagentPublicationTenant(definition),
		Visibility:   defaultString(strings.TrimSpace(req.PublicationScope), definition.PublicationScope),
		Status:       defaultString(strings.TrimSpace(req.Status), definition.Status),
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
	return s.GetSubagentControlPlane(tenantID, userRole, subagentID)
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
		hostAgentID = strings.TrimSpace(controlPlane.Definition.TargetAgentDefinitionID)
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

	legacyDefinitionIDs := make([]string, 0, len(publicationIDs))
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
		if strings.TrimSpace(hydrated.TargetAgentDefinitionID) != "" && hydrated.TargetAgentDefinitionID == agentID {
			return fmt.Errorf("subagent publication %s cannot delegate back to the same agent definition", publicationID)
		}
		if strings.TrimSpace(hydrated.TargetAgentDefinitionID) != "" {
			legacyDefinitionIDs = append(legacyDefinitionIDs, hydrated.ID)
		}
	}

	if err := s.subagentStore.ReplaceAgentSubagentAuthorizations(agentID, publicationIDs, stringPtr(userID)); err != nil {
		return err
	}
	return s.subagentStore.ReplaceAgentSubagentBindings(agentID, tenantID, legacyDefinitionIDs)
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
		if _, err := s.skillStore.UpsertSkill(skill); err != nil {
			return err
		}
	}
	s.systemSkillsSynced = true
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

func buildSubagentGovernanceSummary(controlPlane *database.SubagentControlPlane) *database.SubagentGovernanceSummary {
	if controlPlane == nil {
		return nil
	}

	summary := &database.SubagentGovernanceSummary{
		Warnings: []*database.SubagentGovernanceWarning{},
	}
	if controlPlane.Definition != nil {
		summary.HostAgentDefinitionID = strings.TrimSpace(controlPlane.Definition.HostAgentDefinitionID)
		summary.CompatibilityMode = summary.HostAgentDefinitionID != ""
	}
	if len(controlPlane.Versions) > 0 && controlPlane.Versions[0] != nil {
		summary.LatestVersionNumber = controlPlane.Versions[0].VersionNumber
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

	if summary.CompatibilityMode {
		summary.Warnings = appendSubagentGovernanceWarning(
			summary.Warnings,
			"compatibility-host-override",
			"warning",
			"当前 capability 仍显式绑定宿主 agent，属于兼容模式；后续应优先收口到 publication/version/authorization 语义。",
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
	return summary
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
	def.TargetAgentDefinitionID = hostAgentDefinitionID
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
	definition.TargetAgentDefinitionID = hostAgentDefinitionID
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
		return typed
	default:
		return value
	}
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
