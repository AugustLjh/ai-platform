package service

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"

	"github.com/ai-platform/platform/api/grpc"
	"github.com/ai-platform/platform/database"
	"github.com/google/uuid"
)

// ChatService handles chat business logic
type ChatService struct {
	aiClient *grpc.AIClient
	sessions *SessionManager
	sessionStore *database.SessionStore
}

// NewChatService creates a new chat service
func NewChatService(aiClient *grpc.AIClient, sessionStore *database.SessionStore) *ChatService {
	return &ChatService{
		aiClient: aiClient,
		sessions: NewSessionManager(),
		sessionStore: sessionStore,
	}
}

var (
	ErrSessionNotFound = errors.New("session not found")
	ErrUnauthorized    = errors.New("unauthorized")
)

// StreamChat handles streaming chat requests
func (s *ChatService) StreamChat(ctx context.Context, req *ChatRequest) (<-chan *ChatMessage, error) {
	// Validate request
	if err := s.validateRequest(req); err != nil {
		return nil, err
	}

	modelName := ""
	if req.Config != nil {
		modelName = req.Config.Model
	}

	var dbSession *database.Session
	if s.sessionStore != nil {
		session, err := s.ensureDBSession(req)
		if err != nil {
			if errors.Is(err, ErrUnauthorized) {
				return nil, err
			}
			log.Printf("[ChatService] Failed to ensure session: %v", err)
		} else {
			dbSession = session
			if err := s.persistMessage(req.SessionID, "user", req.Message, modelName); err != nil {
				log.Printf("[ChatService] Failed to persist user message: %v", err)
			}
			s.maybeUpdateTitle(dbSession, req.Message)
		}
	}

	// Get or create session
	session := s.sessions.GetOrCreate(req.SessionID, req.UserID)

	// Add user message to session
	session.AddMessage("user", req.Message)

	// Create gRPC request
	grpcReq := &grpc.ChatRequest{
		SessionID: req.SessionID,
		UserID:    req.UserID,
		TenantID:  req.TenantID,
		Message:   req.Message,
		Metadata:  req.Metadata,
		Config: &grpc.ChatConfig{
			Model:       req.Config.Model,
			Temperature: req.Config.Temperature,
			MaxTokens:   req.Config.MaxTokens,
			UseRAG:      req.Config.UseRAG,
			UseAgent:    req.Config.UseAgent,
			Tools:       req.Config.Tools,
		},
	}

	// Stream from AI runtime
	aiChan, err := s.aiClient.StreamChat(ctx, grpcReq)
	if err != nil {
		return nil, fmt.Errorf("failed to stream from AI runtime: %w", err)
	}

	// Create output channel
	outChan := make(chan *ChatMessage, 100)

	// Forward messages from AI runtime to output
	go func() {
		defer close(outChan)

		fullResponse := ""

		for msg := range aiChan {
			// Forward message
			outChan <- &ChatMessage{
				SessionID: msg.SessionID,
				MessageID: msg.MessageID,
				Type:      msg.Type,
				Content:   msg.Content,
				Error:     msg.Error,
				Metadata:  msg.Metadata,
			}

			// Accumulate response
			if msg.Type == 1 { // CONTENT
				fullResponse += msg.Content
			}

			// Save to session on completion
			if msg.Type == 4 { // COMPLETE
				session.AddMessage("assistant", fullResponse)
				if s.sessionStore != nil {
					if err := s.persistMessage(req.SessionID, "assistant", fullResponse, modelName); err != nil {
						log.Printf("[ChatService] Failed to persist assistant message: %v", err)
					}
				}
			}
		}
	}()

	return outChan, nil
}

// validateRequest validates chat request
func (s *ChatService) validateRequest(req *ChatRequest) error {
	if req.SessionID == "" {
		return fmt.Errorf("session_id is required")
	}
	if req.UserID == "" {
		return fmt.Errorf("user_id is required")
	}
	if req.Message == "" {
		return fmt.Errorf("message is required")
	}
	return nil
}

func (s *ChatService) ensureDBSession(req *ChatRequest) (*database.Session, error) {
	if s.sessionStore == nil {
		return nil, nil
	}

	session, err := s.sessionStore.GetSession(req.SessionID)
	if err != nil {
		if isSessionNotFound(err) {
			newSession := &database.Session{
				ID:       req.SessionID,
				UserID:   req.UserID,
				TenantID: req.TenantID,
				Title:    "新对话",
			}
			if createErr := s.sessionStore.CreateSession(newSession); createErr != nil {
				return nil, createErr
			}
			return newSession, nil
		}
		return nil, err
	}

	if session.UserID != req.UserID {
		return nil, ErrUnauthorized
	}

	return session, nil
}

