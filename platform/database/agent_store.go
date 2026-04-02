package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrAgentDefinitionNotFound = errors.New("agent definition not found")
var ErrAgentRunNotFound = errors.New("agent run not found")

type AgentDefinition struct {
	ID               string          `json:"id"`
	TenantID         string          `json:"tenant_id"`
	Name             string          `json:"name"`
	Description      string          `json:"description,omitempty"`
	SystemPrompt     string          `json:"system_prompt"`
	Model            string          `json:"model,omitempty"`
	Status           string          `json:"status"`
	Config           json.RawMessage `json:"config"`
	Metadata         json.RawMessage `json:"metadata"`
	SkillIDs         []string        `json:"skill_ids,omitempty"`
	MCPServerIDs     []string        `json:"mcp_server_ids,omitempty"`
	KnowledgeBaseIDs []string        `json:"knowledge_base_ids,omitempty"`
	SubagentIDs      []string        `json:"subagent_ids,omitempty"`
	CreatedBy        *string         `json:"created_by,omitempty"`
	UpdatedBy        *string         `json:"updated_by,omitempty"`
	ArchivedAt       *time.Time      `json:"archived_at,omitempty"`
	CreatedAt        time.Time       `json:"created_at"`
	UpdatedAt        time.Time       `json:"updated_at"`
}

type AgentRun struct {
	ID                string           `json:"id"`
	AgentDefinitionID string           `json:"agent_definition_id"`
	TenantID          string           `json:"tenant_id"`
	UserID            *string          `json:"user_id,omitempty"`
	SessionID         *string          `json:"session_id,omitempty"`
	Status            string           `json:"status"`
	Input             json.RawMessage  `json:"input"`
	Plan              json.RawMessage  `json:"plan"`
	Context           json.RawMessage  `json:"context"`
	FinalOutput       *string          `json:"final_output,omitempty"`
	FinalOutputText   *string          `json:"final_output_text,omitempty"`
	FinalOutputJSON   json.RawMessage  `json:"final_output_json,omitempty"`
	ErrorMessage      *string          `json:"error_message,omitempty"`
	StartedAt         *time.Time       `json:"started_at,omitempty"`
	FinishedAt        *time.Time       `json:"finished_at,omitempty"`
	CancelledAt       *time.Time       `json:"cancelled_at,omitempty"`
	CreatedAt         time.Time        `json:"created_at"`
	UpdatedAt         time.Time        `json:"updated_at"`
	Metadata          json.RawMessage  `json:"metadata"`
	Artifacts         []*AgentArtifact `json:"artifacts,omitempty"`
	Steps             []*AgentRunStep  `json:"steps,omitempty"`
	ToolCalls         []*AgentToolCall `json:"tool_calls,omitempty"`
}

type AgentArtifact struct {
	ID           string          `json:"id"`
	RunID        string          `json:"run_id"`
	StepID       *string         `json:"step_id,omitempty"`
	ArtifactType string          `json:"artifact_type"`
	Name         string          `json:"name"`
	MimeType     *string         `json:"mime_type,omitempty"`
	URI          *string         `json:"uri,omitempty"`
	Payload      json.RawMessage `json:"payload"`
	Metadata     json.RawMessage `json:"metadata"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type AgentRunReference struct {
	ID        string  `json:"id"`
	SessionID *string `json:"session_id,omitempty"`
	Status    string  `json:"status"`
}

type AgentRunEvent struct {
	ID        string          `json:"id"`
	RunID     string          `json:"run_id"`
	Sequence  int64           `json:"sequence"`
	EventType string          `json:"event_type"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt time.Time       `json:"created_at"`
}

