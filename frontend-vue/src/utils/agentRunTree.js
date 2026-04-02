const parseJSONSafe = (value, fallback) => {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  if (typeof value === 'object') {
    return value
  }
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

const firstNonEmptyString = (...values) => {
  for (const value of values) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return ''
}

const normalizeReviewFinding = (raw = {}) => ({
  title: raw.title || raw.summary || raw.name || '未命名问题',
  description: raw.description || raw.details || raw.reason || '',
  severity: String(raw.severity || raw.level || 'medium').trim().toLowerCase() || 'medium',
  path: raw.path || raw.file || raw.filepath || '',
  line: raw.line ?? raw.line_number ?? raw.lineNumber ?? null,
  code: raw.code || ''
})

const normalizeStringList = (value) => {
  if (typeof value === 'string') {
    return value
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
  }
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item || '').trim()).filter(Boolean)
}

export const normalizeReviewResult = (raw = {}) => ({
  protocolVersion: raw.protocol_version || raw.protocolVersion || '',
  required: Boolean(raw.required),
  mode: raw.mode || 'none',
  approved: typeof raw.approved === 'boolean' ? raw.approved : null,
  decision: raw.decision || 'not_required',
  childStatus: raw.child_status || raw.childStatus || '',
  childRunId: raw.child_run_id || raw.childRunId || '',
  summary: raw.summary || '',
  conclusion: raw.conclusion || '',
  findingCount: Number(raw.finding_count || raw.findingCount || 0),
  blockingFindingCount: Number(raw.blocking_finding_count || raw.blockingFindingCount || 0),
  blockingSeverities: Array.isArray(raw.blocking_severities || raw.blockingSeverities)
    ? [...(raw.blocking_severities || raw.blockingSeverities)]
    : [],
  findings: Array.isArray(raw.findings) ? raw.findings.map(normalizeReviewFinding) : [],
  testGaps: Array.isArray(raw.test_gaps || raw.testGaps)
    ? [...(raw.test_gaps || raw.testGaps)]
    : [],
  explicitDecision: raw.explicit_decision || raw.explicitDecision || '',
  error: raw.error || ''
})

export const reviewDecisionLabel = (decision) => ({
  not_required: '未要求评审',
  approved: '通过',
  approved_with_findings: '通过但有提示',
  changes_requested: '要求修改',
  rejected: '拒绝',
  needs_input: '等待补充',
  failed: '执行失败',
  cancelled: '已取消',
  inconclusive: '结论不足'
}[decision] || decision || '未知')

export const reviewModeLabel = (mode) => ({
  reviewer: 'Reviewer',
  judge: 'Judge',
  none: '委派'
}[mode] || '委派')

export const normalizeSubagentProgress = (raw = {}) => {
  const state = String(raw.state || raw.status || '').trim().toLowerCase() || 'unknown'
  const completedItems = normalizeStringList(raw.completed_items || raw.completedItems)
  const pendingItems = normalizeStringList(raw.pending_items || raw.pendingItems)
  const summary = raw.summary || raw.message || ''
  const nextAction = raw.next_action || raw.nextAction || ''
  return {
    protocolVersion: raw.protocol_version || raw.protocolVersion || '',
    state,
    summary,
    completedItems,
    pendingItems,
    nextAction,
    artifactCount: Number(raw.artifact_count || raw.artifactCount || 0),
    source: raw.source || '',
    hasData: Boolean(summary || completedItems.length || pendingItems.length || nextAction || state !== 'unknown')
  }
}

export const progressStateLabel = (state) => ({
  requested: '已发起',
  in_progress: '进行中',
  blocked: '阻塞中',
  completed: '已完成',
  failed: '已失败',
  cancelled: '已取消',
  unknown: '未知'
}[state] || state || '未知')

export const normalizeSubagentClarification = (raw = {}) => {
  const question = raw.question || raw.prompt || ''
  const reason = raw.reason || ''
  const requiredFields = normalizeStringList(raw.required_fields || raw.requiredFields)
  const responseHint = raw.response_hint || raw.responseHint || ''
  const state = String(raw.state || raw.status || '').trim().toLowerCase() || 'not_required'
  return {
    protocolVersion: raw.protocol_version || raw.protocolVersion || '',
    state,
    question,
    reason,
    requiredFields,
    responseHint,
    blocking: Boolean(raw.blocking),
    source: raw.source || '',
    hasData: Boolean(question || reason || requiredFields.length || responseHint || state === 'required')
  }
}

