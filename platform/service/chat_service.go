package service

import (
	"context"
	"fmt"

	"github.com/ai-platform/platform/api/grpc"
)

// ChatService handles chat business logic
type ChatService struct {
	aiClient *grpc.AIClient
	sessions *SessionManager
}

// NewChatService creates a new chat service
func NewChatService(aiClient *grpc.AIClient) *ChatService {
	return &ChatService{
		aiClient: aiClient,
		sessions: NewSessionManager(),
	}
}

// StreamChat handles streaming chat requests
func (s *ChatService) StreamChat(ctx context.Context, req *ChatRequest) (<-chan *ChatMessage, error) {
	// Validate request
	if err := s.validateRequest(req); err != nil {
		return nil, err
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
