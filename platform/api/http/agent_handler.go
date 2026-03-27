package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

type AgentHandler struct {
	agentService *service.AgentService
}

func NewAgentHandler(agentService *service.AgentService) *AgentHandler {
	return &AgentHandler{agentService: agentService}
}

func (h *AgentHandler) HandleAgents(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	switch r.Method {
	case http.MethodGet:
		includeArchived := strings.EqualFold(r.URL.Query().Get("include_archived"), "true")
		items, err := h.agentService.ListAgentDefinitions(user.TenantID, includeArchived)
		if err != nil {
			respondError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		respondJSON(w, map[string]any{"agents": items, "total": len(items)}, http.StatusOK)
	case http.MethodPost:
		var req service.AgentDefinitionUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.CreateAgentDefinition(user.TenantID, user.ID, &req)
		if err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, item, http.StatusCreated)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *AgentHandler) HandleAgentByID(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	agentID := extractExactIDFromPath(r.URL.Path, "/api/v1/agents/")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}

	switch r.Method {
	case http.MethodGet:
		item, err := h.agentService.GetAgentDefinition(user.TenantID, agentID)
		if err != nil {
			status := http.StatusInternalServerError
			if err == service.ErrAgentUnauthorized || err == service.ErrUnauthorized {
				status = http.StatusForbidden
			}
			respondError(w, err.Error(), status)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodPut:
		var req service.AgentDefinitionUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.UpdateAgentDefinition(user.TenantID, user.ID, agentID, &req)
		if err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodDelete:
		if err := h.agentService.ArchiveAgentDefinition(user.TenantID, user.ID, agentID); err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, map[string]string{"message": "archived"}, http.StatusOK)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *AgentHandler) HandleCreateRun(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	agentID := extractSuffixID(r.URL.Path, "/api/v1/agents/", "/runs")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}

	var req service.CreateAgentRunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	run, err := h.agentService.CreateRun(r.Context(), user.TenantID, user.ID, agentID, &req)
	if err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, run, http.StatusCreated)
}

func (h *AgentHandler) HandleUpdateAgentKnowledgeBases(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	agentID := extractSuffixID(r.URL.Path, "/api/v1/agents/", "/knowledge-bases")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}
	var req service.UpdateAgentKnowledgeBasesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if err := h.agentService.UpdateAgentKnowledgeBases(user.TenantID, user.ID, agentID, &req); err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, map[string]string{"message": "updated"}, http.StatusOK)
}

func (h *AgentHandler) HandleTools(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	items, err := h.agentService.ListAvailableTools(
		r.Context(),
		user.TenantID,
		strings.TrimSpace(r.URL.Query().Get("agent_definition_id")),
	)
	if err != nil {
		respondError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	respondJSON(w, map[string]any{"tools": items, "total": len(items)}, http.StatusOK)
}

func (h *AgentHandler) HandleRuns(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	limit := parseQueryInt(r, "limit", 50)
	offset := parseQueryInt(r, "offset", 0)
	items, err := h.agentService.ListRuns(user.TenantID, user.ID, limit, offset)
	if err != nil {
		respondError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	respondJSON(w, map[string]any{"runs": items, "total": len(items)}, http.StatusOK)
}

func (h *AgentHandler) HandleRunByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	runID := extractExactIDFromPath(r.URL.Path, "/api/v1/agents/runs/")
	if runID == "" {
		respondError(w, "Invalid run id", http.StatusBadRequest)
		return
	}
	run, err := h.agentService.GetRun(user.TenantID, runID)
	if err != nil {
		respondError(w, err.Error(), http.StatusNotFound)
		return
	}
	respondJSON(w, run, http.StatusOK)
}

func (h *AgentHandler) HandleRunEvents(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	runID := extractSuffixID(r.URL.Path, "/api/v1/agents/runs/", "/events")
	if runID == "" {
		respondError(w, "Invalid run id", http.StatusBadRequest)
		return
	}
	afterSequence, _ := strconv.ParseInt(strings.TrimSpace(r.URL.Query().Get("after_sequence")), 10, 64)
	stream := strings.EqualFold(r.URL.Query().Get("stream"), "true")

	if !stream {
		limit := parseQueryInt(r, "limit", 500)
		items, err := h.agentService.ListRunEvents(user.TenantID, runID, afterSequence, limit)
		if err != nil {
			respondError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		respondJSON(w, map[string]any{"events": items, "total": len(items)}, http.StatusOK)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	flusher, ok := w.(http.Flusher)
	if !ok {
		respondError(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	events, err := h.agentService.StreamRunEvents(ctx, runID, user.TenantID, afterSequence)
	if err != nil {
		respondError(w, err.Error(), http.StatusInternalServerError)
		return
	}

	if _, err := fmt.Fprint(w, ": connected\n\n"); err != nil {
		return
	}
	flusher.Flush()

	heartbeatTicker := time.NewTicker(25 * time.Second)
	defer heartbeatTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-heartbeatTicker.C:
			if _, err := fmt.Fprint(w, ": keepalive\n\n"); err != nil {
				return
			}
			flusher.Flush()
		case event, ok := <-events:
			if !ok {
				return
			}
			data, err := json.Marshal(event)
			if err != nil {
				continue
			}
			if _, err := fmt.Fprintf(w, "data: %s\n\n", data); err != nil {
				return
			}
			flusher.Flush()
		}
	}
}

func (h *AgentHandler) HandleCancelRun(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	runID := extractSuffixID(r.URL.Path, "/api/v1/agents/runs/", "/cancel")
	if runID == "" {
		respondError(w, "Invalid run id", http.StatusBadRequest)
		return
	}
	run, err := h.agentService.CancelRun(r.Context(), user.TenantID, runID)
	if err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, run, http.StatusOK)
}

func (h *AgentHandler) HandleResumeRun(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	runID := extractSuffixID(r.URL.Path, "/api/v1/agents/runs/", "/resume")
	if runID == "" {
		respondError(w, "Invalid run id", http.StatusBadRequest)
		return
	}
	var req service.ResumeAgentRunRequest
	if r.Body != nil {
		_ = json.NewDecoder(r.Body).Decode(&req)
	}
	run, err := h.agentService.ResumeRun(r.Context(), user.TenantID, runID, &req)
	if err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, run, http.StatusOK)
}

func extractExactIDFromPath(path, prefix string) string {
	id := strings.TrimPrefix(path, prefix)
	id = strings.Trim(id, "/")
	if id == "" || strings.Contains(id, "/") {
		return ""
	}
	return id
}

func extractSuffixID(path, prefix, suffix string) string {
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	id := strings.TrimPrefix(path, prefix)
	id = strings.TrimSuffix(id, suffix)
	id = strings.Trim(id, "/")
	if id == "" || strings.Contains(id, "/") {
		return ""
	}
	return id
}
