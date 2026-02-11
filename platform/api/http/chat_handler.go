package http

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/ai-platform/platform/database"
	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
	"github.com/gorilla/websocket"
)

// ChatHandler handles chat HTTP requests
type ChatHandler struct {
	chatService *service.ChatService
	costTracker *middleware.CostTracker
	upgrader    websocket.Upgrader
}

// NewChatHandler creates a new chat handler
func NewChatHandler(chatService *service.ChatService, costTracker *middleware.CostTracker) *ChatHandler {
	return &ChatHandler{
		chatService: chatService,
		costTracker: costTracker,
		upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool {
				origin := r.Header.Get("Origin")
				allowedOrigins := []string{
					"http://localhost:3000",
					"http://localhost:8080",
					os.Getenv("FRONTEND_URL"),
				}
				for _, allowed := range allowedOrigins {
					if origin == allowed {
						return true
					}
				}
				log.Printf("[Security] Rejected WebSocket from origin: %s", origin)
				return false
			},
		},
	}
}

// HandleSSE handles Server-Sent Events streaming
func (h *ChatHandler) HandleSSE(w http.ResponseWriter, r *http.Request) {
	// Set SSE headers
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Parse request
	var req ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}

	// Set user info
	req.UserID = user.ID
	req.TenantID = user.TenantID

	// Convert to service request
	serviceReq := h.toServiceRequest(&req)

	// Stream chat
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	messageChan, err := h.chatService.StreamChat(ctx, serviceReq)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to start chat: %v", err), http.StatusInternalServerError)
		return
	}

	// Get flusher for SSE
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	// Stream messages
	totalInputTokens := int64(0)
	totalOutputTokens := int64(0)

	for {
		select {
		case <-ctx.Done():
			return

		case msg, ok := <-messageChan:
			if !ok {
				// Channel closed
				return
			}

			// Send SSE message
			data, err := json.Marshal(msg)
			if err != nil {
				log.Printf("[SSE] Failed to marshal message: %v", err)
				continue
			}
			fmt.Fprintf(w, "data: %s\n\n", data)
			flusher.Flush()

			// Track tokens on completion
			if msg.Type == 4 { // COMPLETE
				// In production, extract token counts from msg.Metadata
				totalInputTokens = 100  // Mock
				totalOutputTokens = 200 // Mock

				h.costTracker.TrackTokens(user.ID, totalInputTokens, totalOutputTokens)
			}
		}
	}
}

// HandleWebSocket handles WebSocket connections
func (h *ChatHandler) HandleWebSocket(w http.ResponseWriter, r *http.Request) {
	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Upgrade to WebSocket
	conn, err := h.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("Failed to upgrade to WebSocket: %v", err)
		return
	}
	defer conn.Close()

	log.Printf("[WebSocket] New connection from user: %s", user.ID)

	// Read messages from client
	for {
		var req ChatRequest
		if err := conn.ReadJSON(&req); err != nil {
			log.Printf("WebSocket read error: %v", err)
			break
		}

		// Set user info
		req.UserID = user.ID
		req.TenantID = user.TenantID

		// Convert to service request
		serviceReq := h.toServiceRequest(&req)

		// Stream chat
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
		defer cancel() // Ensure cleanup in all paths

		messageChan, err := h.chatService.StreamChat(ctx, serviceReq)
		if err != nil {
			conn.WriteJSON(map[string]string{
				"error": fmt.Sprintf("Failed to start chat: %v", err),
			})
			cancel()
			continue
		}

		// Stream messages to client
		totalInputTokens := int64(0)
		totalOutputTokens := int64(0)

		for msg := range messageChan {
			if err := conn.WriteJSON(msg); err != nil {
				log.Printf("WebSocket write error: %v", err)
				cancel()
				break
			}

			// Track tokens on completion
			if msg.Type == 4 { // COMPLETE
				totalInputTokens = 100
				totalOutputTokens = 200
				h.costTracker.TrackTokens(user.ID, totalInputTokens, totalOutputTokens)
			}
		}

		cancel()
	}

	log.Printf("[WebSocket] Connection closed for user: %s", user.ID)
}