type AgentRunStep struct {
	ID           string          `json:"id"`
	RunID        string          `json:"run_id"`
	StepIndex    int             `json:"step_index"`
	Title        *string         `json:"title,omitempty"`
	Kind         string          `json:"kind"`
	Status       string          `json:"status"`
	Input        json.RawMessage `json:"input"`
	Output       json.RawMessage `json:"output"`
	ErrorMessage *string         `json:"error_message,omitempty"`
	Metadata     json.RawMessage `json:"metadata"`
	StartedAt    *time.Time      `json:"started_at,omitempty"`
	CompletedAt  *time.Time      `json:"completed_at,omitempty"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type AgentToolCall struct {
	ID           string          `json:"id"`
	RunID        string          `json:"run_id"`
	StepID       *string         `json:"step_id,omitempty"`
	ToolName     string          `json:"tool_name"`
	ToolKind     string          `json:"tool_kind"`
	Status       string          `json:"status"`
	Arguments    json.RawMessage `json:"arguments"`
	Result       json.RawMessage `json:"result"`
	ErrorMessage *string         `json:"error_message,omitempty"`
	StartedAt    *time.Time      `json:"started_at,omitempty"`
	CompletedAt  *time.Time      `json:"completed_at,omitempty"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type AgentStore struct {
	pool *pgxpool.Pool
}

func NewAgentStore(pool *pgxpool.Pool) *AgentStore {
	return &AgentStore{pool: pool}
}

func normalizeJSONRaw(raw json.RawMessage, fallback string) json.RawMessage {
	if len(raw) == 0 {
		return json.RawMessage(fallback)
	}
	return raw
}

func NormalizeJSONRawForExport(raw json.RawMessage, fallback string) json.RawMessage {
	return normalizeJSONRaw(raw, fallback)
}

func (s *AgentStore) CreateAgentDefinition(def *AgentDefinition) (*AgentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentDefinition{}
	err := s.pool.QueryRow(ctx, `
		INSERT INTO agent_definitions (
			tenant_id, name, description, system_prompt, model, status,
			config, metadata, created_by, updated_by
		)
		VALUES ($1, $2, $3, $4, $5, COALESCE($6, 'active'), $7, $8, $9, $9)
		RETURNING id, tenant_id, name, description, system_prompt, model, status,
		          config, metadata, created_by, updated_by, archived_at, created_at, updated_at
	`,
		def.TenantID,
		def.Name,
		nullIfEmpty(def.Description),
		def.SystemPrompt,
		nullIfEmpty(def.Model),
		nullIfEmpty(def.Status),
		normalizeJSONRaw(def.Config, `{}`),
		normalizeJSONRaw(def.Metadata, `{}`),
		nullIfPointer(def.CreatedBy),
	).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Description,
		&row.SystemPrompt,
		&row.Model,
		&row.Status,
		&row.Config,
		&row.Metadata,
		&row.CreatedBy,
		&row.UpdatedBy,
		&row.ArchivedAt,
		&row.CreatedAt,
		&row.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create agent definition: %w", err)
	}
	return row, nil
}

func (s *AgentStore) UpdateAgentDefinition(def *AgentDefinition) (*AgentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentDefinition{}
	err := s.pool.QueryRow(ctx, `
		UPDATE agent_definitions
		SET
			name = $3,
			description = $4,
			system_prompt = $5,
			model = $6,
			config = $7,
			metadata = $8,
			updated_by = $9
		WHERE id = $1 AND tenant_id = $2 AND status <> 'archived'
		RETURNING id, tenant_id, name, description, system_prompt, model, status,
		          config, metadata, created_by, updated_by, archived_at, created_at, updated_at
	`,
		def.ID,
		def.TenantID,
		def.Name,
		nullIfEmpty(def.Description),
		def.SystemPrompt,
		nullIfEmpty(def.Model),
		normalizeJSONRaw(def.Config, `{}`),
		normalizeJSONRaw(def.Metadata, `{}`),
		nullIfPointer(def.UpdatedBy),
	).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Description,
		&row.SystemPrompt,
		&row.Model,
		&row.Status,
		&row.Config,
		&row.Metadata,
		&row.CreatedBy,
		&row.UpdatedBy,
		&row.ArchivedAt,
		&row.CreatedAt,
		&row.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrAgentDefinitionNotFound
		}
		return nil, fmt.Errorf("failed to update agent definition: %w", err)
	}
	return row, nil
}

