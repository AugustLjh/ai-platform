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

const normalizeNullableNumber = (value) => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const normalizeReviewFinding = (raw = {}) => ({
  title: raw.title || raw.summary || raw.name || '未命名问题',
  description: raw.description || raw.details || raw.reason || '',
  severity: String(raw.severity || raw.level || 'medium').trim().toLowerCase() || 'medium',
  path: raw.path || raw.file || raw.filepath || '',
  line: raw.line ?? raw.line_number ?? raw.lineNumber ?? null,
  code: raw.code || ''
})

export const statusLabel = (status) => ({
  idle: '待开始',
  pending: '待处理',
  queued: '排队中',
  running: '运行中',
  waiting_user: '等待补充',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}[status] || status || '未知状态')

const truncate = (value, limit = 220) => {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.length <= limit) return text
  return `${text.slice(0, limit - 1)}...`
}

export const normalizeGovernanceUsage = (raw = {}) => ({
  promptTokens: normalizeNullableNumber(raw.prompt_tokens ?? raw.promptTokens ?? raw.input_tokens ?? raw.inputTokens),
  completionTokens: normalizeNullableNumber(raw.completion_tokens ?? raw.completionTokens ?? raw.output_tokens ?? raw.outputTokens),
  totalTokens: normalizeNullableNumber(raw.total_tokens ?? raw.totalTokens),
  costUsd: normalizeNullableNumber(raw.cost_usd ?? raw.costUsd ?? raw.cost),
  source: raw.source || '',
  hasData: Boolean(
    normalizeNullableNumber(raw.prompt_tokens ?? raw.promptTokens ?? raw.input_tokens ?? raw.inputTokens) !== null ||
    normalizeNullableNumber(raw.completion_tokens ?? raw.completionTokens ?? raw.output_tokens ?? raw.outputTokens) !== null ||
    normalizeNullableNumber(raw.total_tokens ?? raw.totalTokens) !== null ||
    normalizeNullableNumber(raw.cost_usd ?? raw.costUsd ?? raw.cost) !== null
  )
})

const normalizeGovernanceLimits = (raw = {}) => ({
  allowNestedDelegation: raw.allow_nested_delegation ?? raw.allowNestedDelegation ?? null,
  maxDelegationDepth: normalizeNullableNumber(raw.max_delegation_depth ?? raw.maxDelegationDepth),
  maxParentDelegations: normalizeNullableNumber(raw.max_parent_delegations ?? raw.maxParentDelegations),
  maxConcurrentDelegations: normalizeNullableNumber(raw.max_concurrent_delegations ?? raw.maxConcurrentDelegations),
  maxRetryAttempts: normalizeNullableNumber(raw.max_retry_attempts ?? raw.maxRetryAttempts),
  timeoutSeconds: normalizeNullableNumber(raw.timeout_seconds ?? raw.timeoutSeconds),
  maxContextObservations: normalizeNullableNumber(raw.max_context_observations ?? raw.maxContextObservations)
})

const normalizeGovernanceBudget = (raw = {}) => ({
  maxTokens: normalizeNullableNumber(raw.max_tokens ?? raw.maxTokens ?? raw.token_limit ?? raw.tokenLimit),
  maxCostUsd: normalizeNullableNumber(raw.max_cost_usd ?? raw.maxCostUsd ?? raw.cost_limit_usd ?? raw.costLimitUsd),
  remainingTokens: normalizeNullableNumber(raw.remaining_tokens ?? raw.remainingTokens),
  remainingCostUsd: normalizeNullableNumber(raw.remaining_cost_usd ?? raw.remainingCostUsd),
  usageStatus: raw.usage_status || raw.usageStatus || '',
  usage: normalizeGovernanceUsage(raw.usage || {}),
  priorUsage: normalizeGovernanceUsage(raw.prior_usage || raw.priorUsage || {}),
  lastInvocationUsage: normalizeGovernanceUsage(raw.last_invocation_usage || raw.lastInvocationUsage || {}),
  raw
})

const normalizeGovernanceEnforcement = (raw = {}) => ({
  hardLimits: normalizeStringList(raw.hard_limits || raw.hardLimits),
  advisoryLimits: normalizeStringList(raw.advisory_limits || raw.advisoryLimits),
  note: raw.note || ''
})

