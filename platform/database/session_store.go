package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Session represents a chat session
type Session struct {
	ID            string
	UserID        string
	TenantID      string
	Title         string
	CreatedAt     time.Time
	UpdatedAt     time.Time
	LastMessageAt *time.Time
}

// Message represents a chat message
type Message struct {
	ID         string
	SessionID  string
	Role       string
	Content    string
	TokenCount int
	Model      string
	CreatedAt  time.Time
	Metadata   map[string]string
}

type UsageSummary struct {
	TotalCost    float64
	TotalTokens  int64
	RequestCount int64
}

type UsageDimension struct {
	Key          string
	Label        string
	TotalCost    float64
	TotalTokens  int64
	RequestCount int64
}

type UsageStats struct {
	CurrentUser     UsageSummary
	CurrentTenant   UsageSummary
	ByKnowledgeBase []UsageDimension
	ByFeature       []UsageDimension
	ByModel         []UsageDimension
}

type LowQualitySample struct {
	MessageID       string
	SessionID       string
	SessionTitle    string
	Content         string
	CreatedAt       time.Time
	KnowledgeBaseID string
	KnowledgeBase   string
	FeedbackLabel   string
	FeedbackComment string
	FeedbackRating  float64
	Metadata        map[string]string
}

// SessionStore manages chat sessions
type SessionStore struct {
	pool *pgxpool.Pool
}

// NewSessionStore creates a new session store
func NewSessionStore(pool *pgxpool.Pool) *SessionStore {
	return &SessionStore{pool: pool}
}

// CreateSession creates a new chat session
func (s *SessionStore) CreateSession(session *Session) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		INSERT INTO sessions (id, user_id, tenant_id, title, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`

	now := time.Now()
	if session.CreatedAt.IsZero() {
		session.CreatedAt = now
	}
	if session.UpdatedAt.IsZero() {
		session.UpdatedAt = now
	}

	_, err := s.pool.Exec(ctx, query,
		session.ID,
		session.UserID,
		session.TenantID,
		session.Title,
		session.CreatedAt,
		session.UpdatedAt,
	)

	if err != nil {
		return fmt.Errorf("failed to create session: %w", err)
	}

	return nil
}

// GetSession retrieves a session by ID
func (s *SessionStore) GetSession(sessionID string) (*Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		SELECT id, user_id, tenant_id, title, created_at, updated_at, last_message_at
		FROM sessions
		WHERE id = $1
	`

	session := &Session{}
	err := s.pool.QueryRow(ctx, query, sessionID).Scan(
		&session.ID,
		&session.UserID,
		&session.TenantID,
		&session.Title,
		&session.CreatedAt,
		&session.UpdatedAt,
		&session.LastMessageAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, fmt.Errorf("session not found")
		}
		return nil, fmt.Errorf("failed to get session: %w", err)
	}

	return session, nil
}

// ListUserSessions lists all sessions for a user
func (s *SessionStore) ListUserSessions(userID, query string, limit, offset int) ([]*Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	baseQuery := `
		SELECT id, user_id, tenant_id, title, created_at, updated_at, last_message_at
		FROM sessions
		WHERE user_id = $1
	`

	args := []interface{}{userID}

	if query != "" {
		args = append(args, "%"+query+"%")
		searchPos := len(args)
		baseQuery += fmt.Sprintf(`
			AND (
				title ILIKE $%d
				OR EXISTS (
					SELECT 1 FROM messages m
					WHERE m.session_id = sessions.id
					AND m.content ILIKE $%d
				)
			)
		`, searchPos, searchPos)
	}

	args = append(args, limit, offset)
	limitPos := len(args) - 1
	offsetPos := len(args)

	baseQuery += fmt.Sprintf(`
		ORDER BY COALESCE(last_message_at, created_at) DESC
		LIMIT $%d OFFSET $%d
	`, limitPos, offsetPos)

	rows, err := s.pool.Query(ctx, baseQuery, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list sessions: %w", err)
	}
	defer rows.Close()

	var sessions []*Session
	for rows.Next() {
		session := &Session{}
		err := rows.Scan(
			&session.ID,
			&session.UserID,
			&session.TenantID,
			&session.Title,
			&session.CreatedAt,
			&session.UpdatedAt,
			&session.LastMessageAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan session: %w", err)
		}
		sessions = append(sessions, session)
	}

	return sessions, nil
}

