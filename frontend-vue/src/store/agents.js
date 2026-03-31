import { defineStore } from 'pinia'
import { agentsAPI, skillsAPI, mcpAPI } from '@/api'
import { buildArtifactsFromStructuredResult, normalizeArtifact, normalizeRunResult, parseJSON } from '@/utils/agentArtifacts'

const terminalRunStatuses = new Set(['completed', 'failed', 'cancelled', 'waiting_user'])
const executionBoundaryEventTypes = new Set(['run.resumed'])

const normalizeAgent = (raw = {}) => ({
  id: raw.id,
  tenantId: raw.tenant_id || raw.tenantId || '',
  name: raw.name || '未命名智能体',
  description: raw.description || '',
  systemPrompt: raw.system_prompt || raw.systemPrompt || '',
  model: raw.model || '',
  status: raw.status || 'active',
  config: parseJSON(raw.config, {}),
  metadata: parseJSON(raw.metadata, {}),
  skillIds: Array.isArray(raw.skill_ids || raw.skillIds)
    ? [...(raw.skill_ids || raw.skillIds)]
    : [],
  mcpServerIds: Array.isArray(raw.mcp_server_ids || raw.mcpServerIds)
    ? [...(raw.mcp_server_ids || raw.mcpServerIds)]
    : [],
  knowledgeBaseIds: Array.isArray(raw.knowledge_base_ids || raw.knowledgeBaseIds)
    ? [...(raw.knowledge_base_ids || raw.knowledgeBaseIds)]
    : [],
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
  archivedAt: raw.archived_at || raw.archivedAt || null
})

const normalizeRun = (raw = {}) => {
  const result = normalizeRunResult(raw)
  return {
    id: raw.id,
    agentDefinitionId: raw.agent_definition_id || raw.agentDefinitionId || '',
    tenantId: raw.tenant_id || raw.tenantId || '',
    userId: raw.user_id || raw.userId || '',
    sessionId: raw.session_id || raw.sessionId || '',
    status: raw.status || 'queued',
    input: parseJSON(raw.input, {}),
    plan: parseJSON(raw.plan, {}),
    context: parseJSON(raw.context, {}),
    finalOutput: result.finalOutput,
    finalOutputText: result.finalOutputText,
    finalOutputJson: result.finalOutputJson,
    errorMessage: raw.error_message || raw.errorMessage || '',
    startedAt: raw.started_at || raw.startedAt || null,
    finishedAt: raw.finished_at || raw.finishedAt || null,
    cancelledAt: raw.cancelled_at || raw.cancelledAt || null,
    createdAt: raw.created_at || raw.createdAt || null,
    updatedAt: raw.updated_at || raw.updatedAt || null,
    metadata: parseJSON(raw.metadata, {}),
    artifacts: result.artifacts,
    steps: Array.isArray(raw.steps) ? raw.steps.map((step) => ({
      id: step.id,
      stepIndex: Number(step.step_index || step.stepIndex || 0),
      kind: step.kind || '',
      title: step.title || '',
      status: step.status || 'pending',
      question: parseJSON(step.output, {})?.question || '',
      output: parseJSON(step.output, {}),
      error: step.error_message || step.errorMessage || '',
      createdAt: step.created_at || step.createdAt || null,
      updatedAt: step.updated_at || step.updatedAt || null
    })) : [],
    toolCalls: Array.isArray(raw.tool_calls || raw.toolCalls) ? (raw.tool_calls || raw.toolCalls).map((toolCall) => ({
      id: toolCall.id,
      stepId: toolCall.step_id || toolCall.stepId || '',
      toolName: toolCall.tool_name || toolCall.toolName || '',
      toolKind: toolCall.tool_kind || toolCall.toolKind || 'builtin',
      status: toolCall.status || 'pending',
      arguments: parseJSON(toolCall.arguments, {}),
      result: parseJSON(toolCall.result, {}),
      error: toolCall.error_message || toolCall.errorMessage || '',
      createdAt: toolCall.created_at || toolCall.createdAt || null,
      updatedAt: toolCall.updated_at || toolCall.updatedAt || null
    })) : []
  }
}