const normalizeGovernanceBlocker = (raw = {}) => ({
  code: raw.code || '',
  message: raw.message || raw.reason || '',
  severity: raw.severity || 'error',
  recoverable: Boolean(raw.recoverable),
  recoveryActions: normalizeStringList(raw.recovery_actions || raw.recoveryActions),
  details: raw.details && typeof raw.details === 'object' ? raw.details : {}
})

const normalizeGovernanceRecovery = (raw = {}) => ({
  recoverable: Boolean(raw.recoverable),
  primaryCode: raw.primary_code || raw.primaryCode || '',
  summary: raw.summary || '',
  actions: normalizeStringList(raw.actions)
})

const normalizeGovernanceHistory = (raw = {}) => ({
  targetSlug: raw.target_slug || raw.targetSlug || '',
  attemptCount: Number(raw.attempt_count || raw.attemptCount || 0),
  failedAttemptCount: Number(raw.failed_attempt_count || raw.failedAttemptCount || 0),
  activeChildCount: Number(raw.active_child_count || raw.activeChildCount || 0),
  waitingUserCount: Number(raw.waiting_user_count || raw.waitingUserCount || 0),
  bubbleToParentCount: Number(raw.bubble_to_parent_count || raw.bubbleToParentCount || 0),
  continueParentCount: Number(raw.continue_parent_count || raw.continueParentCount || 0),
  childOnlyCount: Number(raw.child_only_count || raw.childOnlyCount || 0),
  statuses: normalizeStringList(raw.statuses),
  waitingUserStrategies: normalizeStringList(raw.waiting_user_strategies || raw.waitingUserStrategies)
})

export const normalizeGovernancePolicy = (raw = {}) => {
  const limits = normalizeGovernanceLimits(raw.limits || {})
  const budget = normalizeGovernanceBudget(raw.budget || {})
  const enforcement = normalizeGovernanceEnforcement(raw.enforcement || {})
  const blockers = Array.isArray(raw.blockers || raw.blockersList)
    ? (raw.blockers || raw.blockersList).map(normalizeGovernanceBlocker).filter((item) => item.code || item.message)
    : []
  const recovery = normalizeGovernanceRecovery(raw.recovery || {})
  const waitingUser = raw.waiting_user || raw.waitingUser || {}
  const warnings = normalizeStringList(raw.warnings)
  const history = normalizeGovernanceHistory(raw.history || {})
  const hasData = Boolean(
    (raw.protocol_version || raw.protocolVersion) ||
    Object.values(limits).some((value) => value !== null && value !== false) ||
    budget.maxTokens !== null ||
    budget.maxCostUsd !== null ||
    budget.remainingTokens !== null ||
    budget.remainingCostUsd !== null ||
    budget.usage.hasData ||
    budget.priorUsage.hasData ||
    budget.lastInvocationUsage.hasData ||
    budget.usageStatus ||
    enforcement.hardLimits.length > 0 ||
    enforcement.advisoryLimits.length > 0 ||
    enforcement.note ||
    blockers.length > 0 ||
    recovery.actions.length > 0 ||
    warnings.length > 0 ||
    history.attemptCount > 0 ||
    history.waitingUserCount > 0
  )
  return {
    protocolVersion: raw.protocol_version || raw.protocolVersion || '',
    targetSlug: raw.target_slug || raw.targetSlug || '',
    limits,
    budget,
    waitingUserPropagation: String(waitingUser.propagation || '').trim(),
    waitingUserCountsAsActiveChild: waitingUser.counts_as_active_child ?? waitingUser.countsAsActiveChild ?? null,
    enforcement,
    blockers,
    recovery,
    warnings,
    history,
    raw,
    hasData
  }
}