// AddMessage adds a message to a session
func (s *SessionStore) AddMessage(message *Message) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if message.CreatedAt.IsZero() {
		message.CreatedAt = time.Now()
	}

	// Start transaction
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	// Insert message
	query := `
		INSERT INTO messages (id, session_id, role, content, token_count, model, created_at, metadata)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`

	metadataJSON, err := json.Marshal(normalizeMetadata(message.Metadata))
	if err != nil {
		return fmt.Errorf("failed to marshal message metadata: %w", err)
	}

	_, err = tx.Exec(ctx, query,
		message.ID,
		message.SessionID,
		message.Role,
		message.Content,
		message.TokenCount,
		message.Model,
		message.CreatedAt,
		metadataJSON,
	)

	if err != nil {
		return fmt.Errorf("failed to add message: %w", err)
	}

	// Update session last_message_at
	updateQuery := `
		UPDATE sessions
		SET last_message_at = $2, updated_at = $2
		WHERE id = $1
	`

	_, err = tx.Exec(ctx, updateQuery, message.SessionID, message.CreatedAt)
	if err != nil {
		return fmt.Errorf("failed to update session: %w", err)
	}

	// Commit transaction
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// GetSessionMessages retrieves messages for a session
func (s *SessionStore) GetSessionMessages(sessionID string, limit, offset int) ([]*Message, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	query := `
		SELECT id, session_id, role, content, token_count, model, created_at, metadata
		FROM messages
		WHERE session_id = $1
		ORDER BY created_at ASC
		LIMIT $2 OFFSET $3
	`

	rows, err := s.pool.Query(ctx, query, sessionID, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("failed to get messages: %w", err)
	}
	defer rows.Close()

	var messages []*Message
	for rows.Next() {
		message := &Message{}
		var metadataBytes []byte
		err := rows.Scan(
			&message.ID,
			&message.SessionID,
			&message.Role,
			&message.Content,
			&message.TokenCount,
			&message.Model,
			&message.CreatedAt,
			&metadataBytes,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan message: %w", err)
		}
		message.Metadata = parseMetadata(metadataBytes)
		messages = append(messages, message)
	}

	return messages, nil
}

// DeleteSession deletes a session and all its messages
func (s *SessionStore) DeleteSession(sessionID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `DELETE FROM sessions WHERE id = $1`

	result, err := s.pool.Exec(ctx, query, sessionID)
	if err != nil {
		return fmt.Errorf("failed to delete session: %w", err)
	}

	if result.RowsAffected() == 0 {
		return fmt.Errorf("session not found")
	}

	return nil
}

// UpdateSessionTitle updates the session title
func (s *SessionStore) UpdateSessionTitle(sessionID, title string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	query := `
		UPDATE sessions
		SET title = $2, updated_at = $3
		WHERE id = $1
	`

	_, err := s.pool.Exec(ctx, query, sessionID, title, time.Now())
	if err != nil {
		return fmt.Errorf("failed to update session title: %w", err)
	}

	return nil
}

func (s *SessionStore) SaveMessageFeedback(userID, messageID string, updates map[string]string) (*Message, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	selectQuery := `
		SELECT m.id, m.session_id, m.role, m.content, m.token_count, m.model, m.created_at, m.metadata
		FROM messages m
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE m.id = $1 AND s.user_id = $2
	`

	var metadataBytes []byte
	message := &Message{}
	err := s.pool.QueryRow(ctx, selectQuery, messageID, userID).Scan(
		&message.ID,
		&message.SessionID,
		&message.Role,
		&message.Content,
		&message.TokenCount,
		&message.Model,
		&message.CreatedAt,
		&metadataBytes,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, fmt.Errorf("message not found")
		}
		return nil, fmt.Errorf("failed to load message: %w", err)
	}

	message.Metadata = parseMetadata(metadataBytes)
	for key, value := range updates {
		if value == "" {
			delete(message.Metadata, key)
			continue
		}
		message.Metadata[key] = value
	}

	normalizedMetadata := normalizeMetadata(message.Metadata)
	payload, err := json.Marshal(normalizedMetadata)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal feedback metadata: %w", err)
	}

	updateQuery := `
		UPDATE messages
		SET metadata = $2
		WHERE id = $1
	`

	if _, err := s.pool.Exec(ctx, updateQuery, messageID, payload); err != nil {
		return nil, fmt.Errorf("failed to update message feedback: %w", err)
	}

	message.Metadata = normalizedMetadata
	return message, nil
}

