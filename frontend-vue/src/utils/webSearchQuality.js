export const normalizeWebSearchQualityCase = (raw = {}) => {
  const checks = Array.isArray(raw.checks)
    ? raw.checks.map((check) => ({
        name: check.name || '',
        passed: Boolean(check.passed),
        weight: Number(check.weight || 0),
        summary: check.summary || '',
        details: check.details && typeof check.details === 'object' ? { ...check.details } : {}
      }))
    : []
  const acceptedCount = Number(raw.accepted_count || raw.acceptedCount || 0)
  const rejectedCount = Number(raw.rejected_count || raw.rejectedCount || 0)
  const totalResults = Number(raw.total_results || raw.totalResults || (acceptedCount + rejectedCount))

  return {
    kind: raw.kind || 'web_search',
    name: raw.name || 'web search quality case',
    status: raw.status || 'unknown',
    score: Number(raw.score || 0),
    summary: raw.summary || '',
    policySnapshot: raw.policy_snapshot || raw.policySnapshot || null,
    totalResults,
    acceptedRatio: Number(raw.accepted_ratio || raw.acceptedRatio || (totalResults > 0 ? acceptedCount / totalResults : 1)),
    checkCount: Number(raw.check_count || raw.checkCount || checks.length),
    passedCheckCount: Number(raw.passed_check_count || raw.passedCheckCount || checks.filter((check) => check.passed).length),
    failedCheckCount: Number(raw.failed_check_count || raw.failedCheckCount || checks.filter((check) => !check.passed).length),
    rejectionReasonCounts: raw.rejection_reason_counts || raw.rejectionReasonCounts || {},
    acceptedCount,
    rejectedCount,
    accepted: Array.isArray(raw.accepted) ? [...raw.accepted] : [],
    rejected: Array.isArray(raw.rejected) ? [...raw.rejected] : [],
    checks
  }
}

export const formatWebSearchPolicySnapshot = (policySnapshot = null) => {
  if (!policySnapshot || typeof policySnapshot !== 'object') return ''
  const parts = []
  const allowedDomains = Array.isArray(policySnapshot.allowed_domains || policySnapshot.allowedDomains)
    ? [...(policySnapshot.allowed_domains || policySnapshot.allowedDomains)]
    : []
  const deniedDomains = Array.isArray(policySnapshot.denied_domains || policySnapshot.deniedDomains)
    ? [...(policySnapshot.denied_domains || policySnapshot.deniedDomains)]
    : []
  const allowedSchemes = Array.isArray(policySnapshot.search_allowed_schemes || policySnapshot.searchAllowedSchemes || policySnapshot.allowedSchemes)
    ? [...(policySnapshot.search_allowed_schemes || policySnapshot.searchAllowedSchemes || policySnapshot.allowedSchemes)]
    : []
  if (allowedDomains.length > 0) parts.push(`允许域名 ${allowedDomains.join(', ')}`)
  if (deniedDomains.length > 0) parts.push(`拒绝域名 ${deniedDomains.join(', ')}`)
  if (allowedSchemes.length > 0) parts.push(`scheme ${allowedSchemes.join(', ')}`)
  if (policySnapshot.search_require_url || policySnapshot.searchRequireUrl || policySnapshot.requireUrl) parts.push('要求 URL')
  if (policySnapshot.search_require_title || policySnapshot.searchRequireTitle || policySnapshot.requireTitle) parts.push('要求标题')
  if (policySnapshot.search_require_snippet || policySnapshot.searchRequireSnippet || policySnapshot.requireSnippet) parts.push('要求摘要')
  if (policySnapshot.search_reject_disallowed_domains || policySnapshot.searchRejectDisallowedDomains || policySnapshot.rejectDisallowedDomains) parts.push('拒绝未授权域名')
  if (policySnapshot.search_reject_duplicates || policySnapshot.searchRejectDuplicates || policySnapshot.rejectDuplicates) parts.push('拒绝重复结果')
  return parts.join(' · ')
}

