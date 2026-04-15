package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/ai-platform/platform/database"
	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

type SubagentHandler struct {
	agentService *service.AgentService
}

func NewSubagentHandler(agentService *service.AgentService) *SubagentHandler {
	return &SubagentHandler{agentService: agentService}
}

func (h *SubagentHandler) HandleSubagents(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	switch r.Method {
	case http.MethodGet:
		includeArchived := strings.EqualFold(r.URL.Query().Get("include_archived"), "true")
		items, err := h.agentService.ListSubagentDefinitions(user.TenantID, includeArchived)
		if err != nil {
			respondError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		respondJSON(w, map[string]any{"subagents": items, "total": len(items)}, http.StatusOK)
	case http.MethodPost:
		var req service.SubagentDefinitionUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.CreateSubagentDefinition(user.TenantID, user.ID, user.Role, &req)
		if err != nil {
			statusCode := http.StatusBadRequest
			if errors.Is(err, service.ErrAgentUnauthorized) {
				statusCode = http.StatusForbidden
			}
			respondError(w, err.Error(), statusCode)
			return
		}
		respondJSON(w, item, http.StatusCreated)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *SubagentHandler) HandleSubagentGovernance(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	result, err := h.agentService.GetSubagentGovernance(user.TenantID, user.Role, &database.SubagentPublicationEventFilters{
		DefinitionID:      strings.TrimSpace(r.URL.Query().Get("definition_id")),
		ActionType:        strings.TrimSpace(r.URL.Query().Get("action_type")),
		EventStage:        strings.TrimSpace(r.URL.Query().Get("event_stage")),
		ChangeType:        strings.TrimSpace(r.URL.Query().Get("change_type")),
		RiskLevel:         strings.TrimSpace(r.URL.Query().Get("risk_level")),
		CompatibilityMode: strings.TrimSpace(r.URL.Query().Get("compatibility_mode")),
		Limit:             parseQueryInt(r, "limit", 20),
		Offset:            parseQueryInt(r, "offset", 0),
	})
	if err != nil {
		statusCode := http.StatusInternalServerError
		if errors.Is(err, service.ErrAgentUnauthorized) {
			statusCode = http.StatusForbidden
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, result, http.StatusOK)
}

func (h *SubagentHandler) HandleSubagentByID(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	subagentID := extractExactIDFromPath(r.URL.Path, "/api/v1/subagents/")
	if subagentID == "" {
		respondError(w, "Invalid subagent id", http.StatusBadRequest)
		return
	}

	switch r.Method {
	case http.MethodGet:
		item, err := h.agentService.GetSubagentDefinition(user.TenantID, subagentID)
		if err != nil {
			respondError(w, err.Error(), http.StatusNotFound)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodPut:
		var req service.SubagentDefinitionUpsertRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			respondError(w, "Invalid request", http.StatusBadRequest)
			return
		}
		item, err := h.agentService.UpdateSubagentDefinition(user.TenantID, user.ID, user.Role, subagentID, &req)
		if err != nil {
			statusCode := http.StatusBadRequest
			if errors.Is(err, service.ErrAgentUnauthorized) {
				statusCode = http.StatusForbidden
			}
			respondError(w, err.Error(), statusCode)
			return
		}
		respondJSON(w, item, http.StatusOK)
	case http.MethodDelete:
		if err := h.agentService.DeleteSubagentDefinition(user.TenantID, user.Role, subagentID); err != nil {
			statusCode := http.StatusBadRequest
			if errors.Is(err, service.ErrAgentUnauthorized) {
				statusCode = http.StatusForbidden
			}
			respondError(w, err.Error(), statusCode)
			return
		}
		respondJSON(w, map[string]string{"message": "deleted"}, http.StatusOK)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *SubagentHandler) HandleSubagentControlPlane(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	subagentID := extractSuffixID(r.URL.Path, "/api/v1/subagents/", "/control-plane")
	if subagentID == "" {
		respondError(w, "Invalid subagent id", http.StatusBadRequest)
		return
	}
	controlPlane, err := h.agentService.GetSubagentControlPlane(user.TenantID, user.Role, subagentID)
	if err != nil {
		statusCode := http.StatusBadRequest
		switch {
		case errors.Is(err, service.ErrAgentUnauthorized):
			statusCode = http.StatusForbidden
		case errors.Is(err, database.ErrSubagentDefinitionNotFound):
			statusCode = http.StatusNotFound
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, controlPlane, http.StatusOK)
}

func (h *SubagentHandler) HandleCreateSubagentVersion(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	subagentID := extractSuffixID(r.URL.Path, "/api/v1/subagents/", "/versions")
	if subagentID == "" {
		respondError(w, "Invalid subagent id", http.StatusBadRequest)
		return
	}
	var req service.SubagentVersionCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	controlPlane, err := h.agentService.CreateSubagentVersion(user.TenantID, user.ID, user.Role, subagentID, &req)
	if err != nil {
		statusCode := http.StatusBadRequest
		switch {
		case errors.Is(err, service.ErrAgentUnauthorized):
			statusCode = http.StatusForbidden
		case errors.Is(err, database.ErrSubagentDefinitionNotFound):
			statusCode = http.StatusNotFound
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, controlPlane, http.StatusCreated)
}

func (h *SubagentHandler) HandleUpdateSubagentPublication(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	subagentID := extractSuffixID(r.URL.Path, "/api/v1/subagents/", "/publication")
	if subagentID == "" {
		respondError(w, "Invalid subagent id", http.StatusBadRequest)
		return
	}
	var req service.SubagentPublicationUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	controlPlane, err := h.agentService.UpdateSubagentPublication(user.TenantID, user.ID, user.Role, subagentID, &req)
	if err != nil {
		statusCode := http.StatusBadRequest
		switch {
		case errors.Is(err, service.ErrAgentUnauthorized):
			statusCode = http.StatusForbidden
		case errors.Is(err, database.ErrSubagentDefinitionNotFound), errors.Is(err, database.ErrSubagentPublicationNotFound):
			statusCode = http.StatusNotFound
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, controlPlane, http.StatusOK)
}

func (h *SubagentHandler) HandleFreezeSubagentMetadataAliases(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	var req service.SubagentMetadataAliasFreezeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil && !errors.Is(err, io.EOF) {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	result, err := h.agentService.FreezeSubagentMetadataAliases(user.TenantID, user.ID, user.Role, &req)
	if err != nil {
		statusCode := http.StatusBadRequest
		switch {
		case errors.Is(err, service.ErrAgentUnauthorized):
			statusCode = http.StatusForbidden
		case errors.Is(err, database.ErrSubagentDefinitionNotFound):
			statusCode = http.StatusNotFound
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, result, http.StatusOK)
}

func (h *SubagentHandler) HandleSubagentTestRuns(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	subagentID := extractSuffixID(r.URL.Path, "/api/v1/subagents/", "/test-runs")
	if subagentID == "" {
		respondError(w, "Invalid subagent id", http.StatusBadRequest)
		return
	}
	var req service.SubagentTestRunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	run, err := h.agentService.CreateSubagentTestRun(r.Context(), user.TenantID, user.ID, user.Role, subagentID, &req)
	if err != nil {
		statusCode := http.StatusBadRequest
		switch {
		case errors.Is(err, service.ErrAgentUnauthorized):
			statusCode = http.StatusForbidden
		case errors.Is(err, database.ErrSubagentDefinitionNotFound), errors.Is(err, database.ErrAgentDefinitionNotFound):
			statusCode = http.StatusNotFound
		}
		respondError(w, err.Error(), statusCode)
		return
	}
	respondJSON(w, run, http.StatusCreated)
}

func (h *SubagentHandler) HandleUpdateAgentSubagents(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	agentID := extractSuffixID(r.URL.Path, "/api/v1/agents/", "/subagents")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}
	var req service.UpdateAgentSubagentsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if err := h.agentService.UpdateAgentSubagents(user.TenantID, user.ID, agentID, &req); err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, map[string]string{"message": "updated"}, http.StatusOK)
}