func (s *AgentStore) GetAgentDefinition(id, tenantID string) (*AgentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentDefinition{}
	err := s.pool.QueryRow(ctx, `
		SELECT id, tenant_id, name, description, system_prompt, model, status,
		       config, metadata, created_by, updated_by, archived_at, created_at, updated_at
		FROM agent_definitions
		WHERE id = $1 AND tenant_id = $2
	`, id, tenantID).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Description,
		&row.SystemPrompt,
		&row.Model,
		&row.Status,
		&row.Config,
		&row.Metadata,
		&row.CreatedBy,
		&row.UpdatedBy,
		&row.ArchivedAt,
		&row.CreatedAt,
		&row.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrAgentDefinitionNotFound
		}
		return nil, fmt.Errorf("failed to get agent definition: %w", err)
	}
	return row, nil
}

func (s *AgentStore) ListAgentDefinitions(tenantID string, includeArchived bool) ([]*AgentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, tenant_id, name, description, system_prompt, model, status,
		       config, metadata, created_by, updated_by, archived_at, created_at, updated_at
		FROM agent_definitions
		WHERE tenant_id = $1
		  AND ($2 OR status <> 'archived')
		ORDER BY updated_at DESC
	`, tenantID, includeArchived)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent definitions: %w", err)
	}
	defer rows.Close()

	var items []*AgentDefinition
	for rows.Next() {
		item := &AgentDefinition{}
		if err := rows.Scan(
			&item.ID,
			&item.TenantID,
			&item.Name,
			&item.Description,
			&item.SystemPrompt,
			&item.Model,
			&item.Status,
			&item.Config,
			&item.Metadata,
			&item.CreatedBy,
			&item.UpdatedBy,
			&item.ArchivedAt,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan agent definition: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *AgentStore) ArchiveAgentDefinition(id, tenantID, updatedBy string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	result, err := s.pool.Exec(ctx, `
		UPDATE agent_definitions
		SET status = 'archived', archived_at = now(), updated_by = $3
		WHERE id = $1 AND tenant_id = $2 AND status <> 'archived'
	`, id, tenantID, nullIfEmpty(updatedBy))
	if err != nil {
		return fmt.Errorf("failed to archive agent definition: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrAgentDefinitionNotFound
	}
	return nil
}

func (s *AgentStore) ListAgentRunReferencesByDefinition(agentDefinitionID, tenantID string) ([]*AgentRunReference, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, session_id, status
		FROM agent_runs
		WHERE agent_definition_id = $1 AND tenant_id = $2
		ORDER BY created_at DESC
	`, agentDefinitionID, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent run references: %w", err)
	}
	defer rows.Close()

	var items []*AgentRunReference
	for rows.Next() {
		item := &AgentRunReference{}
		if err := rows.Scan(&item.ID, &item.SessionID, &item.Status); err != nil {
			return nil, fmt.Errorf("failed to scan agent run reference: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *AgentStore) ListAgentRunReferencesByDefinitionAndSession(agentDefinitionID, tenantID, sessionID string) ([]*AgentRunReference, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, session_id, status
		FROM agent_runs
		WHERE agent_definition_id = $1 AND tenant_id = $2 AND session_id = $3
		ORDER BY created_at DESC
	`, agentDefinitionID, tenantID, sessionID)
	if err != nil {
		return nil, fmt.Errorf("failed to list session run references: %w", err)
	}
	defer rows.Close()

	var items []*AgentRunReference
	for rows.Next() {
		item := &AgentRunReference{}
		if err := rows.Scan(&item.ID, &item.SessionID, &item.Status); err != nil {
			return nil, fmt.Errorf("failed to scan session run reference: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *AgentStore) HardDeleteAgentDefinition(id, tenantID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	rows, err := tx.Query(ctx, `
		SELECT DISTINCT session_id
		FROM agent_runs
		WHERE agent_definition_id = $1
		  AND tenant_id = $2
		  AND session_id IS NOT NULL
	`, id, tenantID)
	if err != nil {
		return fmt.Errorf("failed to collect agent sessions: %w", err)
	}
	var sessionIDs []string
	for rows.Next() {
		var sessionID string
		if err := rows.Scan(&sessionID); err != nil {
			rows.Close()
			return fmt.Errorf("failed to scan agent session id: %w", err)
		}
		sessionIDs = append(sessionIDs, sessionID)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return fmt.Errorf("failed to iterate agent sessions: %w", err)
	}
	rows.Close()

	if _, err := tx.Exec(ctx, `DELETE FROM agent_runs WHERE agent_definition_id = $1 AND tenant_id = $2`, id, tenantID); err != nil {
		return fmt.Errorf("failed to delete agent runs: %w", err)
	}

	result, err := tx.Exec(ctx, `DELETE FROM agent_definitions WHERE id = $1 AND tenant_id = $2`, id, tenantID)
	if err != nil {
		return fmt.Errorf("failed to delete agent definition: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrAgentDefinitionNotFound
	}

	for _, sessionID := range normalizeStringIDs(sessionIDs) {
		var remainingRuns int
		if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM agent_runs WHERE session_id = $1`, sessionID).Scan(&remainingRuns); err != nil {
			return fmt.Errorf("failed to count remaining agent runs for session %s: %w", sessionID, err)
		}
		if remainingRuns > 0 {
			continue
		}
		if _, err := tx.Exec(ctx, `DELETE FROM sessions WHERE id = $1 AND title = 'Agent 对话'`, sessionID); err != nil {
			return fmt.Errorf("failed to delete orphaned agent session %s: %w", sessionID, err)
		}
	}

	return tx.Commit(ctx)
}