func (s *SessionStore) ListLowQualitySamples(userID, knowledgeBaseID string, limit int) ([]*LowQualitySample, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if limit <= 0 {
		limit = 20
	}

	query := `
		SELECT
			m.id,
			m.session_id,
			COALESCE(s.title, '新对话') AS session_title,
			m.content,
			m.created_at,
			m.metadata
		FROM messages m
		INNER JOIN sessions s ON s.id = m.session_id
		WHERE s.user_id = $1
		  AND m.role = 'assistant'
		  AND COALESCE(m.metadata->>'low_quality', 'false') = 'true'
		  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
		ORDER BY m.created_at DESC
		LIMIT $3
	`

	rows, err := s.pool.Query(ctx, query, userID, knowledgeBaseID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query low quality samples: %w", err)
	}
	defer rows.Close()

	samples := make([]*LowQualitySample, 0)
	for rows.Next() {
		sample := &LowQualitySample{}
		var metadataBytes []byte
		if err := rows.Scan(
			&sample.MessageID,
			&sample.SessionID,
			&sample.SessionTitle,
			&sample.Content,
			&sample.CreatedAt,
			&metadataBytes,
		); err != nil {
			return nil, fmt.Errorf("failed to scan low quality sample: %w", err)
		}

		sample.Metadata = parseMetadata(metadataBytes)
		sample.KnowledgeBaseID = sample.Metadata["knowledge_base_id"]
		sample.KnowledgeBase = sample.Metadata["knowledge_base_name"]
		sample.FeedbackLabel = sample.Metadata["feedback_label"]
		sample.FeedbackComment = sample.Metadata["feedback_comment"]
		sample.FeedbackRating = parseFloat(sample.Metadata["feedback_rating"])
		samples = append(samples, sample)
	}

	return samples, nil
}

