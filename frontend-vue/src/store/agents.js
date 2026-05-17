import { defineStore } from 'pinia'
import { agentsAPI, skillsAPI, mcpAPI, subagentsAPI } from '@/api'
import {
  buildRunArtifactsFromToolCalls,
  normalizeRunResult,
  parseJSON
} from '@/utils/agentArtifacts'
import { buildRunEventPatch, deriveRunState } from '@/utils/agentRunState'
import { collectRunEventPages } from '@/utils/runEventHydration'
import { normalizeMCPBindingUsage, normalizeMCPEvent, normalizeMCPGovernanceSummary, normalizeMCPRecovery } from '@/utils/mcpServers'
import { collectRunTreeInvocations, normalizeRunTreeNode } from '@/utils/agentRunTree'
import { normalizeRuntimeStatus } from '@/utils/runtimeStatus'
import { redactRuntimePayload } from '@/utils/runtimeRedaction'

const terminalRunStatuses = new Set(['completed', 'failed', 'cancelled', 'waiting_user'])
const MCP_BULK_PREVIEW_STORAGE_KEY = 'mcp_bulk_preview_context'

export const redactMCPBulkPreviewForStorage = (preview = null) => {
  if (!preview || typeof preview !== 'object') return null
  return {
    ...preview,
    previewToken: ''
  }
}

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
  subagentIds: Array.isArray(raw.subagent_ids || raw.subagentIds)
    ? [...(raw.subagent_ids || raw.subagentIds)]
    : [],
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
  archivedAt: raw.archived_at || raw.archivedAt || null
})

const normalizeSubagent = (raw = {}) => ({
  id: raw.publication_id || raw.publicationId || raw.id,
  definitionId: raw.id || raw.definition_id || raw.definitionId || '',
  publicationId: raw.publication_id || raw.publicationId || '',
  versionId: raw.version_id || raw.versionId || '',
  versionNumber: Number(raw.version_number || raw.versionNumber || 0),
  tenantId: raw.tenant_id || raw.tenantId || '',
  name: raw.name || '未命名专家能力',
  slug: raw.slug || '',
  description: raw.description || '',
  systemPrompt: raw.system_prompt || raw.systemPrompt || '',
  model: raw.model || '',
  status: raw.status || 'active',
  definitionStatus: raw.definition_status || raw.definitionStatus || 'active',
  lifecycleStatus: raw.lifecycle_status || raw.lifecycleStatus || 'active',
  publicationScope: raw.publication_scope || raw.publicationScope || 'tenant',
  publicationTenantId: raw.publication_tenant_id || raw.publicationTenantId || '',
  config: parseJSON(raw.config, {}),
  metadata: parseJSON(raw.metadata, {}),
  outputSchema: parseJSON(raw.output_schema || raw.outputSchema, {}),
  handoffInputSchema: parseJSON(raw.handoff_input_schema || raw.handoffInputSchema, {}),
  toolAllowlist: parseJSON(raw.tool_allowlist || raw.toolAllowlist, []),
  skillAllowlist: parseJSON(raw.skill_allowlist || raw.skillAllowlist, []),
  mcpAllowlist: parseJSON(raw.mcp_allowlist || raw.mcpAllowlist, []),
  knowledgePolicy: parseJSON(raw.knowledge_policy || raw.knowledgePolicy, {}),
  reviewPolicy: parseJSON(raw.review_policy || raw.reviewPolicy, {}),
  runtimePolicy: parseJSON(raw.runtime_policy || raw.runtimePolicy, {}),
  publicationMetadata: parseJSON(raw.publication_metadata || raw.publicationMetadata, {}),
  hostAgentDefinitionId: raw.host_agent_definition_id || raw.hostAgentDefinitionId || raw.target_agent_definition_id || raw.targetAgentDefinitionId || '',
  handoffPrompt: raw.handoff_prompt || raw.handoffPrompt || '',
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
  archivedAt: raw.archived_at || raw.archivedAt || null
})

