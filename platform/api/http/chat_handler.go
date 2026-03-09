package http

import (
	"context"
	"encoding/json"
	"errors"
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
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
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
		http.Error(w, fmt.Sprintf("Failed to start chat: %v", err), statusCodeForChatError(err))
		return
	}

	// Get flusher for SSE
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	// Stream messages
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
				inputTokens, outputTokens, totalCost := parseUsageMetadata(msg.Metadata)
				h.costTracker.TrackUsage(user.ID, inputTokens, outputTokens, totalCost)
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
			statusCode := statusCodeForChatError(err)
			conn.WriteJSON(map[string]string{
				"error":  fmt.Sprintf("Failed to start chat: %v", err),
				"status": http.StatusText(statusCode),
			})
			cancel()
			continue
		}

		// Stream messages to client
		for msg := range messageChan {
			if err := conn.WriteJSON(msg); err != nil {
				log.Printf("WebSocket write error: %v", err)
				cancel()
				break
			}

			// Track tokens on completion
			if msg.Type == 4 { // COMPLETE
				inputTokens, outputTokens, totalCost := parseUsageMetadata(msg.Metadata)
				h.costTracker.TrackUsage(user.ID, inputTokens, outputTokens, totalCost)
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
		http.Error(w, fmt.Sprintf("Failed to start chat: %v", err), statusCodeForChatError(err))
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
	if lastMsg != nil {
		inputTokens, outputTokens, totalCost := parseUsageMetadata(lastMsg.Metadata)
		h.costTracker.TrackUsage(user.ID, inputTokens, outputTokens, totalCost)
	}

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

func (h *ChatHandler) HandleUsageStats(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	knowledgeBaseID := strings.TrimSpace(r.URL.Query().Get("knowledge_base_id"))
	stats, err := h.chatService.GetUsageStats(user.ID, user.TenantID, knowledgeBaseID)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to get usage stats: %v", err), http.StatusInternalServerError)
		return
	}

	respondJSON(w, UsageStatsResponse{
		CurrentUser:     toUsageSummaryResponse(stats.CurrentUser),
		CurrentTenant:   toUsageSummaryResponse(stats.CurrentTenant),
		ByKnowledgeBase: toUsageDimensionResponses(stats.ByKnowledgeBase),
		ByFeature:       toUsageDimensionResponses(stats.ByFeature),
		ByModel:         toUsageDimensionResponses(stats.ByModel),
	}, http.StatusOK)
}

func (h *ChatHandler) HandleLowQualitySamples(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	knowledgeBaseID := strings.TrimSpace(r.URL.Query().Get("knowledge_base_id"))
	limit := parseQueryInt(r, "limit", 20)
	samples, err := h.chatService.ListLowQualitySamples(user.ID, knowledgeBaseID, limit)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to get low quality samples: %v", err), http.StatusInternalServerError)
		return
	}

	response := LowQualitySampleListResponse{
		Samples: make([]LowQualitySampleResponse, 0, len(samples)),
		Total:   len(samples),
	}
	for _, sample := range samples {
		response.Samples = append(response.Samples, LowQualitySampleResponse{
			MessageID:       sample.MessageID,
			SessionID:       sample.SessionID,
			SessionTitle:    sample.SessionTitle,
			Content:         sample.Content,
			CreatedAt:       sample.CreatedAt.Format(time.RFC3339),
			KnowledgeBaseID: sample.KnowledgeBaseID,
			KnowledgeBase:   sample.KnowledgeBase,
			FeedbackLabel:   sample.FeedbackLabel,
			FeedbackComment: sample.FeedbackComment,
			FeedbackRating:  sample.FeedbackRating,
			Metadata:        sample.Metadata,
		})
	}

	respondJSON(w, response, http.StatusOK)
}

func (h *ChatHandler) HandleMessageFeedback(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user, ok := middleware.GetUser(r.Context())
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	if !strings.HasSuffix(r.URL.Path, "/feedback") {
		http.Error(w, "Not found", http.StatusNotFound)
		return
	}

	messageID := strings.TrimPrefix(r.URL.Path, "/api/v1/chat/messages/")
	messageID = strings.TrimSuffix(messageID, "/feedback")
	messageID = strings.TrimSpace(strings.Trim(messageID, "/"))
	if messageID == "" || strings.Contains(messageID, "/") {
		http.Error(w, "Invalid message id", http.StatusBadRequest)
		return
	}

	var req MessageFeedbackRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request", http.StatusBadRequest)
		return
	}

	if req.Label == "" {
		http.Error(w, "feedback label is required", http.StatusBadRequest)
		return
	}
	if req.Label != "like" && req.Label != "dislike" {
		http.Error(w, "unsupported feedback label", http.StatusBadRequest)
		return
	}

	message, err := h.chatService.SaveMessageFeedback(user.ID, messageID, req.Rating, req.Label, req.Comment)
	if err != nil {
		switch err {
		case service.ErrMessageNotFound:
			http.Error(w, "Message not found", http.StatusNotFound)
			return
		default:
			http.Error(w, fmt.Sprintf("Failed to save feedback: %v", err), http.StatusInternalServerError)
			return
		}
	}

	respondJSON(w, MessageFeedbackResponse{
		Message: toMessageResponse(message),
	}, http.StatusOK)
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

