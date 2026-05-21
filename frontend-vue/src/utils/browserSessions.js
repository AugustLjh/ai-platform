export const formatBrowserSessionHistoryLabel = (sample = {}, formatDateTime = (value) => value || '') => {
  const sampledAt = formatDateTime(sample.sampledAt || sample.sampled_at || null) || '未知时间'
  const active = Number(sample.activeSessionCount || sample.active_session_count || 0)
  const total = Number(sample.sessionCount || sample.session_count || 0)
  const expired = Number(sample.expiredSessionCount || sample.expired_session_count || 0)
  const networkErrors = Number(sample.networkErrorCount || sample.network_error_count || 0)
  const consoleMessages = Number(sample.consoleMessageCount || sample.console_message_count || 0)
  const health = sample.health && typeof sample.health === 'object' ? sample.health : {}
  const score = Number(health.score || 0)
  const status = health.status || 'unknown'

  return `${sampledAt} · 活跃 ${active}/${total} · 过期 ${expired} · 网络错误 ${networkErrors} · Console ${consoleMessages} · 健康 ${status} ${score}/100`
}

export const buildBrowserSessionTrendPoints = (history = []) => {
  if (!Array.isArray(history)) return []
  return history
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => {
      const score = Number(item.health?.score || 0)
      const expired = Number(item.expiredSessionCount || item.expired_session_count || 0)
      const networkErrors = Number(item.networkErrorCount || item.network_error_count || 0)
      const consoleMessages = Number(item.consoleMessageCount || item.console_message_count || 0)
      const risk = expired * 20 + networkErrors * 8 + Math.floor(consoleMessages / 3)
      return {
        index,
        sampledAt: item.sampledAt || item.sampled_at || null,
        score,
        expired,
        networkErrors,
        consoleMessages,
        risk,
      }
    })
}
