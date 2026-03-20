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

var ErrMCPServerNotFound = errors.New("mcp server not found")

type MCPServer struct {
	ID           string          `json:"id"`
	TenantID     string          `json:"tenant_id"`
	Name         string          `json:"name"`
	Transport    string          `json:"transport"`
	Endpoint     string          `json:"endpoint,omitempty"`
	Command      string          `json:"command,omitempty"`
	Args         json.RawMessage `json:"args"`
	Env          json.RawMessage `json:"env"`
	Status       string          `json:"status"`
	LastTestedAt *time.Time      `json:"last_tested_at,omitempty"`
	LastError    *string         `json:"last_error,omitempty"`
	Metadata     json.RawMessage `json:"metadata"`
	CreatedBy    *string         `json:"created_by,omitempty"`
	UpdatedBy    *string         `json:"updated_by,omitempty"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type MCPServerTool struct {
	ID           string          `json:"id"`
	ServerID     string          `json:"server_id"`
	ToolName     string          `json:"tool_name"`
	Description  string          `json:"description,omitempty"`
	InputSchema  json.RawMessage `json:"input_schema"`
	Metadata     json.RawMessage `json:"metadata"`
	DiscoveredAt time.Time       `json:"discovered_at"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

type MCPStore struct {
	pool *pgxpool.Pool
}

func NewMCPStore(pool *pgxpool.Pool) *MCPStore {
	return &MCPStore{pool: pool}
}

func (s *MCPStore) CreateServer(server *MCPServer) (*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	row := &MCPServer{}
	err := s.pool.QueryRow(ctx, `
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
	).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Transport,
		&row.Endpoint,
		&row.Command,
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
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create mcp server: %w", err)
	}
	return row, nil
}

func (s *MCPStore) UpdateServer(server *MCPServer) (*MCPServer, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	row := &MCPServer{}
	err := s.pool.QueryRow(ctx, `
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
	).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Transport,
		&row.Endpoint,
		&row.Command,
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
	)
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
	err := s.pool.QueryRow(ctx, `
		SELECT id, tenant_id, name, transport, endpoint, command, args, env,
		       status, last_tested_at, last_error, metadata, created_by, updated_by,
		       created_at, updated_at
		FROM mcp_servers
		WHERE id = $1 AND tenant_id = $2
	`, id, tenantID).Scan(
		&row.ID,
		&row.TenantID,
		&row.Name,
		&row.Transport,
		&row.Endpoint,
		&row.Command,
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
	)
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
		if err := rows.Scan(
			&item.ID,
			&item.TenantID,
			&item.Name,
			&item.Transport,
			&item.Endpoint,
			&item.Command,
			&item.Args,
			&item.Env,
			&item.Status,
			&item.LastTestedAt,
			&item.LastError,
			&item.Metadata,
			&item.CreatedBy,
			&item.UpdatedBy,
			&item.CreatedAt,
			&item.UpdatedAt,
		); err != nil {
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
