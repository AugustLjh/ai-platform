import api from "./axios";

export const subagentsAPI = {
  listSubagents(includeArchived = false) {
    return api.get("/api/v1/subagents", {
      params: { include_archived: includeArchived },
    });
  },

  getSubagent(subagentId) {
    return api.get(`/api/v1/subagents/${subagentId}`);
  },

  getControlPlane(subagentId) {
    return api.get(`/api/v1/subagents/${subagentId}/control-plane`);
  },

  getGovernance(params = {}) {
    return api.get("/api/v1/subagents/governance", { params });
  },

  createSubagent(payload) {
    return api.post("/api/v1/subagents", payload);
  },

  updateSubagent(subagentId, payload) {
    return api.put(`/api/v1/subagents/${subagentId}`, payload);
  },

  createSubagentVersion(subagentId, payload) {
    return api.post(`/api/v1/subagents/${subagentId}/versions`, payload);
  },

  updateSubagentPublication(subagentId, payload) {
    return api.post(`/api/v1/subagents/${subagentId}/publication`, payload);
  },

  previewSubagentPublication(subagentId, payload) {
    return api.post(`/api/v1/subagents/${subagentId}/publication`, {
      ...payload,
      preview_only: true,
    });
  },

  freezeMetadataAliases(payload = {}) {
    return api.post("/api/v1/subagents/metadata-aliases/freeze", payload);
  },

  previewMetadataAliasFreeze(payload = {}) {
    return api.post("/api/v1/subagents/metadata-aliases/freeze", {
      ...payload,
      preview_only: true,
    });
  },

  createSubagentTestRun(subagentId, payload) {
    return api.post(`/api/v1/subagents/${subagentId}/test-runs`, payload);
  },

  deleteSubagent(subagentId) {
    return api.delete(`/api/v1/subagents/${subagentId}`);
  },

  updateAgentSubagents(agentId, subagentIds = []) {
    return api.put(`/api/v1/agents/${agentId}/subagents`, {
      subagent_ids: subagentIds,
    });
  },
};
