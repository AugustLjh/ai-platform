package http

import (
	"encoding/json"
	"net/http"

	"github.com/ai-platform/platform/middleware"
	"github.com/ai-platform/platform/service"
)

type SkillHandler struct {
	agentService *service.AgentService
}

func NewSkillHandler(agentService *service.AgentService) *SkillHandler {
	return &SkillHandler{agentService: agentService}
}

func (h *SkillHandler) HandleSkills(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	switch r.Method {
	case http.MethodGet:
		items, err := h.agentService.ListSkills(user.TenantID)
		if err != nil {
			respondError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		respondJSON(w, map[string]any{"skills": items, "total": len(items)}, http.StatusOK)
	default:
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *SkillHandler) HandleSkillByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	skillID := extractExactIDFromPath(r.URL.Path, "/api/v1/skills/")
	if skillID == "" {
		respondError(w, "Invalid skill id", http.StatusBadRequest)
		return
	}
	item, err := h.agentService.GetSkill(user.TenantID, skillID)
	if err != nil {
		respondError(w, err.Error(), http.StatusNotFound)
		return
	}
	respondJSON(w, item, http.StatusOK)
}

func (h *SkillHandler) HandleSyncSkills(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if _, ok := middleware.GetUser(r.Context()); !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	items, err := h.agentService.SyncSkills()
	if err != nil {
		respondError(w, err.Error(), http.StatusInternalServerError)
		return
	}
	respondJSON(w, map[string]any{"skills": items, "total": len(items)}, http.StatusOK)
}

func (h *SkillHandler) HandleUpdateAgentSkills(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		respondError(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	user, ok := middleware.GetUser(r.Context())
	if !ok {
		respondError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	agentID := extractSuffixID(r.URL.Path, "/api/v1/agents/", "/skills")
	if agentID == "" {
		respondError(w, "Invalid agent id", http.StatusBadRequest)
		return
	}
	var req service.UpdateAgentSkillsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if err := h.agentService.UpdateAgentSkills(user.TenantID, agentID, &req); err != nil {
		respondError(w, err.Error(), http.StatusBadRequest)
		return
	}
	respondJSON(w, map[string]string{"message": "updated"}, http.StatusOK)
}