const normalizeEvent = (raw = {}) => ({
  id: raw.id,
  runId: raw.run_id || raw.runId || '',
  sequence: Number(raw.sequence || 0),
  eventType: raw.event_type || raw.eventType || '',
  payload: parseJSON(raw.payload, {}),
  createdAt: raw.created_at || raw.createdAt || null
})

const normalizeSkill = (raw = {}) => ({
  id: raw.id,
  name: raw.name || '',
  slug: raw.slug || '',
  version: raw.version || '',
  description: raw.description || '',
  systemPrompt: raw.system_prompt || '',
  outputSchema: parseJSON(raw.output_schema || raw.outputSchema, {}),
  toolAllowlist: parseJSON(raw.tool_allowlist || raw.toolAllowlist, []),
  metadata: parseJSON(raw.metadata, {}),
  createdAt: raw.created_at || null,
  updatedAt: raw.updated_at || null
})

const normalizeMCPServer = (raw = {}) => ({
  id: raw.id,
  name: raw.name || '',
  transport: raw.transport || '',
  endpoint: raw.endpoint || '',
  command: raw.command || '',
  args: parseJSON(raw.args, []),
  env: parseJSON(raw.env, {}),
  status: raw.status || 'active',
  lastError: raw.last_error || '',
  lastTestedAt: raw.last_tested_at || null,
  updatedAt: raw.updated_at || null,
  connection: raw.connection && typeof raw.connection === 'object'
    ? {
        status: raw.connection.status || 'untested',
        summary: raw.connection.summary || '',
        testedAt: raw.connection.tested_at || raw.connection.testedAt || null,
        error: raw.connection.error || ''
      }
    : null,
  catalog: raw.catalog && typeof raw.catalog === 'object'
    ? {
        status: raw.catalog.status || 'missing',
        summary: raw.catalog.summary || '',
        toolCount: Number(raw.catalog.tool_count || raw.catalog.toolCount || 0),
        refreshedAt: raw.catalog.refreshed_at || raw.catalog.refreshedAt || null,
        ageSeconds: raw.catalog.age_seconds ?? raw.catalog.ageSeconds ?? null,
        staleAfterSeconds: Number(raw.catalog.stale_after_seconds || raw.catalog.staleAfterSeconds || 0),
        isStale: Boolean(raw.catalog.is_stale || raw.catalog.isStale),
        sampleTools: Array.isArray(raw.catalog.sample_tools || raw.catalog.sampleTools)
          ? [...(raw.catalog.sample_tools || raw.catalog.sampleTools)]
          : []
      }
    : null,
  availability: raw.availability && typeof raw.availability === 'object'
    ? {
        status: raw.availability.status || 'unavailable',
        summary: raw.availability.summary || '',
        bindable: Boolean(raw.availability.bindable),
        reason: raw.availability.reason || ''
      }
    : null,
  metadata: parseJSON(raw.metadata, {}),
  tools: Array.isArray(raw.tools) ? raw.tools.map((tool) => ({
    id: tool.id,
    serverId: tool.server_id || tool.serverId || '',
    runtimeName: tool.runtime_name || tool.runtimeName || '',
    serverName: tool.server_name || tool.serverName || '',
    transport: tool.transport || '',
    toolName: tool.tool_name || tool.toolName || '',
    description: tool.description || '',
    inputSchema: parseJSON(tool.input_schema || tool.inputSchema, {}),
    metadata: parseJSON(tool.metadata, {}),
    discoveredAt: tool.discovered_at || tool.discoveredAt || null
  })) : []
})

const normalizeToolSpec = (raw = {}) => ({
  name: raw.name || '',
  description: raw.description || '',
  inputSchema: parseJSON(raw.input_schema || raw.inputSchema, {}),
  kind: raw.kind || 'builtin',
  metadata: parseJSON(raw.metadata, {})
})

const sortByUpdatedDesc = (items) => [...items].sort((a, b) => {
  const aTime = new Date(a.updatedAt || a.createdAt || 0).getTime()
  const bTime = new Date(b.updatedAt || b.createdAt || 0).getTime()
  return bTime - aTime
})

const getActiveExecutionEvents = (events = []) => {
  let boundaryIndex = -1
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (executionBoundaryEventTypes.has(events[index]?.eventType)) {
      boundaryIndex = index
      break
    }
  }
  return boundaryIndex >= 0 ? events.slice(boundaryIndex) : events
}

