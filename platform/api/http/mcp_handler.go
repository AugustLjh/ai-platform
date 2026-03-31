package http

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

type MCPHandler struct {
	agentService *service.AgentService
}

func NewMCPHandler(agentService *service.AgentService) *MCPHandler {
	return &MCPHandler{agentService: agentService}
}

func (h *MCPHandler) HandleServers(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	switch r.Method {
	case http.MethodGet:
		items, err := h.agentService.ListMCPServers(user.TenantID)
		if err != nil {
			respondError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		respondJSON(w, map[string]any{"servers": items, "total": len(items)}, http.StatusOK)
	case http.MethodPost:
		var req service.MCPServerUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.CreateMCPServer(user.TenantID, user.ID, &req)
		if err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, item, http.StatusCreated)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *MCPHandler) HandleServerByID(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	serverID := extractExactIDFromPath(r.URL.Path, "/api/v1/mcp/servers/")
	if serverID == "" {
		respondError(w, "Invalid server id", http.StatusBadRequest)
		return
	}

	switch r.Method {
	case http.MethodGet:
		item, err := h.agentService.GetMCPServer(user.TenantID, serverID)
		if err != nil {
			respondError(w, err.Error(), http.StatusNotFound)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodPut:
		var req service.MCPServerUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.UpdateMCPServer(user.TenantID, user.ID, serverID, &req)
		if err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodDelete:
		if err := h.agentService.DeleteMCPServer(user.TenantID, serverID); err != nil {
			respondError(w, err.Error(), http.StatusBadRequest)
			return
		}
		respondJSON(w, map[string]string{"message": "deleted"}, http.StatusOK)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *MCPHandler) HandleTestServer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	serverID := extractSuffixID(r.URL.Path, "/api/v1/mcp/servers/", "/test")
	if serverID == "" {
		respondError(w, "Invalid server id", http.StatusBadRequest)
		return
	}
	result, err := h.agentService.TestMCPServer(r.Context(), user.TenantID, serverID)
	if err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, result, http.StatusOK)
}

func (h *MCPHandler) HandleRefreshServerTools(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	serverID := extractSuffixID(r.URL.Path, "/api/v1/mcp/servers/", "/refresh-tools")
	if serverID == "" {
		respondError(w, "Invalid server id", http.StatusBadRequest)
		return
	}
	result, err := h.agentService.RefreshMCPServerTools(user.TenantID, serverID)
	if err != nil {
		status := http.StatusBadRequest
		if errors.Is(err, service.ErrNotImplemented) {
			status = http.StatusNotImplemented
		}
		respondError(w, err.Error(), status)
		return
	}
	respondJSON(w, result, http.StatusOK)
}

func (h *MCPHandler) HandleUpdateAgentMCPServers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	agentID := extractSuffixID(r.URL.Path, "/api/v1/agents/", "/mcp-servers")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}
	var req service.UpdateAgentMCPServersRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if err := h.agentService.UpdateAgentMCPServers(user.TenantID, agentID, &req); err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, map[string]string{"message": "updated"}, http.StatusOK)
}