export const clarificationStateLabel = (state) => ({
  required: '待澄清',
  resolved: '已澄清',
  not_required: '无需澄清'
}[state] || state || '无需澄清')

export const normalizeRunTreeInvocation = (raw = {}) => {
  const requestPayload = parseJSONSafe(raw.request_payload || raw.requestPayload, {})
  const resultPayload = parseJSONSafe(raw.result_payload || raw.resultPayload, {})
  return {
    id: raw.id || '',
    parentRunId: raw.parent_run_id || raw.parentRunId || '',
    parentStepId: raw.parent_step_id || raw.parentStepId || '',
    subagentDefinitionId: raw.subagent_definition_id || raw.subagentDefinitionId || '',
    publicationId: raw.publication_id || raw.publicationId || '',
    versionId: raw.version_id || raw.versionId || '',
    authorizationId: raw.authorization_id || raw.authorizationId || '',
    childRunId: raw.child_run_id || raw.childRunId || '',
    status: raw.status || 'pending',
    requestPayload,
    resultPayload,
    reviewResult: normalizeReviewResult(resultPayload.review_result || resultPayload.reviewResult || {}),
    errorMessage: raw.error_message || raw.errorMessage || '',
    startedAt: raw.started_at || raw.startedAt || null,
    completedAt: raw.completed_at || raw.completedAt || null,
    createdAt: raw.created_at || raw.createdAt || null,
    updatedAt: raw.updated_at || raw.updatedAt || null
  }
}

export const normalizeRunTreeNode = (raw = {}) => {
  const run = raw.run && typeof raw.run === 'object' ? raw.run : {}
  return {
    run: {
      id: run.id || '',
      agentDefinitionId: run.agent_definition_id || run.agentDefinitionId || '',
      tenantId: run.tenant_id || run.tenantId || '',
      userId: run.user_id || run.userId || '',
      sessionId: run.session_id || run.sessionId || '',
      status: run.status || 'queued',
      input: parseJSONSafe(run.input, {}),
      metadata: parseJSONSafe(run.metadata, {}),
      finalOutput: run.final_output || run.finalOutput || '',
      finalOutputText: run.final_output_text || run.finalOutputText || '',
      finalOutputJson: parseJSONSafe(run.final_output_json || run.finalOutputJson, null),
      errorMessage: run.error_message || run.errorMessage || '',
      startedAt: run.started_at || run.startedAt || null,
      finishedAt: run.finished_at || run.finishedAt || null,
      cancelledAt: run.cancelled_at || run.cancelledAt || null,
      createdAt: run.created_at || run.createdAt || null,
      updatedAt: run.updated_at || run.updatedAt || null
    },
    depth: Number(raw.depth || 0),
    invocations: Array.isArray(raw.invocations)
      ? raw.invocations.map((edge) => ({
          invocation: normalizeRunTreeInvocation(edge?.invocation || {}),
          childRun: edge?.child_run || edge?.childRun ? normalizeRunTreeNode(edge.child_run || edge.childRun) : null
        }))
      : []
  }
}

export const collectRunTreeNodes = (root) => {
  if (!root) return []
  const nodes = [root]
  for (const edge of root.invocations || []) {
    if (edge?.childRun) {
      nodes.push(...collectRunTreeNodes(edge.childRun))
    }
  }
  return nodes
}

export const collectRunTreeInvocations = (root) => {
  if (!root) return []
  const items = []
  for (const edge of root.invocations || []) {
    items.push({
      invocation: edge.invocation,
      childRun: edge.childRun || null,
      parentRun: root.run
    })
    if (edge?.childRun) {
      items.push(...collectRunTreeInvocations(edge.childRun))
    }
  }
  return items
}

export const summarizeInvocationTarget = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  const policySnapshot = requestPayload.policy_snapshot || requestPayload.policySnapshot || {}
  const target = policySnapshot.target || requestPayload.target || policySnapshot || {}
  if (target.name) return target.name
  if (target.slug) return target.slug
  if (invocation?.publicationId) return `publication ${invocation.publicationId.slice(0, 8)}`
  if (invocation?.subagentDefinitionId) return `subagent ${invocation.subagentDefinitionId.slice(0, 8)}`
  return '未命名专家能力'
}

