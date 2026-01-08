package service

import (
	"sync"
	"time"
)

// Session represents a chat session
type Session struct {
	ID        string
	UserID    string
	Messages  []Message
	CreatedAt time.Time
	UpdatedAt time.Time
	mu        sync.RWMutex
}

// Message represents a chat message
type Message struct {
	Role      string
	Content   string
	Timestamp time.Time
}

// SessionManager manages chat sessions
type SessionManager struct {
	mu       sync.RWMutex
	sessions map[string]*Session
}

// NewSessionManager creates a new session manager
func NewSessionManager() *SessionManager {
	sm := &SessionManager{
		sessions: make(map[string]*Session),
	}

	// Start cleanup goroutine
	go sm.cleanup()

	return sm
}

// GetOrCreate gets or creates a session
func (sm *SessionManager) GetOrCreate(sessionID, userID string) *Session {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	session, exists := sm.sessions[sessionID]
	if !exists {
		session = &Session{
			ID:        sessionID,
			UserID:    userID,
			Messages:  make([]Message, 0),
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
		sm.sessions[sessionID] = session
	}

	return session
}

// Get gets a session by ID
func (sm *SessionManager) Get(sessionID string) (*Session, bool) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	session, exists := sm.sessions[sessionID]
	return session, exists
}

// Delete deletes a session
func (sm *SessionManager) Delete(sessionID string) {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	delete(sm.sessions, sessionID)
}

// AddMessage adds a message to the session
func (s *Session) AddMessage(role, content string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.Messages = append(s.Messages, Message{
		Role:      role,
		Content:   content,
		Timestamp: time.Now(),
	})
	s.UpdatedAt = time.Now()
}

// GetMessages returns session messages
func (s *Session) GetMessages() []Message {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// Return copy
	messages := make([]Message, len(s.Messages))
	copy(messages, s.Messages)
	return messages
}

// cleanup removes old sessions periodically
func (sm *SessionManager) cleanup() {
	ticker := time.NewTicker(30 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		sm.mu.Lock()
		now := time.Now()
		for id, session := range sm.sessions {
			// Remove sessions older than 24 hours
			if now.Sub(session.UpdatedAt) > 24*time.Hour {
				delete(sm.sessions, id)
			}
		}
		sm.mu.Unlock()
	}
}