const getGovernancePayload = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  const resultPayload = invocation?.resultPayload || {}
  const requestGovernance = (
    requestPayload?.policy_snapshot?.governance_policy ||
    requestPayload?.policySnapshot?.governancePolicy ||
    requestPayload?.governance_policy ||
    requestPayload?.governancePolicy ||
    {}
  )
  const resultGovernance = (
    resultPayload?.governance_policy ||
    resultPayload?.governancePolicy ||
    {}
  )
  const requestObject = requestGovernance && typeof requestGovernance === 'object' ? requestGovernance : {}
  const resultObject = resultGovernance && typeof resultGovernance === 'object' ? resultGovernance : {}
  const mergeObjectField = (requestSource, resultSource, field) => {
    const requestField = requestSource?.[field] && typeof requestSource[field] === 'object' ? requestSource[field] : null
    const resultField = resultSource?.[field] && typeof resultSource[field] === 'object' ? resultSource[field] : null
    if (!requestField && !resultField) return null
    return {
      ...(requestField || {}),
      ...(resultField || {})
    }
  }
  const budget = mergeObjectField(requestObject, resultObject, 'budget')
  if (budget) {
    const requestBudget = requestObject.budget && typeof requestObject.budget === 'object' ? requestObject.budget : {}
    const resultBudget = resultObject.budget && typeof resultObject.budget === 'object' ? resultObject.budget : {}
    const usage = mergeObjectField(requestBudget, resultBudget, 'usage')
    if (usage) budget.usage = usage
    const priorUsage = mergeObjectField(requestBudget, resultBudget, 'prior_usage')
    if (priorUsage) budget.prior_usage = priorUsage
    const lastInvocationUsage = mergeObjectField(requestBudget, resultBudget, 'last_invocation_usage')
    if (lastInvocationUsage) budget.last_invocation_usage = lastInvocationUsage
  }
  return {
    ...requestObject,
    ...resultObject,
    ...(mergeObjectField(requestObject, resultObject, 'limits') ? { limits: mergeObjectField(requestObject, resultObject, 'limits') } : {}),
    ...(budget ? { budget } : {}),
    ...(mergeObjectField(requestObject, resultObject, 'waiting_user') ? { waiting_user: mergeObjectField(requestObject, resultObject, 'waiting_user') } : {}),
    ...(mergeObjectField(requestObject, resultObject, 'enforcement') ? { enforcement: mergeObjectField(requestObject, resultObject, 'enforcement') } : {}),
    ...(mergeObjectField(requestObject, resultObject, 'history') ? { history: mergeObjectField(requestObject, resultObject, 'history') } : {})
  }
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
  error: raw.error || '',
  gateBlocked: Boolean(raw.gate_blocked || raw.gateBlocked),
  gateBlockers: Array.isArray(raw.gate_blockers || raw.gateBlockers)
    ? (raw.gate_blockers || raw.gateBlockers).map(normalizeGovernanceBlocker).filter((item) => item.code || item.message)
    : [],
  recovery: normalizeGovernanceRecovery(raw.recovery || {})
})