// HandleChatSync handles synchronous chat (non-streaming)
func (h *ChatHandler) HandleChatSync(w http.ResponseWriter, r *http.Request) {
	// Get user from context
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Parse request
	var req ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}

	// Set user info
	req.UserID = user.ID
	req.TenantID = user.TenantID

	// Convert to service request
	serviceReq := h.toServiceRequest(&req)

	// Stream chat
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	messageChan, err := h.chatService.StreamChat(ctx, serviceReq)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to start chat: %v", err), http.StatusInternalServerError)
		return
	}

	// Collect all messages
	fullResponse := ""
	var lastMsg *service.ChatMessage

	for msg := range messageChan {
		if msg.Type == 1 { // CONTENT
			fullResponse += msg.Content
		}
		lastMsg = msg
	}

	// Track tokens
	h.costTracker.TrackTokens(user.ID, 100, 200)

	// Send response
	response := ChatResponse{
		SessionID: req.SessionID,
		Content:   fullResponse,
	}

	// Only add metadata if lastMsg exists
	if lastMsg != nil {
		response.Metadata = lastMsg.Metadata
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Failed to encode response: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
	}
}

// HandleSessions handles GET/POST /api/v1/chat/sessions
func (h *ChatHandler) HandleSessions(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.handleListSessions(w, r)
	case http.MethodPost:
		h.handleCreateSession(w, r)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

// HandleGetHistory handles GET /api/v1/chat/history/{session_id}
func (h *ChatHandler) HandleGetHistory(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	sessionID := strings.TrimPrefix(r.URL.Path, "/api/v1/chat/history/")
	if sessionID == "" || strings.Contains(sessionID, "/") {
		http.Error(w, "Invalid session id", http.StatusBadRequest)
		return
	}

	limit := parseQueryInt(r, "limit", 200)
	offset := parseQueryInt(r, "offset", 0)

	messages, err := h.chatService.GetSessionMessages(user.ID, sessionID, limit, offset)
	if err != nil {
		switch err {
		case service.ErrUnauthorized:
			http.Error(w, "Unauthorized", http.StatusForbidden)
			return
		case service.ErrSessionNotFound:
			http.Error(w, "Session not found", http.StatusNotFound)
			return
		default:
			http.Error(w, fmt.Sprintf("Failed to get history: %v", err), http.StatusInternalServerError)
			return
		}
	}

	response := ChatHistoryResponse{
		SessionID: sessionID,
		Messages:  make([]ChatMessageResponse, 0, len(messages)),
		Total:     len(messages),
	}

	for _, msg := range messages {
		response.Messages = append(response.Messages, toMessageResponse(msg))
	}

	respondJSON(w, response, http.StatusOK)
}

// HandleDeleteSession handles DELETE /api/v1/chat/session/{session_id}
func (h *ChatHandler) HandleDeleteSession(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	sessionID := strings.TrimPrefix(r.URL.Path, "/api/v1/chat/session/")
	if sessionID == "" || strings.Contains(sessionID, "/") {
		http.Error(w, "Invalid session id", http.StatusBadRequest)
		return
	}

	if err := h.chatService.DeleteSession(user.ID, sessionID); err != nil {
		switch err {
		case service.ErrUnauthorized:
			http.Error(w, "Unauthorized", http.StatusForbidden)
			return
		case service.ErrSessionNotFound:
			http.Error(w, "Session not found", http.StatusNotFound)
			return
		default:
			http.Error(w, fmt.Sprintf("Failed to delete session: %v", err), http.StatusInternalServerError)
			return
		}
	}

	respondJSON(w, map[string]string{"message": "Session deleted"}, http.StatusOK)
}

func (h *ChatHandler) handleListSessions(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	limit := parseQueryInt(r, "limit", 50)
	offset := parseQueryInt(r, "offset", 0)
	query := strings.TrimSpace(r.URL.Query().Get("q"))

	sessions, err := h.chatService.ListSessions(user.ID, query, limit, offset)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to list sessions: %v", err), http.StatusInternalServerError)
		return
	}

	response := ChatSessionListResponse{
		Sessions: make([]ChatSessionResponse, 0, len(sessions)),
		Total:    len(sessions),
	}
	for _, session := range sessions {
		response.Sessions = append(response.Sessions, toSessionResponse(session))
	}

	respondJSON(w, response, http.StatusOK)
}

func (h *ChatHandler) handleCreateSession(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req CreateSessionRequest
	if r.Body != nil {
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil && err.Error() != "EOF" {
			http.Error(w, "Invalid request", http.StatusBadRequest)
			return
		}
	}

	session, err := h.chatService.CreateSession(user.ID, user.TenantID, req.SessionID, req.Title)
	if err != nil {
		switch err {
		case service.ErrUnauthorized:
			http.Error(w, "Unauthorized", http.StatusForbidden)
			return
		default:
			http.Error(w, fmt.Sprintf("Failed to create session: %v", err), http.StatusInternalServerError)
			return
		}
	}

	respondJSON(w, toSessionResponse(session), http.StatusCreated)
}

