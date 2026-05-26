export const summarizeEvaluationHistory = (items = [], meta = null, formatDateTime = (value) => value || '') => {
  const history = Array.isArray(items) ? items : []
  if (history.length === 0) return ''
  const current = history[0] || {}
  const currentSummary = current.summary && typeof current.summary === 'object' ? current.summary : {}
  const currentScore = Number(currentSummary.average_score || currentSummary.averageScore || 0)
  const currentStatus = current.status || currentSummary.status || 'unknown'
  const currentTime = formatDateTime(current.createdAt || current.created_at)
  const comparison = meta && typeof meta === 'object' ? meta.historyComparison || meta.history_comparison : null
  const comparisonDelta = comparison && comparison.delta && typeof comparison.delta === 'object' ? comparison.delta : null
  const comparisonCurrent = comparison && comparison.current && typeof comparison.current === 'object' ? comparison.current : null
  const comparisonSummary = comparison && typeof comparison.summary === 'string' ? comparison.summary.trim() : ''
  const trend = comparison && comparison.trend && typeof comparison.trend === 'object'
    ? comparison.trend
    : (meta?.historySummary?.trend && typeof meta.historySummary.trend === 'object' ? meta.historySummary.trend : null)
  const trendSummary = trend && typeof trend.summary === 'string' ? trend.summary.trim() : ''
  if (history.length === 1) {
    return `${currentStatus} · avg ${currentScore.toFixed(2)} · ${currentTime || '最近一次'}`
  }
  const previous = history[1] || {}
  const previousSummary = previous.summary && typeof previous.summary === 'object' ? previous.summary : {}
  const previousScore = Number(previousSummary.average_score || previousSummary.averageScore || 0)
  const delta = comparisonDelta && typeof comparisonDelta.score === 'number'
    ? comparisonDelta.score
    : currentScore - previousScore
  const parts = [`${currentStatus} · avg ${currentScore.toFixed(2)}`]
  if (comparisonCurrent && comparisonCurrent.current_total !== undefined) {
    parts.push(`${Number(comparisonCurrent.current_passed || 0)}/${Number(comparisonCurrent.current_total || 0)}`)
  }
  if (comparisonCurrent?.readiness) {
    parts.push(String(comparisonCurrent.readiness))
  }
  if (comparisonCurrent?.blocking_check_count !== undefined) {
    parts.push(`blockers ${Number(comparisonCurrent.blocking_check_count || 0)}`)
  }
  if (comparisonCurrent?.evidence_quality_score !== undefined) {
    parts.push(`evidence ${Number(comparisonCurrent.evidence_quality_score || 0).toFixed(2)}`)
  }
  if (comparisonSummary) {
    parts.push(comparisonSummary)
  } else {
    parts.push(`较上次 ${delta === 0 ? '持平' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}`)
  }
  if (trendSummary) {
    parts.push(trendSummary)
  }
  parts.push(currentTime || '最近一次')
  return parts.join(' · ')
}
