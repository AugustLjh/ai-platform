import api from './axios'
import { buildApiUrl } from './base'

const buildStreamUrl = (runId, afterSequence = 0) => {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
  const url = new URL(buildApiUrl(`/api/v1/agents/runs/${runId}/events`), origin)
  url.searchParams.set('stream', 'true')
  url.searchParams.set('after_sequence', String(afterSequence))
  return url.toString()
}

const parseSSE = async (reader, onChunk) => {
  const decoder = new TextDecoder()
  let buffer = ''
  let dataLines = []

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })

    let newlineIndex = buffer.indexOf('\n')
    while (newlineIndex !== -1) {
      let line = buffer.slice(0, newlineIndex)
      buffer = buffer.slice(newlineIndex + 1)
      newlineIndex = buffer.indexOf('\n')

      if (line.endsWith('\r')) {
        line = line.slice(0, -1)
      }

      if (line === '') {
        if (dataLines.length > 0) {
          const data = dataLines.join('\n')
          dataLines = []
          if (data === '[DONE]') {
            return
          }
          onChunk(data)
        }
        continue
      }

      if (line.startsWith('data:')) {
        let dataPart = line.slice(5)
        if (dataPart.startsWith(' ')) {
          dataPart = dataPart.slice(1)
        }
        dataLines.push(dataPart)
      }
    }
  }
}

export const agentsAPI = {
  listAgents(includeArchived = false) {
    return api.get('/api/v1/agents', {
      params: { include_archived: includeArchived }
    })
  },

  getAgent(agentId) {
    return api.get(`/api/v1/agents/${agentId}`)
  },

  createAgent(payload) {
    return api.post('/api/v1/agents', payload)
  },

  updateAgent(agentId, payload) {
    return api.put(`/api/v1/agents/${agentId}`, payload)
  },

  updateAgentKnowledgeBases(agentId, knowledgeBaseIds = []) {
    return api.put(`/api/v1/agents/${agentId}/knowledge-bases`, {
      knowledge_base_ids: knowledgeBaseIds
    })
  },

  archiveAgent(agentId) {
    return api.delete(`/api/v1/agents/${agentId}`)
  },

  clearAgentContext(agentId, payload) {
    return api.post(`/api/v1/agents/${agentId}/clear-context`, payload)
  },

  createRun(agentId, payload) {
    return api.post(`/api/v1/agents/${agentId}/runs`, payload)
  },

  listWorkspaceSources(params = {}) {
    return api.get('/api/v1/agents/workspace-sources', { params })
  },

  inspectWorkspaces() {
    return api.get('/api/v1/agents/workspaces')
  },

  cleanupWorkspaces(params = {}) {
    return api.post('/api/v1/agents/workspaces/cleanup', null, { params })
  },

  cleanupWorkspaceLocks(params = {}) {
    return api.post('/api/v1/agents/workspaces/locks/cleanup', null, { params })
  },

  getRuntimeStatus() {
    return api.get('/api/v1/agents/runtime-status')
  },

  getOpsStatus(role = 'user') {
    return api.get('/api/v1/agents/ops-status', {
      headers: { 'X-User-Role': role }
    })
  },

  getTenantGovernanceStatus(role = 'user') {
    return api.get('/api/v1/agents/tenant-governance', {
      headers: { 'X-User-Role': role }
    })
  },

  evaluateOpsStatus(role = 'user') {
    return api.post('/api/v1/agents/ops-status/evaluate', null, {
      headers: { 'X-User-Role': role }
    })
  },

  getOpsPrometheusMetrics(role = 'user') {
    return api.get('/api/v1/agents/ops-status/metrics', {
      headers: { 'X-User-Role': role },
      responseType: 'text'
    })
  },

  getOpsGrafanaDashboard(role = 'user') {
    return api.get('/api/v1/agents/ops-status/grafana-dashboard', {
      headers: { 'X-User-Role': role }
    })
  },

  acknowledgeRuntimeAlert(ruleName, role = 'user') {
    return api.post(`/api/v1/agents/ops-status/alerts/${encodeURIComponent(ruleName)}/acknowledge`, null, {
      headers: { 'X-User-Role': role }
    })
  },

  resolveRuntimeAlert(ruleName, role = 'user') {
    return api.post(`/api/v1/agents/ops-status/alerts/${encodeURIComponent(ruleName)}/resolve`, null, {
      headers: { 'X-User-Role': role }
    })
  },

  evaluateAuditRedactionRules(testCases = [], role = 'user') {
    return api.post('/api/v1/agents/audit/redaction/evaluate', testCases, {
      headers: { 'X-User-Role': role }
    })
  },

  evaluateSubagentQualityRules(testCases = [], role = 'user') {
    return api.post('/api/v1/agents/subagents/quality/evaluate', testCases, {
      headers: { 'X-User-Role': role }
    })
  },

  listTools(agentDefinitionId = '') {
    const params = {}
    if (agentDefinitionId) {
      params.agent_definition_id = agentDefinitionId
    }
    return api.get('/api/v1/agents/tools', { params })
  },

  listRuns(limit = 50, offset = 0) {
    return api.get('/api/v1/agents/runs', {
      params: { limit, offset }
    })
  },

  getRun(runId) {
    return api.get(`/api/v1/agents/runs/${runId}`)
  },

  getRunInvocations(runId) {
    return api.get(`/api/v1/agents/runs/${runId}/invocations`)
  },

  getRunTree(runId, maxDepth = 4) {
    return api.get(`/api/v1/agents/runs/${runId}/tree`, {
      params: { max_depth: maxDepth }
    })
  },

  getRunEvents(runId, afterSequence = 0, limit = 500) {
    return api.get(`/api/v1/agents/runs/${runId}/events`, {
      params: { after_sequence: afterSequence, limit }
    })
  },

  getRunAuditView(runId, { viewerRole = 'user', includeEvents = true, includeToolCalls = true, eventLimit = 500, role = 'user' } = {}) {
    return api.get(`/api/v1/agents/runs/${runId}/audit-view`, {
      params: {
        viewer_role: viewerRole,
        include_events: includeEvents,
        include_tool_calls: includeToolCalls,
        event_limit: eventLimit
      },
      headers: { 'X-User-Role': role }
    })
  },

  cancelRun(runId) {
    return api.post(`/api/v1/agents/runs/${runId}/cancel`)
  },

  resumeRun(runId, payload = {}) {
    return api.post(`/api/v1/agents/runs/${runId}/resume`, payload)
  },

  reviewRunArtifact(runId, artifactId, payload = {}) {
    return api.post(`/api/v1/agents/runs/${runId}/artifacts/${artifactId}/review`, payload)
  },

  writebackRunWorkspace(runId, payload = {}) {
    return api.post(`/api/v1/agents/runs/${runId}/workspace/writeback`, payload)
  },

  async streamRunEvents(runId, { afterSequence = 0, signal, onEvent, onError } = {}) {
    const token = localStorage.getItem('access_token')
    const response = await fetch(buildStreamUrl(runId, afterSequence), {
      method: 'GET',
      headers: {
        Authorization: token ? `Bearer ${token}` : '',
        Accept: 'text/event-stream'
      },
      signal
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()

    try {
      await parseSSE(reader, (raw) => {
        try {
          const payload = JSON.parse(raw)
          if (payload?.error) {
            onError?.(new Error(payload.error))
            return
          }
          onEvent?.(payload)
        } catch (error) {
          onError?.(error)
        }
      })
    } finally {
      reader.releaseLock()
    }
  }
}
