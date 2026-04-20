import api from './axios'

export const mcpAPI = {
  listServers() {
    return api.get('/api/v1/mcp/servers')
  },

  getGovernance(params = {}) {
    return api.get('/api/v1/mcp/governance', { params })
  },

  getServer(serverId) {
    return api.get(`/api/v1/mcp/servers/${serverId}`)
  },

  createServer(payload) {
    return api.post('/api/v1/mcp/servers', payload)
  },

  updateServer(serverId, payload) {
    return api.put(`/api/v1/mcp/servers/${serverId}`, payload)
  },

  deleteServer(serverId) {
    return api.delete(`/api/v1/mcp/servers/${serverId}`)
  },

  testServer(serverId) {
    return api.post(`/api/v1/mcp/servers/${serverId}/test`)
  },

  refreshTools(serverId) {
    return api.post(`/api/v1/mcp/servers/${serverId}/refresh-tools`)
  },

  bulkAction(payload) {
    return api.post('/api/v1/mcp/bulk-actions', payload)
  },

  previewBulkAction(payload) {
    return api.post('/api/v1/mcp/bulk-actions', {
      ...payload,
      preview_only: true
    })
  },

  updateAgentMCPServers(agentId, serverIds = []) {
    return api.put(`/api/v1/agents/${agentId}/mcp-servers`, {
      server_ids: serverIds
    })
  }
}
