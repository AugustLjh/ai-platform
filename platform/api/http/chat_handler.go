package http

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

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
				return true // In production, check origin properly
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
			data, _ := json.Marshal(msg)
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
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)

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
		Metadata:  lastMsg.Metadata,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
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
	}

	return &service.ChatRequest{
		SessionID: req.SessionID,
		UserID:    req.UserID,
		TenantID:  req.TenantID,
		Message:   req.Message,
		Metadata:  req.Metadata,
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
}

type ChatResponse struct {
	SessionID string            `json:"session_id"`
	Content   string            `json:"content"`
	Metadata  map[string]string `json:"metadata"`
}