func (s *AgentStore) ClearAgentSessionContext(agentDefinitionID, tenantID, sessionID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `
		DELETE FROM agent_runs
		WHERE agent_definition_id = $1
		  AND tenant_id = $2
		  AND session_id = $3
	`, agentDefinitionID, tenantID, sessionID); err != nil {
		return fmt.Errorf("failed to delete agent session runs: %w", err)
	}

	var remainingRuns int
	if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM agent_runs WHERE session_id = $1`, sessionID).Scan(&remainingRuns); err != nil {
		return fmt.Errorf("failed to count remaining session runs: %w", err)
	}
	if remainingRuns == 0 {
		if _, err := tx.Exec(ctx, `DELETE FROM sessions WHERE id = $1 AND title = 'Agent 对话'`, sessionID); err != nil {
			return fmt.Errorf("failed to delete cleared agent session: %w", err)
		}
	}

	return tx.Commit(ctx)
}

func normalizeStringIDs(ids []string) []string {
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

func (s *AgentStore) ReplaceAgentKnowledgeBindings(agentID, tenantID, userID string, knowledgeBaseIDs []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	normalizedIDs := normalizeStringIDs(knowledgeBaseIDs)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if len(normalizedIDs) > 0 {
		rows, err := tx.Query(ctx, `
			SELECT id
			FROM knowledge_bases
			WHERE tenant_id = $1
			  AND id = ANY($2)
			  AND (
					access_level = 'tenant'
					OR (access_level = 'user' AND user_id = $3)
			  )
		`, tenantID, normalizedIDs, nullIfEmpty(userID))
		if err != nil {
			return fmt.Errorf("failed to validate knowledge base bindings: %w", err)
		}
		defer rows.Close()

		allowed := make(map[string]struct{}, len(normalizedIDs))
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err != nil {
				return fmt.Errorf("failed to scan allowed knowledge base id: %w", err)
			}
			allowed[id] = struct{}{}
		}
		if err := rows.Err(); err != nil {
			return fmt.Errorf("failed to iterate allowed knowledge bases: %w", err)
		}
		for _, id := range normalizedIDs {
			if _, ok := allowed[id]; !ok {
				return fmt.Errorf("knowledge base %s not found or access denied", id)
			}
		}
	}

	if _, err := tx.Exec(ctx, `DELETE FROM agent_knowledge_bindings WHERE agent_definition_id = $1`, agentID); err != nil {
		return fmt.Errorf("failed to clear agent knowledge bindings: %w", err)
	}

	for _, knowledgeBaseID := range normalizedIDs {
		if _, err := tx.Exec(ctx, `
			INSERT INTO agent_knowledge_bindings (agent_definition_id, knowledge_base_id, metadata)
			VALUES ($1, $2, '{}'::jsonb)
		`, agentID, knowledgeBaseID); err != nil {
			return fmt.Errorf("failed to bind knowledge base %s: %w", knowledgeBaseID, err)
		}
	}

	return tx.Commit(ctx)
}

func (s *AgentStore) ListAgentKnowledgeBindings(agentID string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT knowledge_base_id
		FROM agent_knowledge_bindings
		WHERE agent_definition_id = $1
		ORDER BY created_at ASC
	`, agentID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent knowledge bindings: %w", err)
	}
	defer rows.Close()

	var knowledgeBaseIDs []string
	for rows.Next() {
		var knowledgeBaseID string
		if err := rows.Scan(&knowledgeBaseID); err != nil {
			return nil, fmt.Errorf("failed to scan agent knowledge binding: %w", err)
		}
		knowledgeBaseIDs = append(knowledgeBaseIDs, knowledgeBaseID)
	}
	return knowledgeBaseIDs, rows.Err()
}

