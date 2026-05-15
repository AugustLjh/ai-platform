import {
  buildArtifactsFromStructuredResult,
  buildRunArtifactsFromToolCalls,
  mergeArtifacts,
  normalizeArtifact,
  normalizeRunResult
} from './agentArtifacts.js'

const executionBoundaryEventTypes = new Set(['run.resumed'])
const runStatusByEventType = {
  'run.started': 'running',
  'run.resumed': 'queued',
  'run.waiting_user': 'waiting_user',
  'run.completed': 'completed',
  'run.failed': 'failed',
  'run.cancelled': 'cancelled'
}

const getExecutionBoundary = (events = []) => {
  let boundaryIndex = -1
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (executionBoundaryEventTypes.has(events[index]?.eventType)) {
      boundaryIndex = index
      break
    }
  }
  return {
    boundaryIndex,
    activeEvents: boundaryIndex >= 0 ? events.slice(boundaryIndex) : events
  }
}

const deriveExecutionSurfaceMeta = (run, events, activeEvents, boundaryIndex) => {
  const resumedEvents = Array.isArray(events)
    ? events.filter((event) => event?.eventType === 'run.resumed')
    : []
  const boundaryEvent = boundaryIndex >= 0 ? events[boundaryIndex] : (events[0] || null)
  const latestEvent = activeEvents[activeEvents.length - 1] || events[events.length - 1] || null
  const source = events.length > 0 ? 'event_replay' : 'persisted_snapshot'

  return {
    source,
    isPersistedSnapshot: source === 'persisted_snapshot',
    hasEmptyEventHistory: events.length === 0,
    attemptIndex: Math.max(1, resumedEvents.length + 1),
    resumed: Boolean(boundaryEvent && boundaryEvent.eventType === 'run.resumed'),
    boundaryEventType: boundaryEvent?.eventType || '',
    boundarySequence: Number(boundaryEvent?.sequence || 0),
    activeEventCount: activeEvents.length,
    latestEventType: latestEvent?.eventType || '',
    latestEventSequence: Number(latestEvent?.sequence || 0),
    runStatus: latestEvent?.payload?.status || latestEvent?.status || run?.status || ''
  }
}

export const deriveRunState = (run, events) => {
  const stepsMap = new Map((Array.isArray(run?.steps) ? run.steps : []).map((step) => [step.id, { ...step }]))
  const toolCallMap = new Map((Array.isArray(run?.toolCalls) ? run.toolCalls : []).map((toolCall) => [toolCall.id, { ...toolCall }]))
  let plan = run?.plan && Object.keys(run.plan).length > 0 ? run.plan : null
  let finalOutput = run?.finalOutput || ''
  let finalOutputText = run?.finalOutputText || ''
  let finalOutputJson = run?.finalOutputJson || null
  let artifacts = Array.isArray(run?.artifacts) ? [...run.artifacts] : []
  let context = run?.context && typeof run.context === 'object' ? { ...run.context } : {}
  const { boundaryIndex, activeEvents } = getExecutionBoundary(events)

  const captureResultPayload = (payload = {}) => {
    const output = payload.output && typeof payload.output === 'object' ? payload.output : null
    const hasFinalResultSurface = (
      payload.final_output !== undefined ||
      payload.final_output_text !== undefined ||
      payload.final_output_json !== undefined ||
      output?.final_output !== undefined ||
      output?.final_output_text !== undefined ||
      output?.final_output_json !== undefined
    )

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
      const nextArtifacts = payload.artifacts.map(normalizeArtifact)
      artifacts = hasFinalResultSurface ? nextArtifacts : mergeArtifacts(artifacts, nextArtifacts)
    } else if (Array.isArray(output?.artifacts)) {
      const nextArtifacts = output.artifacts.map(normalizeArtifact)
      artifacts = hasFinalResultSurface ? nextArtifacts : mergeArtifacts(artifacts, nextArtifacts)
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
      context = {
        ...context
      }
      stepsMap.clear()
      toolCallMap.clear()
    }

    captureResultPayload(payload)

    if (event.eventType === 'plan.created' && payload.plan) {
      plan = payload.plan
    }

    if (event.eventType === 'workspace.bound') {
      context = {
        ...context,
        workspace: payload,
        workspace_root: payload.root || context.workspace_root || ''
      }
      artifacts = mergeArtifacts(artifacts, [normalizeArtifact({
        artifact_type: 'workspace_summary',
        name: 'Workspace Binding',
        payload,
        metadata: {
          source: 'run_event',
          event_type: event.eventType,
          event_sequence: event.sequence
        },
        created_at: event.createdAt
      })])
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
        if (payload.result && typeof payload.result === 'object') {
          existing.result = payload.result
        } else if (payload.output && typeof payload.output === 'object') {
          existing.result = payload.output.tool_result || payload.output || existing.result
        }
      }

      if (event.eventType === 'tool.cancelled') {
        existing.status = 'cancelled'
        existing.error = payload.error || existing.error
        if (payload.result && typeof payload.result === 'object') {
          existing.result = payload.result
        } else if (payload.output && typeof payload.output === 'object') {
          existing.result = payload.output.tool_result || payload.output || existing.result
        }
      }

      toolCallMap.set(toolCallId, existing)
    }
  }

  const derivedToolCalls = [...toolCallMap.values()].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())

  artifacts = mergeArtifacts(
    artifacts,
    buildArtifactsFromStructuredResult(finalOutputJson, finalOutputText || finalOutput)
  )
  artifacts = buildRunArtifactsFromToolCalls(derivedToolCalls, artifacts)

  const derivedSteps = [...stepsMap.values()].sort((a, b) => {
    if (a.stepIndex === b.stepIndex) {
      return new Date(a.createdAt || 0).getTime() - new Date(b.createdAt || 0).getTime()
    }
    return a.stepIndex - b.stepIndex
  })

  return {
    surfaceMeta: deriveExecutionSurfaceMeta(run, events, activeEvents, boundaryIndex),
    plan,
    steps: derivedSteps,
    toolCalls: derivedToolCalls,
    artifacts,
    context,
    runPatch: {
      finalOutput: finalOutputText || finalOutput,
      finalOutputText: finalOutputText || finalOutput,
      finalOutputJson,
      context,
      steps: derivedSteps,
      toolCalls: derivedToolCalls,
      artifacts: mergeArtifacts(artifacts)
    }
  }
}