const deriveRunState = (run, events) => {
  const stepsMap = new Map((Array.isArray(run?.steps) ? run.steps : []).map((step) => [step.id, { ...step }]))
  const toolCallMap = new Map((Array.isArray(run?.toolCalls) ? run.toolCalls : []).map((toolCall) => [toolCall.id, { ...toolCall }]))
  let plan = run?.plan && Object.keys(run.plan).length > 0 ? run.plan : null
  let finalOutput = run?.finalOutput || ''
  let finalOutputText = run?.finalOutputText || ''
  let finalOutputJson = run?.finalOutputJson || null
  let artifacts = Array.isArray(run?.artifacts) ? [...run.artifacts] : []
  const activeEvents = getActiveExecutionEvents(events)

  const captureResultPayload = (payload = {}) => {
    const output = payload.output && typeof payload.output === 'object' ? payload.output : null

    if (payload.final_output !== undefined) {
      finalOutput = payload.final_output || ''
    } else if (output?.final_output !== undefined) {
      finalOutput = output.final_output || ''
    }

    if (payload.final_output_text !== undefined) {
      finalOutputText = payload.final_output_text || ''
    } else if (output?.final_output_text !== undefined) {
      finalOutputText = output.final_output_text || ''
    }

    if (payload.final_output_json !== undefined) {
      finalOutputJson = payload.final_output_json
    } else if (output?.final_output_json !== undefined) {
      finalOutputJson = output.final_output_json
    }

    if (Array.isArray(payload.artifacts)) {
      artifacts = payload.artifacts.map(normalizeArtifact)
    } else if (Array.isArray(output?.artifacts)) {
      artifacts = output.artifacts.map(normalizeArtifact)
    }

    if (payload.question && !finalOutputText) {
      finalOutputText = payload.question
    }
  }

  for (const event of activeEvents) {
    const payload = event.payload || {}

    if (event.eventType === 'run.resumed') {
      plan = null
      finalOutput = ''
      finalOutputText = ''
      finalOutputJson = null
      artifacts = []
      stepsMap.clear()
      toolCallMap.clear()
    }

    captureResultPayload(payload)

    if (event.eventType === 'plan.created' && payload.plan) {
      plan = payload.plan
    }

    if (event.eventType.startsWith('step.')) {
      const stepId = payload.step_id
      if (!stepId) {
        continue
      }

      const existing = stepsMap.get(stepId) || {
        id: stepId,
        stepIndex: payload.step_index || 0,
        kind: payload.kind || '',
        title: payload.title || '',
        status: 'pending',
        question: '',
        output: null,
        error: '',
        createdAt: event.createdAt,
        updatedAt: event.createdAt
      }

      existing.stepIndex = payload.step_index || existing.stepIndex
      existing.kind = payload.kind || existing.kind
      existing.title = payload.title || existing.title
      existing.updatedAt = event.createdAt

      if (event.eventType === 'step.started') {
        existing.status = 'running'
      }

      if (event.eventType === 'step.completed') {
        existing.status = 'completed'
        existing.output = payload.output || existing.output
        existing.question = payload.question || payload.output?.question || existing.question
      }

      if (event.eventType === 'step.failed') {
        existing.status = 'failed'
        existing.error = payload.error || existing.error
      }

      if (event.eventType === 'step.cancelled') {
        existing.status = 'cancelled'
        existing.error = payload.error || existing.error
      }

      stepsMap.set(stepId, existing)
    }

    if (event.eventType.startsWith('tool.')) {
      const toolCallId = payload.tool_call_id
      if (!toolCallId) {
        continue
      }

      const existing = toolCallMap.get(toolCallId) || {
        id: toolCallId,
        stepId: payload.step_id || '',
        toolName: payload.tool_name || '',
        toolKind: payload.tool_kind || 'builtin',
        status: 'pending',
        arguments: payload.arguments || {},
        result: null,
        error: '',
        createdAt: event.createdAt,
        updatedAt: event.createdAt
      }

      existing.stepId = payload.step_id || existing.stepId
      existing.toolName = payload.tool_name || existing.toolName
      existing.toolKind = payload.tool_kind || existing.toolKind || 'builtin'
      existing.updatedAt = event.createdAt

      if (event.eventType === 'tool.started') {
        existing.status = 'running'
        existing.arguments = payload.arguments || existing.arguments
      }

      if (event.eventType === 'tool.completed') {
        existing.status = 'completed'
        existing.result = payload.result || existing.result
      }

      if (event.eventType === 'tool.failed') {
        existing.status = 'failed'
        existing.error = payload.error || existing.error
      }

      if (event.eventType === 'tool.cancelled') {
        existing.status = 'cancelled'
        existing.error = payload.error || existing.error
      }

      toolCallMap.set(toolCallId, existing)
    }
  }

  if ((!artifacts || artifacts.length === 0) && finalOutputJson) {
    artifacts = buildArtifactsFromStructuredResult(finalOutputJson, finalOutputText || finalOutput)
  }

  return {
    plan,
    steps: [...stepsMap.values()].sort((a, b) => {
      if (a.stepIndex === b.stepIndex) {
        return new Date(a.createdAt || 0).getTime() - new Date(b.createdAt || 0).getTime()
      }
      return a.stepIndex - b.stepIndex
    }),
    toolCalls: [...toolCallMap.values()].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()),
    artifacts,
    runPatch: {
      finalOutput: finalOutputText || finalOutput,
      finalOutputText: finalOutputText || finalOutput,
      finalOutputJson,
      steps: [...stepsMap.values()].sort((a, b) => {
        if (a.stepIndex === b.stepIndex) {
          return new Date(a.createdAt || 0).getTime() - new Date(b.createdAt || 0).getTime()
        }
        return a.stepIndex - b.stepIndex
      }),
      toolCalls: [...toolCallMap.values()].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())
    }
  }
}

