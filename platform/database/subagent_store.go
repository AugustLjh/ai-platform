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
	TargetAgentDefinitionID string          `json:"target_agent_definition_id,omitempty"`
	HandoffPrompt           string          `json:"handoff_prompt,omitempty"`
	CreatedBy               *string         `json:"created_by,omitempty"`
	UpdatedBy               *string         `json:"updated_by,omitempty"`
	ArchivedAt              *time.Time      `json:"archived_at,omitempty"`
	CreatedAt               time.Time       `json:"created_at"`
	UpdatedAt               time.Time       `json:"updated_at"`
}

type SubagentDefinitionVersion struct {
	ID                 string
	DefinitionID       string
	VersionNumber      int
	LifecycleStatus    string
	SystemPrompt       string
	Model              string
	Config             json.RawMessage
	Metadata           json.RawMessage
	OutputSchema       json.RawMessage
	HandoffInputSchema json.RawMessage
	ToolAllowlist      json.RawMessage
	SkillAllowlist     json.RawMessage
	MCPAllowlist       json.RawMessage
	KnowledgePolicy    json.RawMessage
	ReviewPolicy       json.RawMessage
	RuntimePolicy      json.RawMessage
	CreatedBy          *string
	UpdatedBy          *string
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

func publicationTenantValue(tenantID, scope string) any {
	if defaultSubagentPublicationScope(scope) == "system_global" {
		return nil
	}
	return tenantID
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
		          mcp_allowlist, knowledge_policy, review_policy, runtime_policy, created_by, updated_by
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

func (s *SubagentStore) UpdateSubagentDefinition(def *SubagentDefinition) (*SubagentDefinition, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

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

	if _, err := s.upsertPublicationTx(ctx, tx, &SubagentPublication{
		DefinitionID: def.ID,
		VersionID:    version.ID,
		TenantID:     def.createdPublicationTenant(),
		Visibility:   def.PublicationScope,
		Status:       def.Status,
		Metadata:     def.PublicationMetadata,
		UpdatedBy:    def.UpdatedBy,
	}); err != nil {
		return nil, err
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

	if _, err := tx.Exec(ctx, `
		DELETE FROM agent_subagent_bindings
		WHERE subagent_definition_id = $1
	`, id); err != nil {
		return fmt.Errorf("failed to clear subagent bindings: %w", err)
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

func (s *SubagentStore) ReplaceAgentSubagentBindings(agentID, tenantID string, subagentIDs []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	normalizedIDs := normalizeStringIDs(subagentIDs)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if len(normalizedIDs) > 0 {
		rows, err := tx.Query(ctx, `
			SELECT id
			FROM subagent_definitions
			WHERE tenant_id = $1
			  AND status = 'active'
			  AND id = ANY($2)
		`, tenantID, normalizedIDs)
		if err != nil {
			return fmt.Errorf("failed to validate subagent bindings: %w", err)
		}
		defer rows.Close()

		allowed := make(map[string]struct{}, len(normalizedIDs))
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err != nil {
				return fmt.Errorf("failed to scan allowed subagent id: %w", err)
			}
			allowed[id] = struct{}{}
		}
		if err := rows.Err(); err != nil {
			return fmt.Errorf("failed to iterate allowed subagents: %w", err)
		}
		for _, id := range normalizedIDs {
			if _, ok := allowed[id]; !ok {
				return fmt.Errorf("subagent %s not found or inactive", id)
			}
		}
	}

	if _, err := tx.Exec(ctx, `
		DELETE FROM agent_subagent_bindings
		WHERE agent_definition_id = $1
	`, agentID); err != nil {
		return fmt.Errorf("failed to clear agent subagent bindings: %w", err)
	}

	for _, subagentID := range normalizedIDs {
		if _, err := tx.Exec(ctx, `
			INSERT INTO agent_subagent_bindings (agent_definition_id, subagent_definition_id, metadata)
			VALUES ($1, $2, '{}'::jsonb)
		`, agentID, subagentID); err != nil {
			return fmt.Errorf("failed to bind subagent %s: %w", subagentID, err)
		}
	}

	return tx.Commit(ctx)
}

func (s *SubagentStore) ListAgentSubagentBindings(agentID string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT subagent_definition_id
		FROM agent_subagent_bindings
		WHERE agent_definition_id = $1
		ORDER BY created_at ASC
	`, agentID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent subagent bindings: %w", err)
	}
	defer rows.Close()

	var subagentIDs []string
	for rows.Next() {
		var subagentID string
		if err := rows.Scan(&subagentID); err != nil {
			return nil, fmt.Errorf("failed to scan agent subagent binding: %w", err)
		}
		subagentIDs = append(subagentIDs, subagentID)
	}
	return subagentIDs, rows.Err()
}
