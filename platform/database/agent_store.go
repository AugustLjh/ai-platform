package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrAgentDefinitionNotFound = errors.New("agent definition not found")
var ErrAgentRunNotFound = errors.New("agent run not found")

type AgentDefinition struct {
	ID           string          `json:"id"`
	TenantID     string          `json:"tenant_id"`
	Name         string          `json:"name"`
	Description  string          `json:"description,omitempty"`
	SystemPrompt string          `json:"system_prompt"`
	Model        string          `json:"model,omitempty"`
	Status       string          `json:"status"`
	Config       json.RawMessage `json:"config"`
	Metadata     json.RawMessage `json:"metadata"`
	CreatedBy    *string         `json:"created_by,omitempty"`
	UpdatedBy    *string         `json:"updated_by,omitempty"`
	ArchivedAt   *time.Time      `json:"archived_at,omitempty"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type AgentRun struct {
	ID                string          `json:"id"`
	AgentDefinitionID string          `json:"agent_definition_id"`
	TenantID          string          `json:"tenant_id"`
	UserID            *string         `json:"user_id,omitempty"`
	SessionID         *string         `json:"session_id,omitempty"`
	Status            string          `json:"status"`
	Input             json.RawMessage `json:"input"`
	Plan              json.RawMessage `json:"plan"`
	Context           json.RawMessage `json:"context"`
	FinalOutput       *string         `json:"final_output,omitempty"`
	ErrorMessage      *string         `json:"error_message,omitempty"`
	StartedAt         *time.Time      `json:"started_at,omitempty"`
	FinishedAt        *time.Time      `json:"finished_at,omitempty"`
	CancelledAt       *time.Time      `json:"cancelled_at,omitempty"`
	CreatedAt         time.Time       `json:"created_at"`
	UpdatedAt         time.Time       `json:"updated_at"`
	Metadata          json.RawMessage `json:"metadata"`
}

type AgentRunEvent struct {
	ID        string          `json:"id"`
	RunID     string          `json:"run_id"`
	Sequence  int64           `json:"sequence"`
	EventType string          `json:"event_type"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt time.Time       `json:"created_at"`
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
		          input, plan, context, final_output, error_message, started_at,
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
		       input, plan, context, final_output, error_message, started_at,
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
	return row, nil
}

func (s *AgentStore) ListAgentRuns(tenantID, userID string, limit, offset int) ([]*AgentRun, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, agent_definition_id, tenant_id, user_id, session_id, status,
		       input, plan, context, final_output, error_message, started_at,
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
	return items, rows.Err()
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
		          input, plan, context, final_output, error_message, started_at,
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
	return row, nil
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
