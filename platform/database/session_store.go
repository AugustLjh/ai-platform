package database

import (
	"context"
	"errors"
	"fmt"
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
		INSERT INTO messages (id, session_id, role, content, token_count, model, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`

	_, err = tx.Exec(ctx, query,
		message.ID,
		message.SessionID,
		message.Role,
		message.Content,
		message.TokenCount,
		message.Model,
		message.CreatedAt,
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
		SELECT id, session_id, role, content, token_count, model, created_at
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
		err := rows.Scan(
			&message.ID,
			&message.SessionID,
			&message.Role,
			&message.Content,
			&message.TokenCount,
			&message.Model,
			&message.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan message: %w", err)
		}
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
