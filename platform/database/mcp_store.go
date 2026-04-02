package database

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrMCPServerNotFound = errors.New("mcp server not found")

type MCPServer struct {
	ID           string           `json:"id"`
	TenantID     string           `json:"tenant_id"`
	Name         string           `json:"name"`
	Transport    string           `json:"transport"`
	Endpoint     string           `json:"endpoint,omitempty"`
	Command      string           `json:"command,omitempty"`
	Args         json.RawMessage  `json:"args"`
	Env          json.RawMessage  `json:"env"`
	Status       string           `json:"status"`
	LastTestedAt *time.Time       `json:"last_tested_at,omitempty"`
	LastError    *string          `json:"last_error,omitempty"`
	Metadata     json.RawMessage  `json:"metadata"`
	CreatedBy    *string          `json:"created_by,omitempty"`
	UpdatedBy    *string          `json:"updated_by,omitempty"`
	CreatedAt    time.Time        `json:"created_at"`
	UpdatedAt    time.Time        `json:"updated_at"`
	Tools        []*MCPServerTool `json:"tools,omitempty"`
	Connection   *MCPConnection   `json:"connection,omitempty"`
	Catalog      *MCPCatalog      `json:"catalog,omitempty"`
	Availability *MCPAvailability `json:"availability,omitempty"`
	BindingUsage *MCPBindingUsage `json:"binding_usage,omitempty"`
}

