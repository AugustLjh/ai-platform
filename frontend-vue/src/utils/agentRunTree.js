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

const normalizeReviewFinding = (raw = {}) => ({
  title: raw.title || raw.summary || raw.name || '未命名问题',
  description: raw.description || raw.details || raw.reason || '',
  severity: String(raw.severity || raw.level || 'medium').trim().toLowerCase() || 'medium',
  path: raw.path || raw.file || raw.filepath || '',
  line: raw.line ?? raw.line_number ?? raw.lineNumber ?? null,
  code: raw.code || ''
})

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
