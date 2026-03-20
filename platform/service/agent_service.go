package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/ai-platform/platform/api/grpc"
	"github.com/ai-platform/platform/database"
)

var ErrAgentUnauthorized = errors.New("unauthorized")
var ErrNotImplemented = errors.New("not implemented")

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

type AgentService struct {
	aiClient   *grpc.AIClient
	agentStore *database.AgentStore
	skillStore *database.SkillStore
	mcpStore   *database.MCPStore
	skillsRoot string
}

func NewAgentService(
	aiClient *grpc.AIClient,
	agentStore *database.AgentStore,
	skillStore *database.SkillStore,
	mcpStore *database.MCPStore,
) *AgentService {
	return &AgentService{
		aiClient:   aiClient,
		agentStore: agentStore,
		skillStore: skillStore,
		mcpStore:   mcpStore,
		skillsRoot: filepath.Join("/mnt/ai-platform", "ai_runtime", "skills"),
	}
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
	return s.agentStore.CreateAgentDefinition(def)
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
	return s.agentStore.UpdateAgentDefinition(current)
}

func (s *AgentService) GetAgentDefinition(tenantID, agentID string) (*database.AgentDefinition, error) {
	return s.agentStore.GetAgentDefinition(agentID, tenantID)
}

func (s *AgentService) ListAgentDefinitions(tenantID string, includeArchived bool) ([]*database.AgentDefinition, error) {
	return s.agentStore.ListAgentDefinitions(tenantID, includeArchived)
}

func (s *AgentService) ArchiveAgentDefinition(tenantID, userID, agentID string) error {
	return s.agentStore.ArchiveAgentDefinition(agentID, tenantID, userID)
}

func (s *AgentService) CreateRun(ctx context.Context, tenantID, userID, agentID string, req *CreateAgentRunRequest) (*database.AgentRun, error) {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
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
		SessionID:         req.SessionID,
		Input:             req.Input,
		Metadata:          req.Metadata,
		AutoStart:         autoStart,
	})
	if err != nil {
		return nil, err
	}
	return run, nil
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

func (s *AgentService) ListSkills(tenantID string) ([]*database.Skill, error) {
	return s.skillStore.ListSkills(tenantID)
}

func (s *AgentService) GetSkill(tenantID, skillID string) (*database.Skill, error) {
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
	return synced, nil
}

func (s *AgentService) UpdateAgentSkills(tenantID, agentID string, req *UpdateAgentSkillsRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	return s.skillStore.ReplaceAgentSkillBindings(agentID, req.SkillIDs)
}

func (s *AgentService) ListMCPServers(tenantID string) ([]*database.MCPServer, error) {
	return s.mcpStore.ListServers(tenantID)
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
	return s.mcpStore.CreateServer(server)
}

func (s *AgentService) UpdateMCPServer(tenantID, userID, serverID string, req *MCPServerUpsertRequest) (*database.MCPServer, error) {
	server := &database.MCPServer{
		ID:        serverID,
		TenantID:  tenantID,
		Name:      strings.TrimSpace(req.Name),
		Transport: strings.TrimSpace(req.Transport),
		Endpoint:  strings.TrimSpace(req.Endpoint),
		Command:   strings.TrimSpace(req.Command),
		Args:      database.NormalizeJSONRawForExport(req.Args, `[]`),
		Env:       database.NormalizeJSONRawForExport(req.Env, `{}`),
		Status:    defaultString(strings.TrimSpace(req.Status), "active"),
		Metadata:  database.NormalizeJSONRawForExport(req.Metadata, `{}`),
		UpdatedBy: stringPtr(userID),
	}
	return s.mcpStore.UpdateServer(server)
}

func (s *AgentService) GetMCPServer(tenantID, serverID string) (*database.MCPServer, error) {
	return s.mcpStore.GetServer(serverID, tenantID)
}

func (s *AgentService) DeleteMCPServer(tenantID, serverID string) error {
	return s.mcpStore.DeleteServer(serverID, tenantID)
}

func (s *AgentService) TestMCPServer(ctx context.Context, tenantID, serverID string) (map[string]any, error) {
	server, err := s.mcpStore.GetServer(serverID, tenantID)
	if err != nil {
		return nil, err
	}

	result := map[string]any{
		"server_id": server.ID,
		"transport": server.Transport,
		"ok":        true,
	}

	if server.Transport == "http" || server.Transport == "sse" {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, server.Endpoint, nil)
		if err != nil {
			return nil, err
		}
		client := &http.Client{Timeout: 5 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			result["ok"] = false
			result["error"] = err.Error()
			return result, nil
		}
		resp.Body.Close()
		result["status_code"] = resp.StatusCode
		result["ok"] = resp.StatusCode < 500
		return result, nil
	}

	if server.Transport == "stdio" && server.Command == "" {
		result["ok"] = false
		result["error"] = "stdio transport requires command"
	}

	return result, nil
}

func (s *AgentService) RefreshMCPServerTools(tenantID, serverID string) ([]*database.MCPServerTool, error) {
	if _, err := s.mcpStore.GetServer(serverID, tenantID); err != nil {
		return nil, err
	}
	return nil, fmt.Errorf("mcp tool refresh is not implemented yet: %w", ErrNotImplemented)
}

func (s *AgentService) UpdateAgentMCPServers(tenantID, agentID string, req *UpdateAgentMCPServersRequest) error {
	if _, err := s.agentStore.GetAgentDefinition(agentID, tenantID); err != nil {
		return err
	}
	return s.mcpStore.ReplaceAgentMCPBindings(agentID, req.ServerIDs)
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

	return &database.Skill{
		Name:          name,
		Slug:          slug,
		Version:       version,
		Description:   description,
		RootPath:      path,
		SystemPrompt:  string(systemPrompt),
		OutputSchema:  outputSchema,
		ToolAllowlist: json.RawMessage(`[]`),
		Metadata:      json.RawMessage(`{}`),
	}, nil
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