type MCPServerTool struct {
	ID           string          `json:"id"`
	ServerID     string          `json:"server_id"`
	RuntimeName  string          `json:"runtime_name,omitempty"`
	ServerName   string          `json:"server_name,omitempty"`
	Transport    string          `json:"transport,omitempty"`
	ToolName     string          `json:"tool_name"`
	Description  string          `json:"description,omitempty"`
	InputSchema  json.RawMessage `json:"input_schema"`
	Metadata     json.RawMessage `json:"metadata"`
	DiscoveredAt time.Time       `json:"discovered_at"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type MCPConnection struct {
	Status   string     `json:"status"`
	Summary  string     `json:"summary"`
	TestedAt *time.Time `json:"tested_at,omitempty"`
	Error    string     `json:"error,omitempty"`
}

type MCPCatalog struct {
	Status            string     `json:"status"`
	Summary           string     `json:"summary"`
	ToolCount         int        `json:"tool_count"`
	RefreshedAt       *time.Time `json:"refreshed_at,omitempty"`
	AgeSeconds        *int64     `json:"age_seconds,omitempty"`
	StaleAfterSeconds int64      `json:"stale_after_seconds"`
	IsStale           bool       `json:"is_stale"`
	SampleTools       []string   `json:"sample_tools,omitempty"`
}

type MCPAvailability struct {
	Status   string `json:"status"`
	Summary  string `json:"summary"`
	Bindable bool   `json:"bindable"`
	Reason   string `json:"reason,omitempty"`
}

type MCPBindingUsage struct {
	AgentCount int                `json:"agent_count"`
	Summary    string             `json:"summary"`
	MoreCount  int                `json:"more_count,omitempty"`
	Agents     []*MCPBindingAgent `json:"agents,omitempty"`
}

type MCPBindingAgent struct {
	AgentID string `json:"agent_id"`
	Name    string `json:"name"`
	Status  string `json:"status"`
}

type MCPStore struct {
	pool *pgxpool.Pool
}

type rowScanner interface {
	Scan(dest ...any) error
}

func NewMCPStore(pool *pgxpool.Pool) *MCPStore {
	return &MCPStore{pool: pool}
}

func (s *MCPStore) CreateServer(server *MCPServer) (*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	row := &MCPServer{}
	err := scanMCPServer(s.pool.QueryRow(ctx, `
		INSERT INTO mcp_servers (
			tenant_id, name, transport, endpoint, command, args, env,
			status, metadata, created_by, updated_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8, 'active'), $9, $10, $10)
		RETURNING id, tenant_id, name, transport, endpoint, command, args, env,
		          status, last_tested_at, last_error, metadata, created_by, updated_by,
		          created_at, updated_at
	`,
		server.TenantID,
		server.Name,
		server.Transport,
		nullIfEmpty(server.Endpoint),
		nullIfEmpty(server.Command),
		normalizeJSONRaw(server.Args, `[]`),
		normalizeJSONRaw(server.Env, `{}`),
		nullIfEmpty(server.Status),
		normalizeJSONRaw(server.Metadata, `{}`),
		nullIfPointer(server.CreatedBy),
	), row)
	if err != nil {
		return nil, fmt.Errorf("failed to create mcp server: %w", err)
	}
	return row, nil
}

func (s *MCPStore) UpdateServer(server *MCPServer) (*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	row := &MCPServer{}
	err := scanMCPServer(s.pool.QueryRow(ctx, `
		UPDATE mcp_servers
		SET
			name = $3,
			transport = $4,
			endpoint = $5,
			command = $6,
			args = $7,
			env = $8,
			status = $9,
			metadata = $10,
			updated_by = $11
		WHERE id = $1 AND tenant_id = $2
		RETURNING id, tenant_id, name, transport, endpoint, command, args, env,
		          status, last_tested_at, last_error, metadata, created_by, updated_by,
		          created_at, updated_at
	`,
		server.ID,
		server.TenantID,
		server.Name,
		server.Transport,
		nullIfEmpty(server.Endpoint),
		nullIfEmpty(server.Command),
		normalizeJSONRaw(server.Args, `[]`),
		normalizeJSONRaw(server.Env, `{}`),
		server.Status,
		normalizeJSONRaw(server.Metadata, `{}`),
		nullIfPointer(server.UpdatedBy),
	), row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrMCPServerNotFound
		}
		return nil, fmt.Errorf("failed to update mcp server: %w", err)
	}
	return row, nil
}

func (s *MCPStore) GetServer(id, tenantID string) (*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	row := &MCPServer{}
	err := scanMCPServer(s.pool.QueryRow(ctx, `
		SELECT id, tenant_id, name, transport, endpoint, command, args, env,
		       status, last_tested_at, last_error, metadata, created_by, updated_by,
		       created_at, updated_at
		FROM mcp_servers
		WHERE id = $1 AND tenant_id = $2
	`, id, tenantID), row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrMCPServerNotFound
		}
		return nil, fmt.Errorf("failed to get mcp server: %w", err)
	}
	return row, nil
}

func (s *MCPStore) ListServers(tenantID string) ([]*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	rows, err := s.pool.Query(ctx, `
		SELECT id, tenant_id, name, transport, endpoint, command, args, env,
		       status, last_tested_at, last_error, metadata, created_by, updated_by,
		       created_at, updated_at
		FROM mcp_servers
		WHERE tenant_id = $1
		ORDER BY updated_at DESC
	`, tenantID)
	if err != nil {
		return nil, fmt.Errorf("failed to list mcp servers: %w", err)
	}
	defer rows.Close()
	var items []*MCPServer
	for rows.Next() {
		item := &MCPServer{}
		if err := scanMCPServer(rows, item); err != nil {
			return nil, fmt.Errorf("failed to scan mcp server: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *MCPStore) DeleteServer(id, tenantID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := s.pool.Exec(ctx, `DELETE FROM mcp_servers WHERE id = $1 AND tenant_id = $2`, id, tenantID)
	if err != nil {
		return fmt.Errorf("failed to delete mcp server: %w", err)
	}
	if result.RowsAffected() == 0 {
		return ErrMCPServerNotFound
	}
	return nil
}

func (s *MCPStore) ReplaceAgentMCPBindings(agentID string, serverIDs []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `DELETE FROM agent_mcp_bindings WHERE agent_definition_id = $1`, agentID); err != nil {
		return fmt.Errorf("failed to clear agent mcp bindings: %w", err)
	}
	for _, serverID := range serverIDs {
		if _, err := tx.Exec(ctx, `
			INSERT INTO agent_mcp_bindings (agent_definition_id, server_id, metadata)
			VALUES ($1, $2, '{}'::jsonb)
		`, agentID, serverID); err != nil {
			return fmt.Errorf("failed to bind mcp server %s: %w", serverID, err)
		}
	}
	return tx.Commit(ctx)
}

func (s *MCPStore) ListAgentMCPBindings(agentID string) ([]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT server_id
		FROM agent_mcp_bindings
		WHERE agent_definition_id = $1
		ORDER BY created_at ASC
	`, agentID)
	if err != nil {
		return nil, fmt.Errorf("failed to list agent mcp bindings: %w", err)
	}
	defer rows.Close()

	var items []string
	for rows.Next() {
		var serverID string
		if err := rows.Scan(&serverID); err != nil {
			return nil, fmt.Errorf("failed to scan agent mcp binding: %w", err)
		}
		items = append(items, serverID)
	}
	return items, rows.Err()
}