func (s *SessionStore) GetUsageStats(userID, tenantID, knowledgeBaseID string) (*UsageStats, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	stats := &UsageStats{}

	currentUserSummary, err := s.queryUsageSummary(
		ctx,
		`
			SELECT
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'cost_usd', ''), '0')::double precision), 0) AS total_cost,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'total_tokens', ''), '0')::bigint), 0) AS total_tokens,
				COUNT(*) AS request_count
			FROM messages m
			INNER JOIN sessions s ON s.id = m.session_id
			WHERE s.user_id = $1
			  AND m.role = 'assistant'
			  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
		`,
		userID,
		knowledgeBaseID,
	)
	if err != nil {
		return nil, err
	}
	stats.CurrentUser = *currentUserSummary

	currentTenantSummary, err := s.queryUsageSummary(
		ctx,
		`
			SELECT
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'cost_usd', ''), '0')::double precision), 0) AS total_cost,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'total_tokens', ''), '0')::bigint), 0) AS total_tokens,
				COUNT(*) AS request_count
			FROM messages m
			INNER JOIN sessions s ON s.id = m.session_id
			WHERE s.tenant_id = $1
			  AND m.role = 'assistant'
			  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
		`,
		tenantID,
		knowledgeBaseID,
	)
	if err != nil {
		return nil, err
	}
	stats.CurrentTenant = *currentTenantSummary

	stats.ByKnowledgeBase, err = s.queryUsageDimensions(
		ctx,
		`
			SELECT
				COALESCE(NULLIF(m.metadata->>'knowledge_base_id', ''), 'none') AS key,
				COALESCE(NULLIF(m.metadata->>'knowledge_base_name', ''), '未绑定知识库') AS label,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'cost_usd', ''), '0')::double precision), 0) AS total_cost,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'total_tokens', ''), '0')::bigint), 0) AS total_tokens,
				COUNT(*) AS request_count
			FROM messages m
			INNER JOIN sessions s ON s.id = m.session_id
			WHERE s.tenant_id = $1
			  AND m.role = 'assistant'
			  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
			GROUP BY 1, 2
			ORDER BY total_cost DESC, total_tokens DESC
			LIMIT 20
		`,
		tenantID,
		knowledgeBaseID,
	)
	if err != nil {
		return nil, err
	}

	stats.ByFeature, err = s.queryUsageDimensions(
		ctx,
		`
			SELECT
				COALESCE(NULLIF(m.metadata->>'feature_code', ''), 'chat') AS key,
				COALESCE(NULLIF(m.metadata->>'feature_code', ''), 'chat') AS label,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'cost_usd', ''), '0')::double precision), 0) AS total_cost,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'total_tokens', ''), '0')::bigint), 0) AS total_tokens,
				COUNT(*) AS request_count
			FROM messages m
			INNER JOIN sessions s ON s.id = m.session_id
			WHERE s.tenant_id = $1
			  AND m.role = 'assistant'
			  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
			GROUP BY 1, 2
			ORDER BY total_cost DESC, total_tokens DESC
			LIMIT 20
		`,
		tenantID,
		knowledgeBaseID,
	)
	if err != nil {
		return nil, err
	}

	stats.ByModel, err = s.queryUsageDimensions(
		ctx,
		`
			SELECT
				COALESCE(NULLIF(m.metadata->>'resolved_model_id', ''), 'unknown') AS key,
				COALESCE(NULLIF(m.metadata->>'resolved_model_name', ''), COALESCE(NULLIF(m.metadata->>'resolved_provider_model_id', ''), 'unknown')) AS label,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'cost_usd', ''), '0')::double precision), 0) AS total_cost,
				COALESCE(SUM(COALESCE(NULLIF(m.metadata->>'total_tokens', ''), '0')::bigint), 0) AS total_tokens,
				COUNT(*) AS request_count
			FROM messages m
			INNER JOIN sessions s ON s.id = m.session_id
			WHERE s.tenant_id = $1
			  AND m.role = 'assistant'
			  AND ($2 = '' OR COALESCE(m.metadata->>'knowledge_base_id', '') = $2)
			GROUP BY 1, 2
			ORDER BY total_cost DESC, total_tokens DESC
			LIMIT 20
		`,
		tenantID,
		knowledgeBaseID,
	)
	if err != nil {
		return nil, err
	}

	return stats, nil
}

func normalizeMetadata(metadata map[string]string) map[string]string {
	if metadata == nil {
		return map[string]string{}
	}
	return metadata
}

func (s *SessionStore) queryUsageSummary(ctx context.Context, query string, args ...interface{}) (*UsageSummary, error) {
	summary := &UsageSummary{}
	if err := s.pool.QueryRow(ctx, query, args...).Scan(
		&summary.TotalCost,
		&summary.TotalTokens,
		&summary.RequestCount,
	); err != nil {
		return nil, fmt.Errorf("failed to query usage summary: %w", err)
	}
	return summary, nil
}

func (s *SessionStore) queryUsageDimensions(ctx context.Context, query string, args ...interface{}) ([]UsageDimension, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query usage dimensions: %w", err)
	}
	defer rows.Close()

	items := make([]UsageDimension, 0)
	for rows.Next() {
		var item UsageDimension
		if err := rows.Scan(
			&item.Key,
			&item.Label,
			&item.TotalCost,
			&item.TotalTokens,
			&item.RequestCount,
		); err != nil {
			return nil, fmt.Errorf("failed to scan usage dimension: %w", err)
		}
		items = append(items, item)
	}

	return items, nil
}

func parseFloat(raw string) float64 {
	if raw == "" {
		return 0
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0
	}
	return value
}

func parseMetadata(raw []byte) map[string]string {
	if len(raw) == 0 {
		return map[string]string{}
	}

	var metadata map[string]string
	if err := json.Unmarshal(raw, &metadata); err != nil {
		return map[string]string{}
	}
	if metadata == nil {
		return map[string]string{}
	}
	return metadata
}