export const reviewDecisionLabel = (decision) => ({
  not_required: '未要求评审',
  approved: '通过',
  approved_with_findings: '通过但有提示',
  changes_requested: '要求修改',
  rejected: '拒绝',
  review_gate_blocked: '评审阻断',
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
  return {
    protocolVersion: raw.protocol_version || raw.protocolVersion || '',
    state,
    summary: raw.summary || raw.message || '',
    completedItems,
    pendingItems,
    nextAction: raw.next_action || raw.nextAction || '',
    artifactCount: Number(raw.artifact_count || raw.artifactCount || 0),
    source: raw.source || '',
    waitingUserPath: normalizeWaitingUserPath(raw.waiting_user_path || raw.waitingUserPath),
    hasData: Boolean(
      raw.summary ||
      raw.message ||
      completedItems.length ||
      pendingItems.length ||
      raw.next_action ||
      raw.nextAction ||
      state !== 'unknown'
    )
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
    waitingUserPath: normalizeWaitingUserPath(raw.waiting_user_path || raw.waitingUserPath),
    hasData: Boolean(question || reason || requiredFields.length || responseHint || state === 'required')
  }
}

export const clarificationStateLabel = (state) => ({
  required: '待澄清',
  resolved: '已澄清',
  not_required: '无需澄清'
}[state] || state || '无需澄清')

export const normalizeWaitingUserPath = (value) => {
  if (!Array.isArray(value)) return []
  return value
    .map((entry) => {
      if (!entry || typeof entry !== 'object') return null
      return {
        runId: entry.run_id || entry.runId || '',
        role: String(entry.role || '').trim() || '',
        status: String(entry.status || '').trim() || '',
        targetSlug: entry.target_slug || entry.targetSlug || '',
        targetName: entry.target_name || entry.targetName || ''
      }
    })
    .filter(Boolean)
}

export const summarizeWaitingUserPath = (path) => {
  if (!Array.isArray(path) || path.length === 0) return ''
  return path
    .map((entry, index) => {
      const role = entry.role === 'parent' ? '父' : entry.role === 'child' ? '子' : `节点${index + 1}`
      const status = statusLabel(entry.status).replace('中', '')
      return `${role}:${status}`
    })
    .join(' -> ')
}

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
    governancePolicy: normalizeGovernancePolicy(getGovernancePayload({ requestPayload, resultPayload })),
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
      context: parseJSONSafe(run.context, {}),
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
  return task.delegate_task || task.message || task.reason || ''
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

export const getInvocationReviewResult = (invocation) => (
  invocation?.reviewResult || normalizeReviewResult(invocation?.resultPayload?.review_result || invocation?.resultPayload?.reviewResult || {})
)

export const summarizeInvocationReview = (invocation) => {
  const reviewResult = getInvocationReviewResult(invocation)
  if (!reviewResult.required && reviewResult.mode === 'none') {
    return ''
  }

  const parts = [`${reviewModeLabel(reviewResult.mode)} ${reviewDecisionLabel(reviewResult.decision)}`]
  if (reviewResult.gateBlocked) {
    parts.push('已阻断')
  }
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

export const getInvocationGovernancePolicy = (invocation) => (
  invocation?.governancePolicy || normalizeGovernancePolicy(getGovernancePayload(invocation))
)

export const summarizeGovernancePolicy = (governance) => {
  if (!governance.hasData) return ''

  const parts = []
  const { limits, budget, enforcement, history } = governance
  if (limits.timeoutSeconds !== null) {
    parts.push(`timeout ${limits.timeoutSeconds}s`)
  }
  if (limits.maxRetryAttempts !== null) {
    parts.push(`retry ${limits.maxRetryAttempts}`)
  }
  if (limits.maxConcurrentDelegations !== null) {
    parts.push(`并发 ${limits.maxConcurrentDelegations}`)
  }
  if (limits.maxDelegationDepth !== null) {
    parts.push(`深度 ${limits.maxDelegationDepth}`)
  }
  if (limits.maxParentDelegations !== null) {
    parts.push(`父级委派 ${limits.maxParentDelegations}`)
  }
  if (budget.maxTokens !== null) {
    if (budget.usage.totalTokens !== null) {
      parts.push(`tokens ${budget.usage.totalTokens}/${budget.maxTokens}`)
    } else {
      parts.push(`tokens ${budget.maxTokens}`)
    }
  } else if (budget.usage.totalTokens !== null) {
    parts.push(`已用 ${budget.usage.totalTokens} tokens`)
  }
  if (budget.maxCostUsd !== null) {
    if (budget.usage.costUsd !== null) {
      parts.push(`cost $${budget.usage.costUsd}/$${budget.maxCostUsd}`)
    } else {
      parts.push(`cost $${budget.maxCostUsd}`)
    }
  } else if (budget.usage.costUsd !== null) {
    parts.push(`已用 $${budget.usage.costUsd}`)
  }
  if (history.waitingUserCount > 0) {
    parts.push(`等待用户 ${history.waitingUserCount}`)
  }
  if (history.bubbleToParentCount > 0) {
    parts.push(`上浮 ${history.bubbleToParentCount}`)
  }
  if (history.continueParentCount > 0) {
    parts.push(`父级继续 ${history.continueParentCount}`)
  }
  if (governance.blockers.length > 0) {
    parts.push(`阻塞 ${governance.blockers.length}`)
  }
  if (governance.recovery.actions.length > 0) {
    parts.push(`恢复 ${governance.recovery.actions.length}`)
  }
  if (!parts.length && enforcement.hardLimits.length > 0) {
    parts.push(`${enforcement.hardLimits.length} 条硬限制`)
  }
  if (!parts.length && enforcement.advisoryLimits.length > 0) {
    parts.push(`${enforcement.advisoryLimits.length} 条预算提醒`)
  }
  return parts.join(' · ')
}

export const summarizeInvocationGovernance = (invocation) => {
  const governance = getInvocationGovernancePolicy(invocation)
  return summarizeGovernancePolicy(governance)
}

export const summarizeGovernanceBlockers = (governance) => {
  if (!governance?.blockers?.length) return ''
  return governance.blockers.map((blocker) => blocker.message || blocker.code).filter(Boolean).join(' · ')
}

export const buildGovernanceRecoverySummary = (governance) => {
  if (!governance?.recovery?.actions?.length) return ''
  return governance.recovery.actions.slice(0, 3).join(' · ')
}

export const getInvocationKnowledgeSummary = (invocation) => {
  const policySnapshot = invocation?.requestPayload?.policy_snapshot || invocation?.requestPayload?.policySnapshot || {}
  const policy = policySnapshot.knowledge_policy || policySnapshot.knowledgePolicy || {}
  return String(policy.mode || policy.access || '').trim()
}

export const getInvocationReviewRequirement = (invocation) => {
  const policySnapshot = invocation?.requestPayload?.policy_snapshot || invocation?.requestPayload?.policySnapshot || {}
  const reviewPolicy = policySnapshot.review_policy || policySnapshot.reviewPolicy || {}
  if (reviewPolicy.requires_judge) return '需要 judge'
  if (reviewPolicy.requires_reviewer || reviewPolicy.required) return '需要 reviewer'
  if (reviewPolicy.mode === 'judge') return 'Judge 能力'
  if (reviewPolicy.mode === 'reviewer') return 'Reviewer 能力'
  return ''
}

export const buildGovernanceBudgetLines = (governance) => {
  if (!governance?.hasData) return []
  const lines = []
  const { budget } = governance
  if (budget.usage.totalTokens !== null || budget.maxTokens !== null) {
    const line = budget.usage.totalTokens !== null
      ? `tokens ${budget.usage.totalTokens}${budget.maxTokens !== null ? ` / ${budget.maxTokens}` : ''}`
      : `tokens 上限 ${budget.maxTokens}`
    lines.push(line)
  }
  if (budget.usage.costUsd !== null || budget.maxCostUsd !== null) {
    const line = budget.usage.costUsd !== null
      ? `cost $${budget.usage.costUsd}${budget.maxCostUsd !== null ? ` / $${budget.maxCostUsd}` : ''}`
      : `cost 上限 $${budget.maxCostUsd}`
    lines.push(line)
  }
  if (budget.priorUsage.hasData) {
    lines.push(`历史累计 ${summarizeGovernanceUsageCompact(budget.priorUsage)}`)
  }
  if (budget.lastInvocationUsage.hasData) {
    lines.push(`本次 child ${summarizeGovernanceUsageCompact(budget.lastInvocationUsage)}`)
  }
  if (budget.remainingTokens !== null) {
    lines.push(`剩余 tokens ${budget.remainingTokens}`)
  }
  if (budget.remainingCostUsd !== null) {
    lines.push(`剩余 cost $${budget.remainingCostUsd}`)
  }
  if (budget.usageStatus) {
    lines.push(`预算状态 ${budget.usageStatus}`)
  }
  return lines
}

export const summarizeGovernanceUsageCompact = (usage) => {
  if (!usage?.hasData) return ''
  const parts = []
  if (usage.totalTokens !== null) parts.push(`${usage.totalTokens} tokens`)
  if (usage.costUsd !== null) parts.push(`$${usage.costUsd}`)
  return parts.join(' · ')
}

export const getInvocationWaitingUserPath = (invocation, childRun = null) => {
  const progress = getInvocationProgress(invocation)
  const clarification = getInvocationClarification(invocation)
  const finalResult = invocation?.resultPayload?.final_result || invocation?.resultPayload?.finalResult || {}
  const partialResult = invocation?.resultPayload?.partial_result || invocation?.resultPayload?.partialResult || {}
  const finalOutputJson = childRun?.run?.finalOutputJson && typeof childRun.run.finalOutputJson === 'object'
    ? childRun.run.finalOutputJson
    : {}
  const candidates = [
    clarification.waitingUserPath,
    progress.waitingUserPath,
    normalizeWaitingUserPath(partialResult.waiting_user_path || partialResult.waitingUserPath),
    normalizeWaitingUserPath(finalResult.waiting_user_path || finalResult.waitingUserPath),
    normalizeWaitingUserPath(finalOutputJson.waiting_user_path || finalOutputJson.waitingUserPath)
  ]
  for (const candidate of candidates) {
    if (candidate.length > 0) return candidate
  }
  return []
}

export const getInvocationResultSummary = (invocation, childRun = null) => {
  const resultPayload = invocation?.resultPayload || {}
  const finalResult = resultPayload.final_result || resultPayload.finalResult || {}
  const reviewResult = getInvocationReviewResult(invocation)
  const question = getInvocationQuestion(invocation, childRun)
  const progress = getInvocationProgress(invocation)
  const childStatus = childRun?.run?.status || resultPayload.status || invocation?.status || ''
  const text = firstNonEmptyString(
    reviewResult.conclusion,
    reviewResult.summary,
    finalResult.summary,
    finalResult.final_output_text,
    finalResult.final_output,
    childRun?.run?.finalOutputText,
    resultPayload.error,
    invocation?.errorMessage
  )
  if (childStatus === 'waiting_user' && question) return question
  if (progress.summary && childStatus !== 'completed') return progress.summary
  return text
}

export const getInvocationRecoverySummary = (invocation, childRun = null) => {
  const status = childRun?.run?.status || invocation?.resultPayload?.status || invocation?.status || ''
  const progress = getInvocationProgress(invocation)
  const clarification = getInvocationClarification(invocation)
  const waitingUserPath = getInvocationWaitingUserPath(invocation, childRun)
  const governance = getInvocationGovernancePolicy(invocation)
  const reviewResult = getInvocationReviewResult(invocation)
  const parts = []
  if (status === 'waiting_user') {
    parts.push('等待父级补充信息')
    if (clarification.requiredFields.length > 0) {
      parts.push(`需补充 ${clarification.requiredFields.join('、')}`)
    }
    if (progress.nextAction) {
      parts.push(progress.nextAction)
    }
  }
  if (status === 'failed') {
    parts.push('child 执行失败')
    if (progress.nextAction) {
      parts.push(progress.nextAction)
    } else if (governance.history.failedAttemptCount > 0) {
      parts.push(`历史失败 ${governance.history.failedAttemptCount} 次`)
    }
  }
  if (governance.blockers.length > 0) {
    parts.push(`阻塞 ${governance.blockers[0].message || governance.blockers[0].code}`)
  }
  if (governance.recovery.actions.length > 0) {
    parts.push(`恢复建议 ${governance.recovery.actions[0]}`)
  } else if (reviewResult.gateBlocked && reviewResult.recovery.actions.length > 0) {
    parts.push(`恢复建议 ${reviewResult.recovery.actions[0]}`)
  }
  if (waitingUserPath.length > 1) {
    parts.push(`链路 ${summarizeWaitingUserPath(waitingUserPath)}`)
  }
  return parts.join(' · ')
}

export const buildInvocationAttentionSummary = (item = {}) => {
  const invocation = item.invocation || {}
  const childRun = item.childRun || null
  const reviewSummary = summarizeInvocationReview(invocation)
  const governanceSummary = summarizeInvocationGovernance(invocation)
  const recoverySummary = getInvocationRecoverySummary(invocation, childRun)
  const progress = getInvocationProgress(invocation)
  const question = getInvocationQuestion(invocation, childRun)
  const parts = []
  if (question && (childRun?.run?.status === 'waiting_user' || invocation?.resultPayload?.status === 'waiting_user')) {
    parts.push(truncate(question, 140))
  } else if (progress.summary && progress.state !== 'completed') {
    parts.push(truncate(progress.summary, 140))
  }
  if (reviewSummary) parts.push(reviewSummary)
  if (recoverySummary) parts.push(recoverySummary)
  if (governanceSummary) parts.push(governanceSummary)
  return parts.join(' · ')
}

export const buildInvocationProtocolEntry = (item = {}) => {
  const invocation = item.invocation || {}
  const childRun = item.childRun || null
  const task = getInvocationTaskPayload(invocation)
  const reviewResult = getInvocationReviewResult(invocation)
  const governance = getInvocationGovernancePolicy(invocation)
  const progress = getInvocationProgress(invocation)
  const clarification = getInvocationClarification(invocation)
  const question = getInvocationQuestion(invocation, childRun)
  const waitingUserPath = getInvocationWaitingUserPath(invocation, childRun)
  const status = childRun?.run?.status || invocation?.resultPayload?.status || invocation.status || 'pending'
  return {
    id: invocation.id || '',
    target: summarizeInvocationTarget(invocation),
    status,
    statusLabel: statusLabel(status),
    protocolVersion: getInvocationProtocolVersion(invocation),
    taskMessage: firstNonEmptyString(task.message, task.delegate_task, task.delegateTask),
    delegateReason: firstNonEmptyString(task.reason),
    constraints: getInvocationConstraints(invocation),
    question,
    progress,
    clarification,
    governance,
    governanceSummary: summarizeInvocationGovernance(invocation),
    governanceBudgetLines: buildGovernanceBudgetLines(governance),
    reviewSummary: summarizeInvocationReview(invocation),
    reviewResult,
    reviewRequirement: getInvocationReviewRequirement(invocation),
    knowledgeSummary: getInvocationKnowledgeSummary(invocation),
    childRunId: invocation.childRunId || childRun?.run?.id || '',
    startedAt: invocation.startedAt || null,
    completedAt: invocation.completedAt || null,
    waitingUserPath,
    waitingUserPathSummary: summarizeWaitingUserPath(waitingUserPath),
    recoverySummary: getInvocationRecoverySummary(invocation, childRun),
    resultSummary: getInvocationResultSummary(invocation, childRun),
    attentionSummary: buildInvocationAttentionSummary(item),
    needsAttention: ['waiting_user', 'failed', 'cancelled'].includes(status) ||
      reviewResult.gateBlocked ||
      reviewResult.blockingFindingCount > 0 ||
      governance.warnings.length > 0,
    attentionTone: status === 'failed'
      ? 'danger'
      : status === 'waiting_user'
        ? 'warning'
        : (reviewResult.gateBlocked || reviewResult.blockingFindingCount > 0)
          ? 'danger'
          : 'neutral'
  }
}

export const buildRunTreeNodeSummary = (node = {}) => {
  const run = node.run || {}
  if (run.status === 'failed') {
    return run.errorMessage || '子任务执行失败。'
  }
  if (run.status === 'waiting_user') {
    const payload = run.finalOutputJson && typeof run.finalOutputJson === 'object' ? run.finalOutputJson : {}
    const question = firstNonEmptyString(
      payload.question,
      payload.clarification?.question,
      run.finalOutputText,
      run.finalOutput
    )
    return question || '子任务暂停，等待父 run 转译后继续。'
  }
  return run.finalOutputText || run.finalOutput || ''
}

export const buildRunTreeNodeView = (node = {}) => {
  const run = node.run || {}
  const attentionChildren = (node.invocations || []).filter((edge) => {
    const entry = buildInvocationProtocolEntry({
      invocation: edge.invocation,
      childRun: edge.childRun,
      parentRun: run
    })
    return entry.needsAttention
  }).length
  return {
    run,
    depth: node.depth || 0,
    statusLabel: statusLabel(run.status),
    title: firstNonEmptyString(run.input?.message, run.input?.prompt, run.finalOutputText, '未命名运行'),
    summary: buildRunTreeNodeSummary(node),
    childInvocationCount: (node.invocations || []).length,
    attentionChildCount: attentionChildren,
    hasNestedAttention: attentionChildren > 0
  }
}

export const buildPendingSubagentClarificationEntry = (run) => {
  const context = run?.context && typeof run.context === 'object' ? run.context : {}
  const payload = context.pending_subagent_clarification || context.pendingSubagentClarification
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const clarification = normalizeSubagentClarification(payload.clarification || {})
  const progress = normalizeSubagentProgress(payload.progress || {})
  const governance = normalizeGovernancePolicy(payload.governance_policy || payload.governancePolicy || {})
  const waitingUserPath = normalizeWaitingUserPath(payload.waiting_user_path || payload.waitingUserPath)
  const question = clarification.question || payload.question || run?.finalOutputText || ''

  if (!question && !clarification.hasData && !progress.hasData) {
    return null
  }

  return {
    question,
    reason: clarification.reason || '',
    responseHint: clarification.responseHint || '',
    requiredFields: clarification.requiredFields,
    progress,
    governance,
    governanceSummary: summarizeGovernancePolicy(governance),
    governanceBudgetLines: buildGovernanceBudgetLines(governance),
    childRunId: payload.child_run_id || payload.childRunId || '',
    targetName: payload.target?.name || '',
    targetSlug: payload.target?.slug || '',
    waitingUserPath,
    waitingUserPathSummary: summarizeWaitingUserPath(waitingUserPath),
    waitingUserPolicy: payload.waiting_user_policy || payload.waitingUserPolicy || {}
  }
}

const makeEventProtocolInvocation = (payload) => ({
  requestPayload: payload.handoff_envelope || payload.handoffEnvelope || {},
  resultPayload: {
    status: payload.child_status || payload.childStatus || payload.status || '',
    error: payload.error || '',
    review_result: payload.review_result || payload.reviewResult || {},
    governance_policy: payload.governance_policy || payload.governancePolicy || {},
    partial_result: payload.partial_result || payload.partialResult || {},
    final_result: {
      progress: payload.progress || {},
      clarification: payload.clarification || {},
      final_output_text: payload.final_output_text || payload.finalOutputText || '',
      summary: payload.summary || ''
    }
  },
  publicationId: payload.subagent_target?.publication_id || payload.subagentTarget?.publicationId || '',
  subagentDefinitionId: payload.subagent_target?.subagent_definition_id || payload.subagentTarget?.subagentDefinitionId || '',
  status: payload.status || ''
})

export const summarizeTimelineEvent = (event) => {
  const payload = event.payload || {}
  if (event.eventType.startsWith('subagent.')) {
    const invocation = makeEventProtocolInvocation(payload)
    const entry = buildInvocationProtocolEntry({ invocation, childRun: null, parentRun: null })
    const parts = [entry.target]
    if (entry.statusLabel) parts.push(entry.statusLabel)
    if (entry.reviewSummary) parts.push(entry.reviewSummary)
    if (entry.recoverySummary) parts.push(entry.recoverySummary)
    if (entry.governanceSummary) parts.push(`治理 ${entry.governanceSummary}`)
    if (payload.child_run_id || payload.childRunId) {
      parts.push(`child ${(payload.child_run_id || payload.childRunId).slice(0, 8)}`)
    }
    if (entry.attentionSummary) {
      parts.push(entry.attentionSummary)
    } else if (entry.taskMessage) {
      parts.push(entry.taskMessage)
    }
    return parts.filter(Boolean).join(' · ')
  }
  if (event.eventType === 'run.resumed') {
    return '恢复执行，当前 workspace 状态已切换到新一轮运行'
  }
  if (event.eventType === 'run.input_patched') {
    return `恢复前更新了输入: ${JSON.stringify(payload.input_patch || {})}`
  }
  if (payload.error) {
    return payload.error
  }
  if (payload.question) {
    return payload.question
  }
  if (payload.final_output_text) {
    return payload.final_output_text
  }
  if (payload.final_output) {
    return payload.final_output
  }
  if (Array.isArray(payload.artifacts) && payload.artifacts.length > 0) {
    return `生成了 ${payload.artifacts.length} 个结构化结果`
  }
  if (payload.output) {
    return JSON.stringify(payload.output, null, 2)
  }
  if (payload.title) {
    return payload.title
  }
  if (payload.tool_name) {
    return `工具 ${payload.tool_name}`
  }
  if (payload.status) {
    return `状态 ${payload.status}`
  }
  if (payload.input_patch) {
    return `输入已更新: ${JSON.stringify(payload.input_patch)}`
  }
  const keys = Object.keys(payload)
  if (keys.length === 0) {
    return '无附加数据'
  }
  return keys.map((key) => `${key}: ${String(payload[key])}`).slice(0, 3).join(' · ')
}