func (s *MCPStore) ListServerBindingAgents(serverID, tenantID string, limit int) ([]*MCPBindingAgent, int, error) {
	if limit <= 0 {
		limit = 5
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var totalCount int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM agent_mcp_bindings bindings
		INNER JOIN agent_definitions agents ON agents.id = bindings.agent_definition_id
		WHERE bindings.server_id = $1 AND agents.tenant_id = $2
	`, serverID, tenantID).Scan(&totalCount); err != nil {
		return nil, 0, fmt.Errorf("failed to count mcp server bindings: %w", err)
	}

	rows, err := s.pool.Query(ctx, `
		SELECT agents.id, agents.name, agents.status
		FROM agent_mcp_bindings bindings
		INNER JOIN agent_definitions agents ON agents.id = bindings.agent_definition_id
		WHERE bindings.server_id = $1 AND agents.tenant_id = $2
		ORDER BY agents.updated_at DESC, agents.created_at DESC, agents.name ASC
		LIMIT $3
	`, serverID, tenantID, limit)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to list mcp server binding agents: %w", err)
	}
	defer rows.Close()

	agents := make([]*MCPBindingAgent, 0, min(limit, totalCount))
	for rows.Next() {
		agent := &MCPBindingAgent{}
		if err := rows.Scan(&agent.AgentID, &agent.Name, &agent.Status); err != nil {
			return nil, 0, fmt.Errorf("failed to scan mcp server binding agent: %w", err)
		}
		agents = append(agents, agent)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	return agents, totalCount, nil
}

func (s *MCPStore) ReplaceServerTools(serverID string, tools []*MCPServerTool) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `DELETE FROM mcp_server_tools WHERE server_id = $1`, serverID); err != nil {
		return fmt.Errorf("failed to clear mcp tools: %w", err)
	}
	for _, tool := range tools {
		if _, err := tx.Exec(ctx, `
			INSERT INTO mcp_server_tools (server_id, tool_name, description, input_schema, metadata)
			VALUES ($1, $2, $3, $4, $5)
		`,
			serverID,
			tool.ToolName,
			nullIfEmpty(tool.Description),
			normalizeJSONRaw(tool.InputSchema, `{}`),
			normalizeJSONRaw(tool.Metadata, `{}`),
		); err != nil {
			return fmt.Errorf("failed to insert mcp tool %s: %w", tool.ToolName, err)
		}
	}
	return tx.Commit(ctx)
}

func (s *MCPStore) ListServerTools(serverID string) ([]*MCPServerTool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	rows, err := s.pool.Query(ctx, `
		SELECT id, server_id, tool_name, description, input_schema, metadata, discovered_at, created_at, updated_at
		FROM mcp_server_tools
		WHERE server_id = $1
		ORDER BY tool_name ASC
	`, serverID)
	if err != nil {
		return nil, fmt.Errorf("failed to list mcp server tools: %w", err)
	}
	defer rows.Close()

	var items []*MCPServerTool
	for rows.Next() {
		item := &MCPServerTool{}
		if err := scanMCPServerTool(rows, item); err != nil {
			return nil, fmt.Errorf("failed to scan mcp server tool: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func scanMCPServer(scanner rowScanner, row *MCPServer) error {
	var endpoint sql.NullString
	var command sql.NullString

	if err := scanner.Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Transport,
		&endpoint,
		&command,
		&row.Args,
		&row.Env,
		&row.Status,
		&row.LastTestedAt,
		&row.LastError,
		&row.Metadata,
		&row.CreatedBy,
		&row.UpdatedBy,
		&row.CreatedAt,
		&row.UpdatedAt,
	); err != nil {
		return err
	}

	row.Endpoint = nullableStringValue(endpoint)
	row.Command = nullableStringValue(command)
	return nil
}

func scanMCPServerTool(scanner rowScanner, row *MCPServerTool) error {
	var description sql.NullString

	if err := scanner.Scan(
		&row.ID,
		&row.ServerID,
		&row.ToolName,
		&description,
		&row.InputSchema,
		&row.Metadata,
		&row.DiscoveredAt,
		&row.CreatedAt,
		&row.UpdatedAt,
	); err != nil {
		return err
	}

	row.Description = nullableStringValue(description)
	return nil
}

func nullableStringValue(value sql.NullString) string {
	if !value.Valid {
		return ""
	}
	return value.String
}