func parseQueryInt(r *http.Request, key string, defaultValue int) int {
	value := r.URL.Query().Get(key)
	if value == "" {
		return defaultValue
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}
	return parsed
}

func toSessionResponse(session *database.Session) ChatSessionResponse {
	response := ChatSessionResponse{
		ID:        session.ID,
		Title:     session.Title,
		CreatedAt: session.CreatedAt.Format(time.RFC3339),
		UpdatedAt: session.UpdatedAt.Format(time.RFC3339),
	}
	if session.LastMessageAt != nil {
		value := session.LastMessageAt.Format(time.RFC3339)
		response.LastMessageAt = &value
	}
	return response
}

func toMessageResponse(message *database.Message) ChatMessageResponse {
	return ChatMessageResponse{
		ID:        message.ID,
		Role:      message.Role,
		Content:   message.Content,
		CreatedAt: message.CreatedAt.Format(time.RFC3339),
	}
}

// toServiceRequest converts HTTP request to service request
func (h *ChatHandler) toServiceRequest(req *ChatRequest) *service.ChatRequest {
	config := &service.ChatConfig{
		Model:       "gpt-4",
		Temperature: 0.7,
		MaxTokens:   2000,
		UseRAG:      false,
		UseAgent:    false,
		Tools:       []string{},
		KnowledgeBaseID: "",
	}

	if req.Config != nil {
		if req.Config.Model != "" {
			config.Model = req.Config.Model
		}
		if req.Config.Temperature > 0 {
			config.Temperature = req.Config.Temperature
		}
		if req.Config.MaxTokens > 0 {
			config.MaxTokens = req.Config.MaxTokens
		}
		config.UseRAG = req.Config.UseRAG
		config.UseAgent = req.Config.UseAgent
		config.Tools = req.Config.Tools
		config.KnowledgeBaseID = req.Config.KnowledgeBaseID
	}

	metadata := req.Metadata
	if metadata == nil {
		metadata = map[string]string{}
	}
	if req.Config != nil && req.Config.KnowledgeBaseID != "" {
		metadata["knowledge_base_id"] = req.Config.KnowledgeBaseID
	}

	return &service.ChatRequest{
		SessionID: req.SessionID,
		UserID:    req.UserID,
		TenantID:  req.TenantID,
		Message:   req.Message,
		Metadata:  metadata,
		Config:    config,
	}
}

// Request/Response types

type ChatRequest struct {
	SessionID string                 `json:"session_id"`
	UserID    string                 `json:"user_id"`
	TenantID  string                 `json:"tenant_id"`
	Message   string                 `json:"message"`
	Metadata  map[string]string      `json:"metadata"`
	Config    *ChatConfigRequest     `json:"config"`
}

type ChatConfigRequest struct {
	Model       string   `json:"model"`
	Temperature float32  `json:"temperature"`
	MaxTokens   int32    `json:"max_tokens"`
	UseRAG      bool     `json:"use_rag"`
	UseAgent    bool     `json:"use_agent"`
	Tools       []string `json:"tools"`
	KnowledgeBaseID string `json:"knowledge_base_id"`
}

type ChatResponse struct {
	SessionID string            `json:"session_id"`
	Content   string            `json:"content"`
	Metadata  map[string]string `json:"metadata"`
}

type CreateSessionRequest struct {
	SessionID string `json:"session_id"`
	Title     string `json:"title"`
}

type ChatSessionResponse struct {
	ID            string  `json:"id"`
	Title         string  `json:"title"`
	CreatedAt     string  `json:"created_at"`
	UpdatedAt     string  `json:"updated_at"`
	LastMessageAt *string `json:"last_message_at,omitempty"`
}

type ChatSessionListResponse struct {
	Sessions []ChatSessionResponse `json:"sessions"`
	Total    int                   `json:"total"`
}

type ChatMessageResponse struct {
	ID        string `json:"id"`
	Role      string `json:"role"`
	Content   string `json:"content"`
	CreatedAt string `json:"created_at"`
}

type ChatHistoryResponse struct {
	SessionID string                `json:"session_id"`
	Messages  []ChatMessageResponse `json:"messages"`
	Total     int                   `json:"total"`
}