func (s *AgentStore) CreateAgentRun(run *AgentRun) (*AgentRun, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentRun{}
	err := s.pool.QueryRow(ctx, `
		INSERT INTO agent_runs (
			agent_definition_id, tenant_id, user_id, session_id, status,
			input, plan, context, metadata
		)
		VALUES ($1, $2, $3, $4, COALESCE($5, 'queued'), $6, $7, $8, $9)
		RETURNING id, agent_definition_id, tenant_id, user_id, session_id, status,
		          input, plan, context, final_output, final_output_text, final_output_json, error_message, started_at,
		          finished_at, cancelled_at, created_at, updated_at, metadata
	`,
		run.AgentDefinitionID,
		run.TenantID,
		nullIfPointer(run.UserID),
		nullIfPointer(run.SessionID),
		nullIfEmpty(run.Status),
		normalizeJSONRaw(run.Input, `{}`),
		normalizeJSONRaw(run.Plan, `{}`),
		normalizeJSONRaw(run.Context, `{}`),
		normalizeJSONRaw(run.Metadata, `{}`),
	).Scan(
		&row.ID,
		&row.AgentDefinitionID,
		&row.TenantID,
		&row.UserID,
		&row.SessionID,
		&row.Status,
		&row.Input,
		&row.Plan,
		&row.Context,
		&row.FinalOutput,
		&row.FinalOutputText,
		&row.FinalOutputJSON,
		&row.ErrorMessage,
		&row.StartedAt,
		&row.FinishedAt,
		&row.CancelledAt,
		&row.CreatedAt,
		&row.UpdatedAt,
		&row.Metadata,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create agent run: %w", err)
	}
	return row, nil
}

func (s *AgentStore) GetAgentRun(id, tenantID string) (*AgentRun, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentRun{}
	err := s.pool.QueryRow(ctx, `
		SELECT id, agent_definition_id, tenant_id, user_id, session_id, status,
		       input, plan, context, final_output, final_output_text, final_output_json, error_message, started_at,
		       finished_at, cancelled_at, created_at, updated_at, metadata
		FROM agent_runs
		WHERE id = $1 AND tenant_id = $2
	`, id, tenantID).Scan(
		&row.ID,
		&row.AgentDefinitionID,
		&row.TenantID,
		&row.UserID,
		&row.SessionID,
		&row.Status,
		&row.Input,
		&row.Plan,
		&row.Context,
		&row.FinalOutput,
		&row.FinalOutputText,
		&row.FinalOutputJSON,
		&row.ErrorMessage,
		&row.StartedAt,
		&row.FinishedAt,
		&row.CancelledAt,
		&row.CreatedAt,
		&row.UpdatedAt,
		&row.Metadata,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrAgentRunNotFound
		}
		return nil, fmt.Errorf("failed to get agent run: %w", err)
	}
	if err := s.hydrateAgentRunArtifacts(row, tenantID); err != nil {
		return nil, err
	}
	if err := s.hydrateAgentRunExecution(row, tenantID); err != nil {
		return nil, err
	}
	s.applyLegacyRunCompatibility(row)
	return row, nil
}