export const summarizeInvocationTask = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  const task = requestPayload.task || {}
  return (
    task.delegate_task ||
    task.message ||
    task.reason ||
    ''
  )
}

export const getInvocationProtocolVersion = (invocation) => firstNonEmptyString(
  invocation?.requestPayload?.protocol_version,
  invocation?.requestPayload?.protocolVersion,
  invocation?.resultPayload?.protocol_version,
  invocation?.resultPayload?.protocolVersion
)

export const getInvocationQuestion = (invocation, childRun = null) => {
  const partialResult = invocation?.resultPayload?.partial_result || invocation?.resultPayload?.partialResult || {}
  const clarification = normalizeSubagentClarification(
    partialResult.clarification ||
    invocation?.resultPayload?.final_result?.clarification ||
    invocation?.resultPayload?.finalResult?.clarification ||
    {}
  )
  return firstNonEmptyString(
    clarification.question,
    partialResult.question,
    childRun?.run?.finalOutputText,
    childRun?.run?.finalOutput,
    invocation?.resultPayload?.final_result?.final_output_text,
    invocation?.resultPayload?.finalResult?.finalOutputText
  )
}

export const getInvocationProgress = (invocation) => normalizeSubagentProgress(
  invocation?.resultPayload?.partial_result?.progress ||
  invocation?.resultPayload?.partialResult?.progress ||
  invocation?.resultPayload?.final_result?.progress ||
  invocation?.resultPayload?.finalResult?.progress ||
  invocation?.requestPayload?.progress ||
  {}
)

export const getInvocationClarification = (invocation) => normalizeSubagentClarification(
  invocation?.resultPayload?.partial_result?.clarification ||
  invocation?.resultPayload?.partialResult?.clarification ||
  invocation?.resultPayload?.final_result?.clarification ||
  invocation?.resultPayload?.finalResult?.clarification ||
  invocation?.requestPayload?.clarification ||
  {}
)

export const getInvocationConstraints = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  return Array.isArray(requestPayload.constraints)
    ? requestPayload.constraints.map((item) => String(item || '').trim()).filter(Boolean)
    : []
}

export const getInvocationTaskPayload = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  return requestPayload.task || {}
}

export const buildInvocationProtocolEntry = (item = {}) => {
  const invocation = item.invocation || {}
  const childRun = item.childRun || null
  const task = getInvocationTaskPayload(invocation)
  const reviewResult = getInvocationReviewResult(invocation)
  const progress = getInvocationProgress(invocation)
  const clarification = getInvocationClarification(invocation)
  const question = getInvocationQuestion(invocation, childRun)
  return {
    id: invocation.id || '',
    target: summarizeInvocationTarget(invocation),
    status: childRun?.run?.status || invocation?.resultPayload?.status || invocation.status || 'pending',
    protocolVersion: getInvocationProtocolVersion(invocation),
    taskMessage: firstNonEmptyString(task.message, task.delegate_task, task.delegateTask),
    delegateReason: firstNonEmptyString(task.reason),
    constraints: getInvocationConstraints(invocation),
    question,
    progress,
    clarification,
    reviewSummary: summarizeInvocationReview(invocation),
    reviewResult,
    childRunId: invocation.childRunId || childRun?.run?.id || '',
    startedAt: invocation.startedAt || null,
    completedAt: invocation.completedAt || null
  }
}

export const getInvocationReviewResult = (invocation) => (
  invocation?.reviewResult || normalizeReviewResult(invocation?.resultPayload?.review_result || invocation?.resultPayload?.reviewResult || {})
)

export const summarizeInvocationReview = (invocation) => {
  const reviewResult = getInvocationReviewResult(invocation)
  if (!reviewResult.required && reviewResult.mode === 'none') {
    return ''
  }

  const parts = [`${reviewModeLabel(reviewResult.mode)} ${reviewDecisionLabel(reviewResult.decision)}`]
  if (reviewResult.blockingFindingCount > 0) {
    parts.push(`${reviewResult.blockingFindingCount} 条阻塞`)
  } else if (reviewResult.findingCount > 0) {
    parts.push(`${reviewResult.findingCount} 条 finding`)
  }
  if (reviewResult.childStatus && reviewResult.childStatus !== invocation?.status) {
    parts.push(`child ${reviewResult.childStatus}`)
  }
  return parts.join(' · ')
}
