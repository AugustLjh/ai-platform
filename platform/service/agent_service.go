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

type AgentService struct {
	aiClient           *grpc.AIClient
	agentStore         *database.AgentStore
	sessionStore       *database.SessionStore
	skillStore         *database.SkillStore
	mcpStore           *database.MCPStore
	skillsRoot         string
	systemSkillsSynced bool
}

func NewAgentService(
	aiClient *grpc.AIClient,
	agentStore *database.AgentStore,
	sessionStore *database.SessionStore,
	skillStore *database.SkillStore,
	mcpStore *database.MCPStore,
) *AgentService {
	return &AgentService{
		aiClient:     aiClient,
		agentStore:   agentStore,
		sessionStore: sessionStore,
		skillStore:   skillStore,
		mcpStore:     mcpStore,
		skillsRoot:   resolveSkillsRoot(),
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
	return s.skillStore.ListSkills(tenantID)
}

func (s *AgentService) GetSkill(tenantID, skillID string) (*database.Skill, error) {
	if err := s.ensureSystemSkillsSynced(); err != nil {
		return nil, err
	}
	return s.skillStore.GetSkill(skillID, tenantID)
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
	return s.hydrateMCPServer(created)
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
	return s.hydrateMCPServer(updated)
}

func (s *AgentService) GetMCPServer(tenantID, serverID string) (*database.MCPServer, error) {
	server, err := s.mcpStore.GetServer(serverID, tenantID)
	if err != nil {
		return nil, err
	}
	return s.hydrateMCPServer(server)
}

func (s *AgentService) DeleteMCPServer(tenantID, serverID string) error {
	return s.mcpStore.DeleteServer(serverID, tenantID)
}

func (s *AgentService) TestMCPServer(ctx context.Context, tenantID, serverID string) (*MCPServerTestResponse, error) {
	if _, err := s.mcpStore.GetServer(serverID, tenantID); err != nil {
		return nil, err
	}
	result, err := s.aiClient.TestMCPServer(ctx, tenantID, serverID)
	if err != nil {
		return nil, err
	}
	server, err := s.GetMCPServer(tenantID, serverID)
	if err != nil {
		return nil, err
	}
	return &MCPServerTestResponse{
		Result:       maskSensitiveObject(result, false),
		Server:       server,
		Connection:   server.Connection,
		Catalog:      server.Catalog,
		Availability: server.Availability,
	}, nil
}

func (s *AgentService) RefreshMCPServerTools(tenantID, serverID string) (*MCPServerRefreshResponse, error) {
	if _, err := s.mcpStore.GetServer(serverID, tenantID); err != nil {
		return nil, err
	}
	items, err := s.aiClient.RefreshMCPServerTools(context.Background(), tenantID, serverID)
	if err != nil {
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
	return &MCPServerRefreshResponse{
		Tools:        items,
		Total:        len(items),
		Server:       server,
		Connection:   server.Connection,
		Catalog:      server.Catalog,
		Availability: server.Availability,
	}, nil
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

	return &database.Skill{
		Name:          name,
		Slug:          slug,
		Version:       version,
		Description:   description,
		RootPath:      path,
		SystemPrompt:  string(systemPrompt),
		OutputSchema:  outputSchema,
		ToolAllowlist: toolAllowlist,
		Metadata:      metadata,
	}, nil
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