const normalizeRun = (raw = {}) => {
  const result = normalizeRunResult(raw)
  const toolCalls = Array.isArray(raw.tool_calls || raw.toolCalls) ? (raw.tool_calls || raw.toolCalls).map((toolCall) => ({
    id: toolCall.id,
    stepId: toolCall.step_id || toolCall.stepId || '',
    toolName: toolCall.tool_name || toolCall.toolName || '',
    toolKind: toolCall.tool_kind || toolCall.toolKind || 'builtin',
    status: toolCall.status || 'pending',
    arguments: redactRuntimePayload(parseJSON(toolCall.arguments, {})),
    result: redactRuntimePayload(parseJSON(toolCall.result, {})),
    recovery: redactRuntimePayload(parseJSON(toolCall.result, {}))?.recovery || {},
    error: toolCall.error_message || toolCall.errorMessage || '',
    createdAt: toolCall.created_at || toolCall.createdAt || null,
    updatedAt: toolCall.updated_at || toolCall.updatedAt || null
  })) : []
  const artifacts = buildRunArtifactsFromToolCalls(toolCalls, result.artifacts)
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
    artifacts,
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
    toolCalls
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

const normalizeStringList = (value, allowedSet = null) => {
  if (!Array.isArray(value)) return []
  const result = []
  const seen = new Set()
  value.forEach((item) => {
    const normalized = String(item || '').trim().toLowerCase()
    if (!normalized) return
    if (allowedSet && !allowedSet.has(normalized)) return
    if (seen.has(normalized)) return
    seen.add(normalized)
    result.push(normalized)
  })
  return result
}

const normalizeSkillContract = (raw = {}) => {
  const metadata = parseJSON(raw.metadata, {})
  const outputSchema = parseJSON(raw.output_schema || raw.outputSchema, {})
  const toolAllowlist = parseJSON(raw.tool_allowlist || raw.toolAllowlist, [])
  const fallbackOutputFields = Object.keys(outputSchema?.properties || {}).filter(Boolean).sort()
  const contract = parseJSON(raw.contract, {})

  const managedToolKinds = normalizeStringList(contract.managed_tool_kinds || metadata.managed_tool_kinds)
  const activationIntents = normalizeStringList(contract.activation_intents || metadata.activation_intents)
  const activationPhases = normalizeStringList(
    contract.activation_phases || metadata.activation_phases,
    new Set(['planning', 'execution', 'synthesis', 'output'])
  )
  const hasSystemPrompt = Boolean((raw.system_prompt || raw.systemPrompt || '').trim())
  const hasOutputSchema = contract.has_output_schema ?? Boolean(outputSchema && Object.keys(outputSchema).length > 0)
  const toolPolicyMode = contract.tool_policy_mode ||
    (managedToolKinds.length > 0 ? 'provider_managed' : (Array.isArray(toolAllowlist) && toolAllowlist.length > 0 ? 'allowlist' : 'inherit'))
  const kind = ['capability_pack', 'role_prompt'].includes(contract.kind)
    ? contract.kind
    : 'capability_pack'
  const surfaces = Array.isArray(contract.surfaces) && contract.surfaces.length > 0
    ? [...contract.surfaces]
    : [
        ...(hasSystemPrompt ? ['prompt'] : []),
        ...(toolPolicyMode !== 'inherit' ? ['tools'] : []),
        ...(hasOutputSchema ? ['output'] : [])
      ]

  return {
    kind,
    capabilityType: contract.capability_type || metadata.capability_type || '',
    displayName: contract.display_name || metadata.display_name || raw.name || raw.slug || '',
    bindingMode: contract.binding_mode || ((metadata.fixed_binding || raw.slug === 'implementation-planner') ? 'fixed' : 'optional'),
    systemSkill: Boolean(contract.system_skill ?? metadata.system_skill),
    activationIntents,
    activationPhases,
    intentPolicy: contract.intent_policy || (activationIntents.length > 0 ? 'explicit' : 'all'),
    phasePolicy: contract.phase_policy || (activationPhases.length > 0 ? 'explicit' : 'all'),
    hasSystemPrompt,
    toolPolicyMode,
    managedToolKinds,
    hasOutputSchema,
    outputFieldNames: Array.isArray(contract.output_field_names) && contract.output_field_names.length > 0
      ? [...contract.output_field_names]
      : fallbackOutputFields,
    surfaces,
    governanceStatus: contract.governance_status || 'ready',
    governanceErrors: Array.isArray(contract.governance_errors) ? [...contract.governance_errors] : [],
    governanceWarnings: Array.isArray(contract.governance_warnings) ? [...contract.governance_warnings] : [],
    governanceRequirements: Array.isArray(contract.governance_requirements) ? [...contract.governance_requirements] : []
  }
}

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
  contract: normalizeSkillContract(raw),
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
  bindingUsage: normalizeMCPBindingUsage(raw.binding_usage || raw.bindingUsage),
  recovery: normalizeMCPRecovery(raw.recovery),
  events: Array.isArray(raw.events) ? raw.events.map(normalizeMCPEvent).filter(Boolean) : [],
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

const normalizeExecutionMode = (raw = {}) => ({
  name: raw.name || 'context_only',
  label: raw.label || 'Context Only',
  summary: raw.summary || '',
  capabilities: Array.isArray(raw.capabilities) ? [...raw.capabilities] : [],
  riskLevel: raw.risk_level || raw.riskLevel || 'low',
  source: raw.source || 'default',
  allowedModes: Array.isArray(raw.allowed_modes || raw.allowedModes)
    ? [...(raw.allowed_modes || raw.allowedModes)]
    : []
})

const sortByUpdatedDesc = (items) => [...items].sort((a, b) => {
  const aTime = new Date(a.updatedAt || a.createdAt || 0).getTime()
  const bTime = new Date(b.updatedAt || b.createdAt || 0).getTime()
  return bTime - aTime
})

export const useAgentsStore = defineStore('agents', {
  state: () => ({
    agentDefinitions: [],
    runs: [],
    currentAgent: null,
    currentRun: null,
    currentRunTree: null,
    currentRunInvocations: [],
    runEvents: [],
    steps: [],
    toolCalls: [],
    plan: null,
    artifacts: [],
    executionSurface: null,
    availableTools: [],
    availableToolsExecutionMode: null,
    runtimeStatus: null,
    workspaceInspection: null,
    workspaceCleanupResult: null,
    skills: [],
    mcpServers: [],
    mcpGovernanceSummary: null,
    mcpBulkPreviewContext: parseJSON(typeof localStorage !== 'undefined' ? localStorage.getItem(MCP_BULK_PREVIEW_STORAGE_KEY) : null, null),
    subagents: [],
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
      this.currentRunTree = null
      this.currentRunInvocations = []
      this.runEvents = []
      this.steps = []
      this.toolCalls = []
      this.plan = null
      this.artifacts = []
      this.executionSurface = null
    },

    hydrateRunSurface(run = this.currentRun, events = this.runEvents) {
      const derived = deriveRunState(run, events)
      this.executionSurface = derived.surfaceMeta
      this.plan = derived.plan
      this.steps = derived.steps
      this.toolCalls = derived.toolCalls
      this.artifacts = derived.artifacts
      if (run?.id) {
        this.applyRunPatch(run.id, {
          ...derived.runPatch,
          artifacts: derived.artifacts
        })
      }
      return derived
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
      this.hydrateRunSurface(this.currentRun, merged)
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
      const patch = buildRunEventPatch(this.currentRun, event)
      if (Array.isArray(patch.artifacts)) {
        this.artifacts = patch.artifacts
      }
      this.applyRunPatch(event.runId, patch)
    },

    async fetchRunTree(runId, maxDepth = 4) {
      try {
        const { data } = await agentsAPI.getRunTree(runId, maxDepth)
        const root = data?.root ? normalizeRunTreeNode(data.root) : null
        this.currentRunTree = root
        this.currentRunInvocations = collectRunTreeInvocations(root)
        return root
      } catch (error) {
        this.setError(error, 'Failed to fetch run tree')
        throw error
      }
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
        this.executionSurface = deriveRunState(run, []).surfaceMeta
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
        this.executionSurface = deriveRunState(run, []).surfaceMeta
        return run
      } catch (error) {
        this.setError(error, 'Failed to fetch run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchRunEvents(runId, afterSequence = 0, limit = 500, { exhaustive = afterSequence <= 0 } = {}) {
      this.loading = true
      this.error = null
      try {
        const events = await collectRunEventPages(
          async (cursor, pageLimit) => {
            const { data } = await agentsAPI.getRunEvents(runId, cursor, pageLimit)
            return (data.events || []).map(normalizeEvent)
          },
          { afterSequence, limit, exhaustive }
        )

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
      await Promise.all([
        this.fetchRunEvents(runId, 0, 500),
        this.fetchRunTree(runId).catch(() => null)
      ])

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
          if (
            normalized.runId === runId &&
            (normalized.eventType.startsWith('subagent.') || normalized.eventType === 'run.resumed')
          ) {
            this.fetchRunTree(runId).catch(() => null)
          }
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
        await this.fetchRunTree(run.id).catch(() => null)
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
        this.currentRunTree = null
        this.currentRunInvocations = []
        this.runEvents = []
        this.steps = []
        this.toolCalls = []
        this.plan = null
        this.artifacts = []
        this.executionSurface = deriveRunState(run, []).surfaceMeta
        this.subscribeToRun(run.id)
        return run
      } catch (error) {
        this.setError(error, 'Failed to resume run')
        throw error
      } finally {
        this.loading = false
      }
    },

    async reviewRunArtifact(runId, artifactId, payload = {}) {
      this.error = null
      try {
        const { data } = await agentsAPI.reviewRunArtifact(runId, artifactId, payload)
        const run = normalizeRun(data)
        this.currentRun = run
        this.upsertRun(run)
        this.steps = Array.isArray(run.steps) ? run.steps : []
        this.toolCalls = Array.isArray(run.toolCalls) ? run.toolCalls : []
        this.plan = run.plan && Object.keys(run.plan).length > 0 ? run.plan : null
        this.artifacts = Array.isArray(run.artifacts) ? run.artifacts : []
        this.executionSurface = deriveRunState(run, this.runEvents).surfaceMeta
        return data
      } catch (error) {
        this.setError(error, 'Failed to review artifact')
        throw error
      }
    },

    async writebackRunWorkspace(runId, payload = {}) {
      this.error = null
      try {
        const { data } = await agentsAPI.writebackRunWorkspace(runId, payload)
        const run = normalizeRun(data)
        this.currentRun = run
        this.upsertRun(run)
        this.steps = Array.isArray(run.steps) ? run.steps : []
        this.toolCalls = Array.isArray(run.toolCalls) ? run.toolCalls : []
        this.plan = run.plan && Object.keys(run.plan).length > 0 ? run.plan : null
        this.artifacts = Array.isArray(run.artifacts) ? run.artifacts : []
        this.executionSurface = deriveRunState(run, this.runEvents).surfaceMeta
        return data
      } catch (error) {
        this.setError(error, 'Failed to write back workspace')
        throw error
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
        const [serversResponse, governanceResponse] = await Promise.all([
          mcpAPI.listServers(),
          mcpAPI.getGovernance().catch(() => null)
        ])
        const { data } = serversResponse
        this.mcpServers = (data.servers || []).map(normalizeMCPServer)
        this.mcpGovernanceSummary = governanceResponse?.data?.summary
          ? normalizeMCPGovernanceSummary(governanceResponse.data.summary)
          : null
        return this.mcpServers
      } catch (error) {
        this.setError(error, 'Failed to fetch MCP servers')
        throw error
      }
    },

    setMCPBulkPreviewContext(preview = null) {
      this.mcpBulkPreviewContext = preview || null
      if (typeof localStorage === 'undefined') return
      if (preview) {
        localStorage.setItem(MCP_BULK_PREVIEW_STORAGE_KEY, JSON.stringify(redactMCPBulkPreviewForStorage(preview)))
      } else {
        localStorage.removeItem(MCP_BULK_PREVIEW_STORAGE_KEY)
      }
    },

    clearMCPBulkPreviewContext() {
      this.setMCPBulkPreviewContext(null)
    },

    async fetchTools(agentDefinitionId = '') {
      try {
        const { data } = await agentsAPI.listTools(agentDefinitionId)
        this.availableTools = (data.tools || []).map(normalizeToolSpec)
        this.availableToolsExecutionMode = normalizeExecutionMode(data.execution_mode || data.executionMode || {})
        return this.availableTools
      } catch (error) {
        this.setError(error, 'Failed to fetch agent tools')
        throw error
      }
    },

    async fetchRuntimeStatus() {
      try {
        const { data } = await agentsAPI.getRuntimeStatus()
        this.runtimeStatus = normalizeRuntimeStatus(data || {})
        this.workspaceInspection = this.runtimeStatus.workspace?.inspection || null
        return this.runtimeStatus
      } catch (error) {
        this.setError(error, 'Failed to fetch runtime status')
        throw error
      }
    },

    async inspectWorkspaces() {
      try {
        const { data } = await agentsAPI.inspectWorkspaces()
        this.workspaceInspection = data || null
        return this.workspaceInspection
      } catch (error) {
        this.setError(error, 'Failed to inspect workspaces')
        throw error
      }
    },

    async cleanupWorkspaces(params = {}) {
      try {
        const { data } = await agentsAPI.cleanupWorkspaces(params)
        this.workspaceCleanupResult = data || null
        return this.workspaceCleanupResult
      } catch (error) {
        this.setError(error, 'Failed to cleanup workspaces')
        throw error
      }
    },

    async cleanupWorkspaceLocks(params = {}) {
      try {
        const { data } = await agentsAPI.cleanupWorkspaceLocks(params)
        this.workspaceCleanupResult = data || null
        return this.workspaceCleanupResult
      } catch (error) {
        this.setError(error, 'Failed to cleanup workspace locks')
        throw error
      }
    },

    async fetchSubagents(includeArchived = false) {
      try {
        const { data } = await subagentsAPI.listSubagents(includeArchived)
        this.subagents = (data.subagents || []).map(normalizeSubagent)
        return this.subagents
      } catch (error) {
        this.setError(error, 'Failed to fetch subagents')
        throw error
      }
    },

    async updateAgentSubagents(agentId, subagentIds = []) {
      this.loading = true
      this.error = null
      try {
        await subagentsAPI.updateAgentSubagents(agentId, subagentIds)
        const nextSubagentIds = Array.isArray(subagentIds) ? [...subagentIds] : []
        const applyPatch = (agent) => {
          if (!agent || agent.id !== agentId) return agent
          return {
            ...agent,
            subagentIds: nextSubagentIds
          }
        }

        if (this.currentAgent?.id === agentId) {
          this.currentAgent = applyPatch(this.currentAgent)
        }
        this.agentDefinitions = this.agentDefinitions.map(applyPatch)
        return nextSubagentIds
      } catch (error) {
        this.setError(error, 'Failed to update agent subagents')
        throw error
      } finally {
        this.loading = false
      }
    }
  }
})