export const buildRunEventPatch = (currentRun, event) => {
  const payload = event.payload || {}
  const patch = {}

  if (payload.status || runStatusByEventType[event.eventType]) {
    patch.status = payload.status || runStatusByEventType[event.eventType]
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
    patch.context = {
      ...(currentRun?.context || {})
    }
    delete patch.context.pending_question
    delete patch.context.pendingQuestion
    delete patch.context.pending_subagent_clarification
    delete patch.context.pendingSubagentClarification
    delete patch.context.ask_user_guard
    delete patch.context.askUserGuard
  }

  if (event.eventType === 'run.resumed') {
    patch.startedAt = null
  }

  if (event.eventType === 'run.started') {
    patch.startedAt = event.createdAt || currentRun?.startedAt || null
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
    const nextArtifacts = payload.artifacts.map(normalizeArtifact)
    const hasFinalResultSurface = (
      payload.final_output !== undefined ||
      payload.final_output_text !== undefined ||
      payload.final_output_json !== undefined ||
      event.eventType === 'run.completed' ||
      event.eventType === 'run.waiting_user' ||
      event.eventType === 'run.failed' ||
      event.eventType === 'run.cancelled'
    )

    if (hasFinalResultSurface) {
      const normalized = normalizeRunResult({
        final_output: patch.finalOutput !== undefined ? patch.finalOutput : currentRun?.finalOutput,
        final_output_text: patch.finalOutputText !== undefined ? patch.finalOutputText : currentRun?.finalOutputText,
        final_output_json: patch.finalOutputJson !== undefined ? patch.finalOutputJson : currentRun?.finalOutputJson,
        artifacts: mergeArtifacts(nextArtifacts)
      })
      patch.artifacts = buildRunArtifactsFromToolCalls(currentRun?.toolCalls || [], normalized.artifacts)
    } else {
      patch.artifacts = mergeArtifacts(currentRun?.artifacts || [], nextArtifacts)
    }
  }

  if (payload.error) {
    patch.errorMessage = payload.error
  }

  if (event.eventType === 'run.completed') {
    patch.finishedAt = event.createdAt || currentRun?.finishedAt || null
    patch.cancelledAt = null
  }

  if (event.eventType === 'run.failed') {
    patch.finishedAt = event.createdAt || currentRun?.finishedAt || null
  }

  if (event.eventType === 'run.cancelled') {
    patch.cancelledAt = event.createdAt || currentRun?.cancelledAt || null
  }

  if (payload.input_patch && currentRun?.id === event.runId) {
    patch.input = {
      ...(currentRun?.input || {}),
      ...payload.input_patch
    }
  }

  if (payload.context_patch && currentRun?.id === event.runId) {
    patch.context = {
      ...(currentRun?.context || {}),
      ...payload.context_patch
    }
  }

  return patch
}
