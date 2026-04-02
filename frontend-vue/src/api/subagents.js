import api from './axios'

export const subagentsAPI = {
  listSubagents(includeArchived = false) {
    return api.get('/api/v1/subagents', {
      params: { include_archived: includeArchived }
    })
  },

  getSubagent(subagentId) {
    return api.get(`/api/v1/subagents/${subagentId}`)
  },

  createSubagent(payload) {
    return api.post('/api/v1/subagents', payload)
  },

  updateSubagent(subagentId, payload) {
    return api.put(`/api/v1/subagents/${subagentId}`, payload)
  },

  deleteSubagent(subagentId) {
    return api.delete(`/api/v1/subagents/${subagentId}`)
  },

  updateAgentSubagents(agentId, subagentIds = []) {
    return api.put(`/api/v1/agents/${agentId}/subagents`, {
      subagent_ids: subagentIds
    })
  }
}