func (s *AgentStore) ListAgentRuns(tenantID, userID string, limit, offset int) ([]*AgentRun, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, agent_definition_id, tenant_id, user_id, session_id, status,
		       input, plan, context, final_output, final_output_text, final_output_json, error_message, started_at,
		       finished_at, cancelled_at, created_at, updated_at, metadata
		FROM agent_runs
		WHERE tenant_id = $1
		  AND ($2 = '' OR user_id = $2::uuid)
		ORDER BY created_at DESC
		LIMIT $3 OFFSET $4
	`, tenantID, userID, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent runs: %w", err)
	}
	defer rows.Close()

	var items []*AgentRun
	for rows.Next() {
		item := &AgentRun{}
		if err := rows.Scan(
			&item.ID,
			&item.AgentDefinitionID,
			&item.TenantID,
			&item.UserID,
			&item.SessionID,
			&item.Status,
			&item.Input,
			&item.Plan,
			&item.Context,
			&item.FinalOutput,
			&item.FinalOutputText,
			&item.FinalOutputJSON,
			&item.ErrorMessage,
			&item.StartedAt,
			&item.FinishedAt,
			&item.CancelledAt,
			&item.CreatedAt,
			&item.UpdatedAt,
			&item.Metadata,
		); err != nil {
			return nil, fmt.Errorf("failed to scan agent run: %w", err)
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if err := s.hydrateAgentRunsArtifacts(items, tenantID); err != nil {
		return nil, err
	}
	for _, item := range items {
		s.applyLegacyRunCompatibility(item)
	}
	return items, nil
}

func (s *AgentStore) UpdateAgentRunStatus(runID, status string, plan json.RawMessage, finalOutput, errorMessage *string) (*AgentRun, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	row := &AgentRun{}
	err := s.pool.QueryRow(ctx, `
		UPDATE agent_runs
		SET
			status = $2,
			plan = COALESCE($3, plan),
			final_output = COALESCE($4, final_output),
			error_message = $5,
			started_at = CASE
				WHEN $2 = 'running' AND started_at IS NULL THEN now()
				ELSE started_at
			END,
			finished_at = CASE
				WHEN $2 IN ('completed', 'failed') THEN now()
				ELSE finished_at
			END,
			cancelled_at = CASE
				WHEN $2 = 'cancelled' THEN now()
				ELSE cancelled_at
			END
		WHERE id = $1
		RETURNING id, agent_definition_id, tenant_id, user_id, session_id, status,
		          input, plan, context, final_output, final_output_text, final_output_json, error_message, started_at,
		          finished_at, cancelled_at, created_at, updated_at, metadata
	`, runID, status, nilIfEmptyJSON(plan), finalOutput, errorMessage).Scan(
		&row.ID,
		&row.AgentDefinitionID,
		&row.TenantID,
		&row.UserID,
		&row.SessionID,
		&row.Status,
		&row.Input,
		&row.Plan,
		&row.Context,
		&row.FinalOutput,
		&row.FinalOutputText,
		&row.FinalOutputJSON,
		&row.ErrorMessage,
		&row.StartedAt,
		&row.FinishedAt,
		&row.CancelledAt,
		&row.CreatedAt,
		&row.UpdatedAt,
		&row.Metadata,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrAgentRunNotFound
		}
		return nil, fmt.Errorf("failed to update agent run status: %w", err)
	}
	s.applyLegacyRunCompatibility(row)
	return row, nil
}

func (s *AgentStore) listAgentArtifactsByRunIDs(runIDs []string, tenantID string) (map[string][]*AgentArtifact, error) {
	if len(runIDs) == 0 {
		return map[string][]*AgentArtifact{}, nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT a.id, a.run_id, a.step_id, a.artifact_type, a.name, a.mime_type, a.uri,
		       a.payload, a.metadata, a.created_at, a.updated_at
		FROM agent_artifacts a
		INNER JOIN agent_runs r ON r.id = a.run_id
		WHERE a.run_id = ANY($1::uuid[]) AND r.tenant_id = $2
		ORDER BY a.run_id ASC, a.created_at ASC, a.updated_at ASC
	`, runIDs, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent artifacts: %w", err)
	}
	defer rows.Close()

	grouped := make(map[string][]*AgentArtifact)
	for rows.Next() {
		item := &AgentArtifact{}
		if err := rows.Scan(
			&item.ID,
			&item.RunID,
			&item.StepID,
			&item.ArtifactType,
			&item.Name,
			&item.MimeType,
			&item.URI,
			&item.Payload,
			&item.Metadata,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan agent artifact: %w", err)
		}
		item.Payload = normalizeJSONRaw(item.Payload, `{}`)
		item.Metadata = normalizeJSONRaw(item.Metadata, `{}`)
		grouped[item.RunID] = append(grouped[item.RunID], item)
	}
	return grouped, rows.Err()
}

