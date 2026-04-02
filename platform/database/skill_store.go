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

var ErrSkillNotFound = errors.New("skill not found")

type Skill struct {
	ID            string          `json:"id"`
	TenantID      *string         `json:"tenant_id,omitempty"`
	Name          string          `json:"name"`
	Slug          string          `json:"slug"`
	Version       string          `json:"version"`
	Description   string          `json:"description,omitempty"`
	RootPath      string          `json:"root_path"`
	SystemPrompt  string          `json:"system_prompt"`
	OutputSchema  json.RawMessage `json:"output_schema"`
	ToolAllowlist json.RawMessage `json:"tool_allowlist"`
	Metadata      json.RawMessage `json:"metadata"`
	Contract      json.RawMessage `json:"contract,omitempty"`
	CreatedAt     time.Time       `json:"created_at"`
	UpdatedAt     time.Time       `json:"updated_at"`
}

type SkillStore struct {
	pool *pgxpool.Pool
}

func NewSkillStore(pool *pgxpool.Pool) *SkillStore {
	return &SkillStore{pool: pool}
}

func (s *SkillStore) UpsertSkill(skill *Skill) (*Skill, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var existingID *string
	if err := s.pool.QueryRow(ctx, `
		SELECT id
		FROM skills
		WHERE (($1::uuid IS NULL AND tenant_id IS NULL) OR tenant_id = $1)
		  AND lower(slug) = lower($2)
		LIMIT 1
	`, nullIfPointer(skill.TenantID), skill.Slug).Scan(&existingID); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return nil, fmt.Errorf("failed to check existing skill: %w", err)
		}
		existingID = nil
	}

	row := &Skill{}
	var err error
	if existingID != nil {
		err = s.pool.QueryRow(ctx, `
			UPDATE skills
			SET
				name = $2,
				version = $3,
				description = $4,
				root_path = $5,
				system_prompt = $6,
				output_schema = $7,
				tool_allowlist = $8,
				metadata = $9
			WHERE id = $1
			RETURNING id, tenant_id, name, slug, version, description, root_path,
			          system_prompt, output_schema, tool_allowlist, metadata, created_at, updated_at
		`,
			existingID,
			skill.Name,
			skill.Version,
			nullIfEmpty(skill.Description),
			skill.RootPath,
			skill.SystemPrompt,
			normalizeJSONRaw(skill.OutputSchema, `{}`),
			normalizeJSONRaw(skill.ToolAllowlist, `[]`),
			normalizeJSONRaw(skill.Metadata, `{}`),
		).Scan(
			&row.ID,
			&row.TenantID,
			&row.Name,
			&row.Slug,
			&row.Version,
			&row.Description,
			&row.RootPath,
			&row.SystemPrompt,
			&row.OutputSchema,
			&row.ToolAllowlist,
			&row.Metadata,
			&row.CreatedAt,
			&row.UpdatedAt,
		)
	} else {
		err = s.pool.QueryRow(ctx, `
			INSERT INTO skills (
				tenant_id, name, slug, version, description, root_path,
				system_prompt, output_schema, tool_allowlist, metadata
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
			RETURNING id, tenant_id, name, slug, version, description, root_path,
			          system_prompt, output_schema, tool_allowlist, metadata, created_at, updated_at
		`,
			nullIfPointer(skill.TenantID),
			skill.Name,
			skill.Slug,
			skill.Version,
			nullIfEmpty(skill.Description),
			skill.RootPath,
			skill.SystemPrompt,
			normalizeJSONRaw(skill.OutputSchema, `{}`),
			normalizeJSONRaw(skill.ToolAllowlist, `[]`),
			normalizeJSONRaw(skill.Metadata, `{}`),
		).Scan(
			&row.ID,
			&row.TenantID,
			&row.Name,
			&row.Slug,
			&row.Version,
			&row.Description,
			&row.RootPath,
			&row.SystemPrompt,
			&row.OutputSchema,
			&row.ToolAllowlist,
			&row.Metadata,
			&row.CreatedAt,
			&row.UpdatedAt,
		)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to upsert skill: %w", err)
	}
	return row, nil
}

func (s *SkillStore) ListSkills(tenantID string) ([]*Skill, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, tenant_id, name, slug, version, description, root_path,
		       system_prompt, output_schema, tool_allowlist, metadata, created_at, updated_at
		FROM skills
		WHERE tenant_id IS NULL OR tenant_id = $1
		ORDER BY slug ASC, version DESC
	`, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list skills: %w", err)
	}
	defer rows.Close()

	var items []*Skill
	for rows.Next() {
		item := &Skill{}
		if err := rows.Scan(
			&item.ID,
			&item.TenantID,
			&item.Name,
			&item.Slug,
			&item.Version,
			&item.Description,
			&item.RootPath,
			&item.SystemPrompt,
			&item.OutputSchema,
			&item.ToolAllowlist,
			&item.Metadata,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan skill: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *SkillStore) GetSkill(id, tenantID string) (*Skill, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	item := &Skill{}
	err := s.pool.QueryRow(ctx, `
		SELECT id, tenant_id, name, slug, version, description, root_path,
		       system_prompt, output_schema, tool_allowlist, metadata, created_at, updated_at
		FROM skills
		WHERE id = $1 AND (tenant_id IS NULL OR tenant_id = $2)
	`, id, tenantID).Scan(
		&item.ID,
		&item.TenantID,
		&item.Name,
		&item.Slug,
		&item.Version,
		&item.Description,
		&item.RootPath,
		&item.SystemPrompt,
		&item.OutputSchema,
		&item.ToolAllowlist,
		&item.Metadata,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrSkillNotFound
		}
		return nil, fmt.Errorf("failed to get skill: %w", err)
	}
	return item, nil
}

func (s *SkillStore) ReplaceAgentSkillBindings(agentID string, skillIDs []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `DELETE FROM agent_skill_bindings WHERE agent_definition_id = $1`, agentID); err != nil {
		return fmt.Errorf("failed to clear agent skill bindings: %w", err)
	}

	for _, skillID := range skillIDs {
		if _, err := tx.Exec(ctx, `
			INSERT INTO agent_skill_bindings (agent_definition_id, skill_id, metadata)
			VALUES ($1, $2, '{}'::jsonb)
		`, agentID, skillID); err != nil {
			return fmt.Errorf("failed to bind skill %s: %w", skillID, err)
		}
	}

	return tx.Commit(ctx)
}

func (s *SkillStore) ListAgentSkillBindings(agentID string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT skill_id
		FROM agent_skill_bindings
		WHERE agent_definition_id = $1
		ORDER BY created_at ASC
	`, agentID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent skill bindings: %w", err)
	}
	defer rows.Close()

	var skillIDs []string
	for rows.Next() {
		var skillID string
		if err := rows.Scan(&skillID); err != nil {
			return nil, fmt.Errorf("failed to scan agent skill binding: %w", err)
		}
		skillIDs = append(skillIDs, skillID)
	}
	return skillIDs, rows.Err()
}