export const normalizeWebSearchQualityEvaluation = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  const policySnapshot = raw.policy_snapshot || raw.policySnapshot || null
  const results = Array.isArray(raw.results) ? raw.results.map(normalizeWebSearchQualityCase) : []
  const acceptedCount = Number(raw.accepted_count || raw.acceptedCount || results.reduce((sum, item) => sum + item.acceptedCount, 0))
  const rejectedCount = Number(raw.rejected_count || raw.rejectedCount || results.reduce((sum, item) => sum + item.rejectedCount, 0))
  const totalResults = Number(raw.total_results || raw.totalResults || results.reduce((sum, item) => sum + item.totalResults, 0) || acceptedCount + rejectedCount)
  const passedCheckCount = Number(raw.passed_check_count || raw.passedCheckCount || results.reduce((sum, item) => sum + item.passedCheckCount, 0))
  const failedCheckCount = Number(raw.failed_check_count || raw.failedCheckCount || results.reduce((sum, item) => sum + item.failedCheckCount, 0))
  const caseSummaries = Array.isArray(raw.case_summaries || raw.caseSummaries)
    ? (raw.case_summaries || raw.caseSummaries).map((item) => ({
        name: item?.name || '',
        status: item?.status || 'unknown',
        score: Number(item?.score || 0),
        summary: item?.summary || '',
        acceptedCount: Number(item?.accepted_count || item?.acceptedCount || 0),
        rejectedCount: Number(item?.rejected_count || item?.rejectedCount || 0),
        failedCheckCount: Number(item?.failed_check_count || item?.failedCheckCount || 0)
      }))
    : []
  return {
    ...raw,
    protocolVersion: raw.protocol_version || raw.protocolVersion || '',
    suiteName: raw.suite_name || raw.suiteName || '',
    suiteSource: raw.suite_source || raw.suiteSource || '',
    status: raw.status || 'unknown',
    total: Number(raw.total || results.length),
    passed: Number(raw.passed || 0),
    warning: Number(raw.warning || 0),
    failed: Number(raw.failed || 0),
    averageScore: Number(raw.average_score || raw.averageScore || 0),
    summary: raw.summary || '',
    policySnapshot,
    totalResults,
    acceptedCount,
    rejectedCount,
    acceptedRatio: Number(raw.accepted_ratio || raw.acceptedRatio || (totalResults > 0 ? acceptedCount / totalResults : 1)),
    checkCount: Number(raw.check_count || raw.checkCount || passedCheckCount + failedCheckCount || results.reduce((sum, item) => sum + item.checkCount, 0)),
    passedCheckCount,
    failedCheckCount,
    rejectionReasonCounts: raw.rejection_reason_counts || raw.rejectionReasonCounts || {},
    caseSummaries,
    results: results.map((item) => ({
      ...item,
      policySnapshot: item.policySnapshot || policySnapshot
    }))
  }
}

export const webSearchQualityTone = (status = 'unknown') => {
  if (status === 'passed' || status === 'healthy') return 'ready'
  if (status === 'failed' || status === 'critical') return 'danger'
  return 'warning'
}

export const summarizeWebSearchQualityEvaluation = (evaluation = null) => {
  if (!evaluation) return ''
  const score = Number(evaluation.averageScore || evaluation.average_score || 0)
  const summary = evaluation.summary || `${evaluation.passed || 0} passed / ${evaluation.warning || 0} warning / ${evaluation.failed || 0} failed`
  const accepted = Number(evaluation.acceptedCount || evaluation.accepted_count || 0)
  const rejected = Number(evaluation.rejectedCount || evaluation.rejected_count || 0)
  const checks = Number(evaluation.passedCheckCount || evaluation.passed_check_count || 0) + Number(evaluation.failedCheckCount || evaluation.failed_check_count || 0)
  return `${evaluation.status || 'unknown'} · ${summary} · avg ${score.toFixed(2)} · accepted ${accepted} · rejected ${rejected} · checks ${checks}`
}