func (s *AgentStore) hydrateAgentRunArtifacts(run *AgentRun, tenantID string) error {
	if run == nil {
		return nil
	}
	grouped, err := s.listAgentArtifactsByRunIDs([]string{run.ID}, tenantID)
	if err != nil {
		return err
	}
	run.Artifacts = grouped[run.ID]
	if run.Artifacts == nil {
		run.Artifacts = []*AgentArtifact{}
	}
	return nil
}

func (s *AgentStore) hydrateAgentRunExecution(run *AgentRun, tenantID string) error {
	if run == nil {
		return nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	stepRows, err := s.pool.Query(ctx, `
		SELECT st.id, st.run_id, st.step_index, st.title, st.kind, st.status, st.input, st.output,
		       st.error_message, st.metadata, st.started_at, st.completed_at, st.created_at, st.updated_at
		FROM agent_run_steps st
		INNER JOIN agent_runs r ON r.id = st.run_id
		WHERE st.run_id = $1 AND r.tenant_id = $2
		ORDER BY st.step_index ASC, st.created_at ASC
	`, run.ID, tenantID)
	if err != nil {
		return fmt.Errorf("failed to list agent run steps: %w", err)
	}
	defer stepRows.Close()

	var steps []*AgentRunStep
	for stepRows.Next() {
		item := &AgentRunStep{}
		if err := stepRows.Scan(
			&item.ID,
			&item.RunID,
			&item.StepIndex,
			&item.Title,
			&item.Kind,
			&item.Status,
			&item.Input,
			&item.Output,
			&item.ErrorMessage,
			&item.Metadata,
			&item.StartedAt,
			&item.CompletedAt,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return fmt.Errorf("failed to scan agent run step: %w", err)
		}
		item.Input = normalizeJSONRaw(item.Input, `{}`)
		item.Output = normalizeJSONRaw(item.Output, `{}`)
		item.Metadata = normalizeJSONRaw(item.Metadata, `{}`)
		steps = append(steps, item)
	}
	if err := stepRows.Err(); err != nil {
		return err
	}

	toolRows, err := s.pool.Query(ctx, `
		SELECT tc.id, tc.run_id, tc.step_id, tc.tool_name, tc.tool_kind, tc.status, tc.arguments, tc.result,
		       tc.error_message, tc.started_at, tc.completed_at, tc.created_at, tc.updated_at
		FROM agent_tool_calls tc
		INNER JOIN agent_runs r ON r.id = tc.run_id
		WHERE tc.run_id = $1 AND r.tenant_id = $2
		ORDER BY tc.created_at ASC, tc.updated_at ASC
	`, run.ID, tenantID)
	if err != nil {
		return fmt.Errorf("failed to list agent tool calls: %w", err)
	}
	defer toolRows.Close()

	var toolCalls []*AgentToolCall
	for toolRows.Next() {
		item := &AgentToolCall{}
		if err := toolRows.Scan(
			&item.ID,
			&item.RunID,
			&item.StepID,
			&item.ToolName,
			&item.ToolKind,
			&item.Status,
			&item.Arguments,
			&item.Result,
			&item.ErrorMessage,
			&item.StartedAt,
			&item.CompletedAt,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return fmt.Errorf("failed to scan agent tool call: %w", err)
		}
		item.Arguments = normalizeJSONRaw(item.Arguments, `{}`)
		item.Result = normalizeJSONRaw(item.Result, `{}`)
		toolCalls = append(toolCalls, item)
	}
	if err := toolRows.Err(); err != nil {
		return err
	}

	run.Steps = steps
	if run.Steps == nil {
		run.Steps = []*AgentRunStep{}
	}
	run.ToolCalls = toolCalls
	if run.ToolCalls == nil {
		run.ToolCalls = []*AgentToolCall{}
	}
	return nil
}

func (s *AgentStore) hydrateAgentRunsArtifacts(runs []*AgentRun, tenantID string) error {
	runIDs := make([]string, 0, len(runs))
	for _, run := range runs {
		if run == nil || run.ID == "" {
			continue
		}
		runIDs = append(runIDs, run.ID)
	}
	grouped, err := s.listAgentArtifactsByRunIDs(runIDs, tenantID)
	if err != nil {
		return err
	}
	for _, run := range runs {
		if run == nil {
			continue
		}
		run.Artifacts = grouped[run.ID]
		if run.Artifacts == nil {
			run.Artifacts = []*AgentArtifact{}
		}
	}
	return nil
}

func (s *AgentStore) applyLegacyRunCompatibility(run *AgentRun) {
	if run == nil {
		return
	}
	run.Input = normalizeJSONRaw(run.Input, `{}`)
	run.Plan = normalizeJSONRaw(run.Plan, `{}`)
	run.Context = normalizeJSONRaw(run.Context, `{}`)
	run.Metadata = normalizeJSONRaw(run.Metadata, `{}`)
	if len(run.FinalOutputJSON) == 0 {
		run.FinalOutputJSON = nil
	}
	if (run.FinalOutputText == nil || *run.FinalOutputText == "") && run.FinalOutput != nil && *run.FinalOutput != "" {
		run.FinalOutputText = run.FinalOutput
	}
}

func (s *AgentStore) AppendAgentRunEvent(runID, eventType string, payload json.RawMessage) (*AgentRunEvent, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, runID); err != nil {
		return nil, fmt.Errorf("failed to lock run event sequence: %w", err)
	}

	var sequence int64
	if err := tx.QueryRow(ctx, `
		SELECT COALESCE(MAX(sequence), 0) + 1
		FROM agent_run_events
		WHERE run_id = $1
	`, runID).Scan(&sequence); err != nil {
		return nil, fmt.Errorf("failed to resolve next event sequence: %w", err)
	}

	row := &AgentRunEvent{}
	if err := tx.QueryRow(ctx, `
		INSERT INTO agent_run_events (run_id, sequence, event_type, payload)
		VALUES ($1, $2, $3, $4)
		RETURNING id, run_id, sequence, event_type, payload, created_at
	`, runID, sequence, eventType, normalizeJSONRaw(payload, `{}`)).Scan(
		&row.ID,
		&row.RunID,
		&row.Sequence,
		&row.EventType,
		&row.Payload,
		&row.CreatedAt,
	); err != nil {
		return nil, fmt.Errorf("failed to append agent run event: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("failed to commit agent run event: %w", err)
	}
	return row, nil
}

func (s *AgentStore) ListAgentRunEvents(runID, tenantID string, afterSequence int64, limit int) ([]*AgentRunEvent, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT e.id, e.run_id, e.sequence, e.event_type, e.payload, e.created_at
		FROM agent_run_events e
		INNER JOIN agent_runs r ON r.id = e.run_id
		WHERE e.run_id = $1 AND r.tenant_id = $2 AND e.sequence > $3
		ORDER BY sequence ASC
		LIMIT $4
	`, runID, tenantID, afterSequence, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent run events: %w", err)
	}
	defer rows.Close()

	var items []*AgentRunEvent
	for rows.Next() {
		item := &AgentRunEvent{}
		if err := rows.Scan(
			&item.ID,
			&item.RunID,
			&item.Sequence,
			&item.EventType,
			&item.Payload,
			&item.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan agent run event: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func nullIfEmpty(value string) interface{} {
	if value == "" {
		return nil
	}
	return value
}

func nullIfPointer(value *string) interface{} {
	if value == nil || *value == "" {
		return nil
	}
	return *value
}

func nilIfEmptyJSON(value json.RawMessage) interface{} {
	if len(value) == 0 {
		return nil
	}
	return value
}