func statusCodeForChatError(err error) int {
	if err == nil {
		return http.StatusInternalServerError
	}

	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return http.StatusGatewayTimeout
	}

	if grpcStatus, ok := status.FromError(err); ok {
		switch grpcStatus.Code() {
		case codes.Unavailable, codes.FailedPrecondition:
			return http.StatusServiceUnavailable
		case codes.DeadlineExceeded:
			return http.StatusGatewayTimeout
		}
	}

	errMsg := strings.ToLower(err.Error())
	switch {
	case strings.Contains(errMsg, "connection refused"),
		strings.Contains(errMsg, "no such host"),
		strings.Contains(errMsg, "service unavailable"),
		strings.Contains(errMsg, "transport is closing"),
		strings.Contains(errMsg, "connection error"),
		strings.Contains(errMsg, "error reading from server"),
		strings.Contains(errMsg, "server closed the stream"):
		return http.StatusServiceUnavailable
	case strings.Contains(errMsg, "deadline exceeded"),
		strings.Contains(errMsg, "request cancelled"),
		strings.Contains(errMsg, "context canceled"),
		strings.Contains(errMsg, "context deadline exceeded"):
		return http.StatusGatewayTimeout
	default:
		return http.StatusInternalServerError
	}
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

func parseUsageMetadata(metadata map[string]string) (int64, int64, float64) {
	if metadata == nil {
		return 0, 0, 0
	}

	inputTokens, _ := strconv.ParseInt(strings.TrimSpace(metadata["prompt_tokens"]), 10, 64)
	outputTokens, _ := strconv.ParseInt(strings.TrimSpace(metadata["completion_tokens"]), 10, 64)
	totalCost, _ := strconv.ParseFloat(strings.TrimSpace(metadata["cost_usd"]), 64)
	return inputTokens, outputTokens, totalCost
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
		Metadata:  message.Metadata,
	}
}

func toUsageSummaryResponse(summary database.UsageSummary) UsageSummaryResponse {
	return UsageSummaryResponse{
		TotalCost:    summary.TotalCost,
		TotalTokens:  summary.TotalTokens,
		RequestCount: summary.RequestCount,
	}
}

func toUsageDimensionResponses(items []database.UsageDimension) []UsageDimensionResponse {
	responses := make([]UsageDimensionResponse, 0, len(items))
	for _, item := range items {
		responses = append(responses, UsageDimensionResponse{
			Key:          item.Key,
			Label:        item.Label,
			TotalCost:    item.TotalCost,
			TotalTokens:  item.TotalTokens,
			RequestCount: item.RequestCount,
		})
	}
	return responses
}

// toServiceRequest converts HTTP request to service request
func (h *ChatHandler) toServiceRequest(req *ChatRequest) *service.ChatRequest {
	config := &service.ChatConfig{
		Model:           "gpt-4",
		Temperature:     0.7,
		MaxTokens:       2000,
		UseRAG:          false,
		UseAgent:        false,
		Tools:           []string{},
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
	SessionID string             `json:"session_id"`
	UserID    string             `json:"user_id"`
	TenantID  string             `json:"tenant_id"`
	Message   string             `json:"message"`
	Metadata  map[string]string  `json:"metadata"`
	Config    *ChatConfigRequest `json:"config"`
}

type ChatConfigRequest struct {
	Model           string   `json:"model"`
	Temperature     float32  `json:"temperature"`
	MaxTokens       int32    `json:"max_tokens"`
	UseRAG          bool     `json:"use_rag"`
	UseAgent        bool     `json:"use_agent"`
	Tools           []string `json:"tools"`
	KnowledgeBaseID string   `json:"knowledge_base_id"`
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
	ID        string            `json:"id"`
	Role      string            `json:"role"`
	Content   string            `json:"content"`
	CreatedAt string            `json:"created_at"`
	Metadata  map[string]string `json:"metadata"`
}

type ChatHistoryResponse struct {
	SessionID string                `json:"session_id"`
	Messages  []ChatMessageResponse `json:"messages"`
	Total     int                   `json:"total"`
}

type MessageFeedbackRequest struct {
	Label   string  `json:"label"`
	Rating  float64 `json:"rating"`
	Comment string  `json:"comment"`
}

type MessageFeedbackResponse struct {
	Message ChatMessageResponse `json:"message"`
}

type UsageSummaryResponse struct {
	TotalCost    float64 `json:"total_cost"`
	TotalTokens  int64   `json:"total_tokens"`
	RequestCount int64   `json:"request_count"`
}

type UsageDimensionResponse struct {
	Key          string  `json:"key"`
	Label        string  `json:"label"`
	TotalCost    float64 `json:"total_cost"`
	TotalTokens  int64   `json:"total_tokens"`
	RequestCount int64   `json:"request_count"`
}

type UsageStatsResponse struct {
	CurrentUser     UsageSummaryResponse     `json:"current_user"`
	CurrentTenant   UsageSummaryResponse     `json:"current_tenant"`
	ByKnowledgeBase []UsageDimensionResponse `json:"by_knowledge_base"`
	ByFeature       []UsageDimensionResponse `json:"by_feature"`
	ByModel         []UsageDimensionResponse `json:"by_model"`
}

type LowQualitySampleResponse struct {
	MessageID       string            `json:"message_id"`
	SessionID       string            `json:"session_id"`
	SessionTitle    string            `json:"session_title"`
	Content         string            `json:"content"`
	CreatedAt       string            `json:"created_at"`
	KnowledgeBaseID string            `json:"knowledge_base_id"`
	KnowledgeBase   string            `json:"knowledge_base"`
	FeedbackLabel   string            `json:"feedback_label"`
	FeedbackComment string            `json:"feedback_comment"`
	FeedbackRating  float64           `json:"feedback_rating"`
	Metadata        map[string]string `json:"metadata"`
}

type LowQualitySampleListResponse struct {
	Samples []LowQualitySampleResponse `json:"samples"`
	Total   int                        `json:"total"`
}