func (s *ChatService) persistMessage(sessionID, role, content, model string) error {
	if s.sessionStore == nil {
		return nil
	}

	message := &database.Message{
		ID:        uuid.NewString(),
		SessionID: sessionID,
		Role:      role,
		Content:   content,
		TokenCount: 0,
		Model:     model,
	}

	return s.sessionStore.AddMessage(message)
}

func (s *ChatService) maybeUpdateTitle(session *database.Session, message string) {
	if s.sessionStore == nil || session == nil {
		return
	}
	if session.Title != "" && session.Title != "新对话" {
		return
	}

	trimmed := strings.TrimSpace(message)
	if trimmed == "" {
		return
	}

	maxLen := 30
	runes := []rune(trimmed)
	if len(runes) > maxLen {
		trimmed = string(runes[:maxLen]) + "..."
	}

	if err := s.sessionStore.UpdateSessionTitle(session.ID, trimmed); err != nil {
		log.Printf("[ChatService] Failed to update session title: %v", err)
		return
	}
	session.Title = trimmed
}

func (s *ChatService) ListSessions(userID, query string, limit, offset int) ([]*database.Session, error) {
	if s.sessionStore == nil {
		return nil, fmt.Errorf("session store not configured")
	}
	return s.sessionStore.ListUserSessions(userID, query, limit, offset)
}

func (s *ChatService) GetSessionMessages(userID, sessionID string, limit, offset int) ([]*database.Message, error) {
	if s.sessionStore == nil {
		return nil, fmt.Errorf("session store not configured")
	}

	session, err := s.sessionStore.GetSession(sessionID)
	if err != nil {
		if isSessionNotFound(err) {
			return nil, ErrSessionNotFound
		}
		return nil, err
	}
	if session.UserID != userID {
		return nil, ErrUnauthorized
	}

	return s.sessionStore.GetSessionMessages(sessionID, limit, offset)
}

func (s *ChatService) DeleteSession(userID, sessionID string) error {
	if s.sessionStore == nil {
		return fmt.Errorf("session store not configured")
	}

	session, err := s.sessionStore.GetSession(sessionID)
	if err != nil {
		if isSessionNotFound(err) {
			return ErrSessionNotFound
		}
		return err
	}
	if session.UserID != userID {
		return ErrUnauthorized
	}

	if err := s.sessionStore.DeleteSession(sessionID); err != nil {
		if isSessionNotFound(err) {
			return ErrSessionNotFound
		}
		return err
	}

	return nil
}

func (s *ChatService) CreateSession(userID, tenantID, sessionID, title string) (*database.Session, error) {
	if s.sessionStore == nil {
		return nil, fmt.Errorf("session store not configured")
	}
	if sessionID == "" {
		sessionID = uuid.NewString()
	}
	if title == "" {
		title = "新对话"
	}

	existing, err := s.sessionStore.GetSession(sessionID)
	if err == nil {
		if existing.UserID != userID {
			return nil, ErrUnauthorized
		}
		return existing, nil
	}
	if err != nil && !isSessionNotFound(err) {
		return nil, err
	}

	session := &database.Session{
		ID:       sessionID,
		UserID:   userID,
		TenantID: tenantID,
		Title:    title,
	}
	if err := s.sessionStore.CreateSession(session); err != nil {
		return nil, err
	}

	return session, nil
}

func isSessionNotFound(err error) bool {
	if err == nil {
		return false
	}
	return strings.Contains(strings.ToLower(err.Error()), "session not found")
}

// ChatRequest represents a chat request
type ChatRequest struct {
	SessionID string
	UserID    string
	TenantID  string
	Message   string
	Metadata  map[string]string
	Config    *ChatConfig
}

// ChatConfig holds chat configuration
type ChatConfig struct {
	Model       string
	Temperature float32
	MaxTokens   int32
	UseRAG      bool
	UseAgent    bool
	Tools       []string
	KnowledgeBaseID string
}

// ChatMessage represents a chat message
type ChatMessage struct {
	SessionID string            
	MessageID string            
	Type      int32             
	Content   string            
	Error     string            
	Metadata  map[string]string 
}