export const useAgentsStore = defineStore('agents', {
  state: () => ({
    agentDefinitions: [],
    runs: [],
    currentAgent: null,
    currentRun: null,
    runEvents: [],
    steps: [],
    toolCalls: [],
    plan: null,
    artifacts: [],
    availableTools: [],
    skills: [],
    mcpServers: [],
    loading: false,
    error: null,
    streamController: null,
    streamRunId: null,
    streaming: false
  }),

  getters: {
    sortedAgents(state) {
      return sortByUpdatedDesc(state.agentDefinitions)
    },

    sortedRuns(state) {
      return sortByUpdatedDesc(state.runs)
    },

    currentAgentRuns(state) {
      if (!state.currentAgent?.id) return []
      return sortByUpdatedDesc(
        state.runs.filter((run) => run.agentDefinitionId === state.currentAgent.id)
      )
    },

    latestSequence(state) {
      return state.runEvents.reduce((max, event) => Math.max(max, event.sequence || 0), 0)
    }
  },

  actions: {
    setError(error, fallback) {
      this.error = error?.response?.data?.error || error?.response?.data?.detail || error?.message || fallback
    },

    resetRunState() {
      this.currentRun = null
      this.runEvents = []
      this.steps = []
      this.toolCalls = []
      this.plan = null
      this.artifacts = []
    },

    applyEvents(events = []) {
      const merged = [...this.runEvents]
      const knownIds = new Set(merged.map((event) => event.id))

      for (const event of events.map(normalizeEvent)) {
        if (knownIds.has(event.id)) {
          continue
        }
        merged.push(event)
        knownIds.add(event.id)
      }

      merged.sort((a, b) => a.sequence - b.sequence)
      this.runEvents = merged

      const derived = deriveRunState(this.currentRun, merged)
      this.plan = derived.plan
      this.steps = derived.steps
      this.toolCalls = derived.toolCalls
      this.artifacts = derived.artifacts
      if (this.currentRun?.id) {
        this.applyRunPatch(this.currentRun.id, {
          ...derived.runPatch,
          artifacts: derived.artifacts
        })
      }
    },

    upsertRun(run) {
      const index = this.runs.findIndex((item) => item.id === run.id)
      if (index === -1) {
        this.runs.unshift(run)
      } else {
        this.runs[index] = run
      }
    },

    applyRunPatch(runId, patch = {}) {
      if (!runId || Object.keys(patch).length === 0) {
        return
      }

      if (this.currentRun?.id === runId) {
        this.currentRun = {
          ...this.currentRun,
          ...patch
        }
      }

      const index = this.runs.findIndex((item) => item.id === runId)
      if (index !== -1) {
        this.runs[index] = {
          ...this.runs[index],
          ...patch
        }
      }
    },

    applyRunEvent(event) {
      const payload = event.payload || {}
      const patch = {}

      if (payload.status) {
        patch.status = payload.status
      }

      if (event.createdAt) {
        patch.updatedAt = event.createdAt
      }

      if (event.eventType === 'run.resumed' || event.eventType === 'run.started') {
        patch.finalOutput = ''
        patch.finalOutputText = ''
        patch.finalOutputJson = null
        patch.artifacts = []
        patch.errorMessage = ''
        patch.finishedAt = null
        patch.cancelledAt = null
        patch.plan = {}
      }

      if (event.eventType === 'run.resumed') {
        patch.startedAt = null
      }

      if (event.eventType === 'run.started') {
        patch.startedAt = event.createdAt || this.currentRun?.startedAt || null
      }

      if (payload.plan) {
        patch.plan = payload.plan
      }

      if (event.eventType === 'run.waiting_user' && payload.question) {
        patch.finalOutput = payload.question
        patch.finalOutputText = payload.question
      } else if (payload.final_output !== undefined) {
        patch.finalOutput = payload.final_output
      }

      if (payload.final_output_text !== undefined) {
        patch.finalOutputText = payload.final_output_text
      }

      if (payload.final_output_json !== undefined) {
        patch.finalOutputJson = payload.final_output_json
      }

      if (Array.isArray(payload.artifacts)) {
        patch.artifacts = payload.artifacts.map(normalizeArtifact)
        this.artifacts = patch.artifacts
      }

      if (payload.error) {
        patch.errorMessage = payload.error
      }

      if (event.eventType === 'run.completed') {
        patch.finishedAt = event.createdAt || this.currentRun?.finishedAt || null
        patch.cancelledAt = null
      }

      if (event.eventType === 'run.failed') {
        patch.finishedAt = event.createdAt || this.currentRun?.finishedAt || null
      }

      if (event.eventType === 'run.cancelled') {
        patch.cancelledAt = event.createdAt || this.currentRun?.cancelledAt || null
      }

      if (payload.input_patch && this.currentRun?.id === event.runId) {
        patch.input = {
          ...(this.currentRun.input || {}),
          ...payload.input_patch
        }
      }

      this.applyRunPatch(event.runId, patch)
    },

    async fetchAgents(includeArchived = false) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.listAgents(includeArchived)
        this.agentDefinitions = (data.agents || []).map(normalizeAgent)
        return this.agentDefinitions
      } catch (error) {
        this.setError(error, 'Failed to fetch agents')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchAgent(agentId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.getAgent(agentId)
        const agent = normalizeAgent(data)
        const index = this.agentDefinitions.findIndex((item) => item.id === agent.id)
        if (index === -1) {
          this.agentDefinitions.push(agent)
        } else {
          this.agentDefinitions[index] = agent
        }
        this.currentAgent = agent
        return agent
      } catch (error) {
        this.setError(error, 'Failed to fetch agent')
        throw error
      } finally {
        this.loading = false
      }
    },

    async createAgent(payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.createAgent(payload)
        const agent = normalizeAgent(data)
        this.agentDefinitions.unshift(agent)
        this.currentAgent = agent
        return agent
      } catch (error) {
        this.setError(error, 'Failed to create agent')
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateAgent(agentId, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.updateAgent(agentId, payload)
        const agent = normalizeAgent(data)
        const index = this.agentDefinitions.findIndex((item) => item.id === agent.id)
        if (index === -1) {
          this.agentDefinitions.unshift(agent)
        } else {
          this.agentDefinitions[index] = agent
        }
        if (this.currentAgent?.id === agent.id) {
          this.currentAgent = agent
        }
        return agent
      } catch (error) {
        this.setError(error, 'Failed to update agent')
        throw error
      } finally {
        this.loading = false
      }
    },

    async archiveAgent(agentId) {
      this.loading = true
      this.error = null
      try {
        await agentsAPI.archiveAgent(agentId)
        this.agentDefinitions = this.agentDefinitions.filter((item) => item.id !== agentId)
        if (this.currentAgent?.id === agentId) {
          this.currentAgent = null
        }
      } catch (error) {
        this.setError(error, 'Failed to archive agent')
        throw error
      } finally {
        this.loading = false
      }
    },

    async clearAgentContext(agentId, sessionId) {
      this.loading = true
      this.error = null
      try {
        await agentsAPI.clearAgentContext(agentId, { session_id: sessionId })
        this.runs = this.runs.filter((run) => !(run.agentDefinitionId === agentId && run.sessionId === sessionId))
        if (this.currentRun?.agentDefinitionId === agentId && this.currentRun?.sessionId === sessionId) {
          this.resetRunState()
        }
      } catch (error) {
        this.setError(error, 'Failed to clear agent context')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchRuns(limit = 50, offset = 0) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.listRuns(limit, offset)
        this.runs = (data.runs || []).map(normalizeRun)
        return this.runs
      } catch (error) {
        this.setError(error, 'Failed to fetch runs')
        throw error
      } finally {
        this.loading = false
      }
    },

    async createRun(agentId, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.createRun(agentId, payload)
        const run = normalizeRun(data)
        this.currentRun = run
        this.upsertRun(run)
        this.runEvents = []
        this.steps = Array.isArray(run.steps) ? run.steps : []
        this.toolCalls = Array.isArray(run.toolCalls) ? run.toolCalls : []
        this.plan = run.plan && Object.keys(run.plan).length > 0 ? run.plan : null
        this.artifacts = Array.isArray(run.artifacts) ? run.artifacts : []
        return run
      } catch (error) {
        this.setError(error, 'Failed to create run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchRun(runId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.getRun(runId)
        const run = normalizeRun(data)
        this.upsertRun(run)
        this.currentRun = run
        this.plan = run.plan && Object.keys(run.plan).length > 0 ? run.plan : null
        this.steps = Array.isArray(run.steps) ? run.steps : []
        this.toolCalls = Array.isArray(run.toolCalls) ? run.toolCalls : []
        this.artifacts = Array.isArray(run.artifacts) ? run.artifacts : []
        return run
      } catch (error) {
        this.setError(error, 'Failed to fetch run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchRunEvents(runId, afterSequence = 0, limit = 500) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.getRunEvents(runId, afterSequence, limit)
        const events = (data.events || []).map(normalizeEvent)
        if (afterSequence > 0) {
          this.applyEvents(events)
        } else {
          this.runEvents = []
          this.applyEvents(events)
        }
        return events
      } catch (error) {
        this.setError(error, 'Failed to fetch run events')
        throw error
      } finally {
        this.loading = false
      }
    },

    async openRun(runId, { stream = true } = {}) {
      this.stopRunStream()
      this.resetRunState()
      const run = await this.fetchRun(runId)
      await this.fetchRunEvents(runId, 0, 500)

      if (stream && run && !terminalRunStatuses.has(run.status)) {
        this.subscribeToRun(run.id)
      }

      return run
    },

    subscribeToRun(runId) {
      this.stopRunStream()
      const controller = new AbortController()
      this.streamController = controller
      this.streamRunId = runId
      this.streaming = true

      agentsAPI.streamRunEvents(runId, {
        afterSequence: this.latestSequence,
        signal: controller.signal,
        onEvent: (event) => {
          const normalized = normalizeEvent(event)
          this.applyEvents([normalized])
          this.applyRunEvent(normalized)
        },
        onError: (error) => {
          if (controller.signal.aborted) {
            return
          }
          this.setError(error, 'Run event stream failed')
        }
      })
        .catch((error) => {
          if (controller.signal.aborted) {
            return
          }
          this.setError(error, 'Run event stream failed')
        })
        .finally(() => {
          if (this.streamController === controller) {
            this.streamController = null
            this.streamRunId = null
            this.streaming = false
          }
        })
    },

    stopRunStream() {
      if (this.streamController) {
        this.streamController.abort()
      }
      this.streamController = null
      this.streamRunId = null
      this.streaming = false
    },

    async cancelRun(runId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.cancelRun(runId)
        const run = normalizeRun(data)
        this.currentRun = run
        this.upsertRun(run)
        this.stopRunStream()
        return run
      } catch (error) {
        this.setError(error, 'Failed to cancel run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async resumeRun(runId, inputPatch = {}) {
      this.loading = true
      this.error = null
      try {
        const { data } = await agentsAPI.resumeRun(runId, { input_patch: inputPatch })
        const run = {
          ...normalizeRun(data),
          finalOutput: '',
          finalOutputText: '',
          finalOutputJson: null,
          artifacts: [],
          errorMessage: '',
          plan: {}
        }
        this.currentRun = run
        this.upsertRun(run)
        this.runEvents = []
        this.steps = []
        this.toolCalls = []
        this.plan = null
        this.artifacts = []
        this.subscribeToRun(run.id)
        return run
      } catch (error) {
        this.setError(error, 'Failed to resume run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchSkills() {
      try {
        const { data } = await skillsAPI.listSkills()
        this.skills = (data.skills || []).map(normalizeSkill)
        return this.skills
      } catch (error) {
        this.setError(error, 'Failed to fetch skills')
        throw error
      }
    },

    async syncSkills() {
      try {
        const { data } = await skillsAPI.syncSkills()
        this.skills = (data.skills || []).map(normalizeSkill)
        return this.skills
      } catch (error) {
        this.setError(error, 'Failed to sync skills')
        throw error
      }
    },

    async updateAgentSkills(agentId, skillIds = []) {
      this.loading = true
      this.error = null
      try {
        await skillsAPI.updateAgentSkills(agentId, skillIds)
        const nextSkillIds = Array.isArray(skillIds) ? [...skillIds] : []
        const applyPatch = (agent) => {
          if (!agent || agent.id !== agentId) return agent
          return {
            ...agent,
            skillIds: nextSkillIds
          }
        }

        if (this.currentAgent?.id === agentId) {
          this.currentAgent = applyPatch(this.currentAgent)
        }
        this.agentDefinitions = this.agentDefinitions.map(applyPatch)
        return nextSkillIds
      } catch (error) {
        this.setError(error, 'Failed to update agent skills')
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateAgentKnowledgeBases(agentId, knowledgeBaseIds = []) {
      this.loading = true
      this.error = null
      try {
        await agentsAPI.updateAgentKnowledgeBases(agentId, knowledgeBaseIds)
        const nextKnowledgeBaseIds = Array.isArray(knowledgeBaseIds) ? [...knowledgeBaseIds] : []
        const applyPatch = (agent) => {
          if (!agent || agent.id !== agentId) return agent
          return {
            ...agent,
            knowledgeBaseIds: nextKnowledgeBaseIds
          }
        }

        if (this.currentAgent?.id === agentId) {
          this.currentAgent = applyPatch(this.currentAgent)
        }
        this.agentDefinitions = this.agentDefinitions.map(applyPatch)
        return nextKnowledgeBaseIds
      } catch (error) {
        this.setError(error, 'Failed to update agent knowledge bases')
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateAgentMCPServers(agentId, serverIds = []) {
      this.loading = true
      this.error = null
      try {
        await mcpAPI.updateAgentMCPServers(agentId, serverIds)
        const nextServerIds = Array.isArray(serverIds) ? [...serverIds] : []
        const applyPatch = (agent) => {
          if (!agent || agent.id !== agentId) return agent
          return {
            ...agent,
            mcpServerIds: nextServerIds
          }
        }

        if (this.currentAgent?.id === agentId) {
          this.currentAgent = applyPatch(this.currentAgent)
        }
        this.agentDefinitions = this.agentDefinitions.map(applyPatch)
        return nextServerIds
      } catch (error) {
        this.setError(error, 'Failed to update agent MCP servers')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchMCPServers() {
      try {
        const { data } = await mcpAPI.listServers()
        this.mcpServers = (data.servers || []).map(normalizeMCPServer)
        return this.mcpServers
      } catch (error) {
        this.setError(error, 'Failed to fetch MCP servers')
        throw error
      }
    },

    async fetchTools(agentDefinitionId = '') {
      try {
        const { data } = await agentsAPI.listTools(agentDefinitionId)
        this.availableTools = (data.tools || []).map(normalizeToolSpec)
        return this.availableTools
      } catch (error) {
        this.setError(error, 'Failed to fetch agent tools')
        throw error
      }
    }
  }
})
