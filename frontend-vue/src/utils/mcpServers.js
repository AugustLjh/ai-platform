const connectionStatusMap = {
  healthy: '连接正常',
  degraded: '连接异常',
  untested: '未测试',
  disabled: '已禁用'
}

const catalogStatusMap = {
  ready: 'Catalog 就绪',
  stale: 'Catalog 过期',
  empty: 'Catalog 为空',
  missing: '未刷新',
  disabled: '已禁用'
}

const availabilityStatusMap = {
  available: '可投入使用',
  warning: '可用但需关注',
  degraded: '不建议使用',
  unavailable: '不可用',
  disabled: '已禁用'
}

export const summarizeCatalogAge = (catalog) => {
  if (!catalog?.refreshedAt) return '尚未刷新'
  if (catalog.ageSeconds === null || catalog.ageSeconds === undefined) return '刚刚刷新'
  const seconds = Number(catalog.ageSeconds)
  if (seconds < 60) return `${seconds} 秒前`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  return `${Math.floor(seconds / 86400)} 天前`
}

export const statusTone = (kind, status) => {
  const normalized = String(status || '').trim() || 'default'
  return `${kind}-${normalized}`
}

export const statusLabel = (kind, status) => {
  if (kind === 'connection') return connectionStatusMap[status] || status || '未知状态'
  if (kind === 'catalog') return catalogStatusMap[status] || status || '未知状态'
  return availabilityStatusMap[status] || status || '未知状态'
}

export const serverStatusLabel = (server) => {
  if (server?.status !== 'active') return '已禁用'
  if (server?.availability?.status) return statusLabel('availability', server.availability.status)
  if (server?.catalog?.status) return statusLabel('catalog', server.catalog.status)
  if (server?.connection?.status) return statusLabel('connection', server.connection.status)
  return '状态未知'
}

export const serverCatalogSummary = (server) => {
  const toolCount = server?.catalog?.toolCount ?? server?.tools?.length ?? 0
  const age = summarizeCatalogAge(server?.catalog)
  return `${toolCount} 个 catalog tools · ${age}`
}

export const serverCardTone = (server) => {
  if (server?.status !== 'active' || server?.availability?.status === 'disabled') return 'tone-disabled'
  if (!server?.availability?.bindable) return 'tone-danger'
  if (server?.catalog?.isStale || server?.availability?.status === 'warning') return 'tone-warning'
  if (server?.availability?.status === 'available') return 'tone-ready'
  return 'tone-neutral'
}

export const normalizeMCPBindingUsage = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    agentCount: Number(raw.agent_count || raw.agentCount || 0),
    activeAgentCount: Number(raw.active_agent_count || raw.activeAgentCount || 0),
    inactiveAgentCount: Number(raw.inactive_agent_count || raw.inactiveAgentCount || 0),
    summary: raw.summary || '',
    moreCount: Number(raw.more_count || raw.moreCount || 0),
    agents: Array.isArray(raw.agents)
      ? raw.agents.map((agent) => ({
          agentId: agent.agent_id || agent.agentId || '',
          name: agent.name || '',
          status: agent.status || 'active'
        }))
      : []
  }
}

export const normalizeMCPRecovery = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    status: raw.status || 'healthy',
    severity: raw.severity || 'info',
    summary: raw.summary || '',
    failureMode: raw.failure_mode || raw.failureMode || '',
    recoverable: Boolean(raw.recoverable),
    actions: Array.isArray(raw.actions)
      ? raw.actions.map((action) => ({
          type: action.type || '',
          label: action.label || '',
          description: action.description || '',
          priority: action.priority || ''
        }))
      : [],
    impact: raw.impact && typeof raw.impact === 'object'
      ? {
          agentCount: Number(raw.impact.agent_count || raw.impact.agentCount || 0),
          activeAgentCount: Number(raw.impact.active_agent_count || raw.impact.activeAgentCount || 0),
          inactiveAgentCount: Number(raw.impact.inactive_agent_count || raw.impact.inactiveAgentCount || 0),
          summary: raw.impact.summary || ''
        }
      : null
  }
}

export const normalizeMCPEvent = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    id: raw.id || '',
    tenantId: raw.tenant_id || raw.tenantId || '',
    serverId: raw.server_id || raw.serverId || '',
    serverName: raw.server_name || raw.serverName || '',
    eventType: raw.event_type || raw.eventType || '',
    actionType: raw.action_type || raw.actionType || '',
    status: raw.status || '',
    failureMode: raw.failure_mode || raw.failureMode || '',
    summary: raw.summary || '',
    details: raw.details && typeof raw.details === 'object' ? raw.details : {},
    actorUserId: raw.actor_user_id || raw.actorUserId || '',
    createdAt: raw.created_at || raw.createdAt || null
  }
}

export const normalizeMCPSecurityScore = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    score: Number(raw.score || 0),
    maxScore: Number(raw.max_score || raw.maxScore || 100),
    status: raw.status || 'unknown',
    riskLevel: raw.risk_level || raw.riskLevel || 'unknown',
    summary: raw.summary || '',
    evaluatedAt: raw.evaluated_at || raw.evaluatedAt || null,
    breakdown: Array.isArray(raw.breakdown)
      ? raw.breakdown.map((item) => ({
          key: item.key || '',
          label: item.label || '',
          score: Number(item.score || 0),
          maxScore: Number(item.max_score || item.maxScore || 0),
          status: item.status || '',
          summary: item.summary || ''
        }))
      : []
  }
}

export const normalizeMCPAuditReport = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  const overview = raw.overview && typeof raw.overview === 'object' ? raw.overview : {}
  return {
    tenantId: raw.tenant_id || raw.tenantId || '',
    generatedAt: raw.generated_at || raw.generatedAt || null,
    overview: {
      totalServers: Number(overview.total_servers || overview.totalServers || 0),
      averageScore: Number(overview.average_score || overview.averageScore || 0),
      medianScore: Number(overview.median_score || overview.medianScore || 0),
      lowRiskCount: Number(overview.low_risk_count || overview.lowRiskCount || 0),
      mediumRiskCount: Number(overview.medium_risk_count || overview.mediumRiskCount || 0),
      highRiskCount: Number(overview.high_risk_count || overview.highRiskCount || 0),
      criticalRiskCount: Number(overview.critical_risk_count || overview.criticalRiskCount || 0),
      blockedCount: Number(overview.blocked_count || overview.blockedCount || 0),
      recoveringCount: Number(overview.recovering_count || overview.recoveringCount || 0),
      staleCount: Number(overview.stale_count || overview.staleCount || 0),
      untestedCount: Number(overview.untested_count || overview.untestedCount || 0)
    },
    topRiskServers: Array.isArray(raw.top_risk_servers || raw.topRiskServers)
      ? (raw.top_risk_servers || raw.topRiskServers).map((server) => ({
          serverId: server.server_id || server.serverId || '',
          serverName: server.server_name || server.serverName || '',
          transport: server.transport || '',
          status: server.status || '',
          score: Number(server.score || 0),
          riskLevel: server.risk_level || server.riskLevel || '',
          summary: server.summary || '',
          failureMode: server.failure_mode || server.failureMode || '',
          recoverable: Boolean(server.recoverable),
          bindingCount: Number(server.binding_count || server.bindingCount || 0),
          activeCount: Number(server.active_count || server.activeCount || 0),
          eventCount: Number(server.event_count || server.eventCount || 0),
          lastTestedAt: server.last_tested_at || server.lastTestedAt || null,
          evaluatedAt: server.evaluated_at || server.evaluatedAt || null,
          breakdown: Array.isArray(server.breakdown)
            ? normalizeMCPSecurityScore({ breakdown: server.breakdown }).breakdown
            : []
        }))
      : [],
    scoreDistribution: raw.score_distribution || raw.scoreDistribution || {},
    recentEvents: Array.isArray(raw.recent_events || raw.recentEvents)
      ? (raw.recent_events || raw.recentEvents).map(normalizeMCPEvent).filter(Boolean)
      : [],
    failureModeCounts: raw.failure_mode_counts || raw.failureModeCounts || {},
    actionTypeCounts: raw.action_type_counts || raw.actionTypeCounts || {},
    recommendedActions: Array.isArray(raw.recommended_actions || raw.recommendedActions)
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : []
  }
}

export const normalizeMCPGovernanceSummary = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  const rawFilters = raw.event_filters || raw.eventFilters || {}
  return {
    totalServers: Number(raw.total_servers || raw.totalServers || 0),
    recoveringServers: Number(raw.recovering_servers || raw.recoveringServers || 0),
    blockedServers: Number(raw.blocked_servers || raw.blockedServers || 0),
    staleServers: Number(raw.stale_servers || raw.staleServers || 0),
    untestedServers: Number(raw.untested_servers || raw.untestedServers || 0),
    impactedAgents: Number(raw.impacted_agents || raw.impactedAgents || 0),
    activeImpactedAgents: Number(raw.active_impacted_agents || raw.activeImpactedAgents || 0),
    recentEventCount: Number(raw.recent_event_count || raw.recentEventCount || 0),
    longStaleServers: Array.isArray(raw.long_stale_servers || raw.longStaleServers)
      ? [...(raw.long_stale_servers || raw.longStaleServers)]
      : [],
    recoverableServers: Array.isArray(raw.recoverable_servers || raw.recoverableServers)
      ? [...(raw.recoverable_servers || raw.recoverableServers)]
      : [],
    recentEvents: Array.isArray(raw.recent_events || raw.recentEvents)
      ? (raw.recent_events || raw.recentEvents).map(normalizeMCPEvent).filter(Boolean)
      : [],
    failureModeCounts: raw.failure_mode_counts || raw.failureModeCounts || {},
    actionTypeCounts: raw.action_type_counts || raw.actionTypeCounts || {},
    eventStatusCounts: raw.event_status_counts || raw.eventStatusCounts || {},
    eventFilters: {
      serverId: rawFilters.server_id || rawFilters.serverId || '',
      actionType: rawFilters.action_type || rawFilters.actionType || '',
      status: rawFilters.status || '',
      failureMode: rawFilters.failure_mode || rawFilters.failureMode || '',
      limit: Number(rawFilters.limit || 0)
    }
  }
}

export const normalizeMCPBulkPreview = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    action: raw.action || '',
    previewOnly: Boolean(raw.preview_only || raw.previewOnly),
    previewToken: raw.preview_token || raw.previewToken || '',
    orderedBy: raw.ordered_by || raw.orderedBy || '',
    riskSummary: raw.risk_summary || raw.riskSummary || '',
    requiresConfirmation: Boolean(raw.requires_confirmation || raw.requiresConfirmation),
    confirmationMessage: raw.confirmation_message || raw.confirmationMessage || '',
    generatedAt: raw.generated_at || raw.generatedAt || null,
    expiresAt: raw.expires_at || raw.expiresAt || null,
    selectedServerIds: Array.isArray(raw.selected_server_ids || raw.selectedServerIds)
      ? [...(raw.selected_server_ids || raw.selectedServerIds)]
      : [],
    recommendations: Array.isArray(raw.recommendations)
      ? raw.recommendations.map((item, index) => ({
          order: Number(item.order || index + 1),
          serverId: item.server_id || item.serverId || '',
          serverName: item.server_name || item.serverName || '',
          action: item.action || '',
          priority: item.priority || 'medium',
          reason: item.reason || '',
          failureMode: item.failure_mode || item.failureMode || '',
          recoveryStatus: item.recovery_status || item.recoveryStatus || '',
          impactedAgents: Number(item.impacted_agents || item.impactedAgents || 0),
          activeImpactedAgents: Number(item.active_impacted_agents || item.activeImpactedAgents || 0),
          suggestedFollowUps: Array.isArray(item.suggested_follow_ups || item.suggestedFollowUps)
            ? (item.suggested_follow_ups || item.suggestedFollowUps).map((action) => ({
                type: action.type || '',
                label: action.label || '',
                description: action.description || '',
                priority: action.priority || ''
              }))
            : []
        }))
      : []
  }
}

export const normalizeMCPBulkFollowUpPlan = (raw = null) => {
  if (!raw || typeof raw !== 'object') return null
  return {
    status: raw.status || 'settled',
    summary: raw.summary || '',
    requiresManualReview: Boolean(raw.requires_manual_review || raw.requiresManualReview),
    manualReviewReason: raw.manual_review_reason || raw.manualReviewReason || '',
    recommendedActions: Array.isArray(raw.recommended_actions || raw.recommendedActions)
      ? [...(raw.recommended_actions || raw.recommendedActions)].filter(Boolean)
      : [],
    compensationActions: Array.isArray(raw.compensation_actions || raw.compensationActions)
      ? [...(raw.compensation_actions || raw.compensationActions)].filter(Boolean)
      : [],
    rollbackActions: Array.isArray(raw.rollback_actions || raw.rollbackActions)
      ? [...(raw.rollback_actions || raw.rollbackActions)].filter(Boolean)
      : [],
    failedServerIds: Array.isArray(raw.failed_server_ids || raw.failedServerIds)
      ? [...(raw.failed_server_ids || raw.failedServerIds)].filter(Boolean)
      : [],
    driftedServerIds: Array.isArray(raw.drifted_server_ids || raw.driftedServerIds)
      ? [...(raw.drifted_server_ids || raw.driftedServerIds)].filter(Boolean)
      : [],
    recoveryStageCounts: Array.isArray(raw.recovery_stage_counts || raw.recoveryStageCounts)
      ? (raw.recovery_stage_counts || raw.recoveryStageCounts).map((item) => ({
          key: item.key || '',
          label: item.label || '',
          count: Number(item.count || 0),
          priority: item.priority || '',
          summary: item.summary || ''
        }))
      : []
  }
}

export const bindingUsageLabel = (bindingUsage) => {
  const count = Number(bindingUsage?.agentCount || 0)
  if (count <= 0) return '未绑定'
  return `${count} 个 agent`
}

export const recoverySeverityTone = (recovery) => {
  const severity = String(recovery?.severity || '').trim() || 'info'
  return `recovery-${severity}`
}

export const buildRecoveryActions = (server) => {
  const actions = Array.isArray(server?.recovery?.actions) ? server.recovery.actions.filter((action) => action?.type) : []
  if (actions.length > 0) return actions
  const fallback = buildWarningAction(server)
  return fallback ? [fallback] : []
}

export const buildMCPManageRoute = (serverId = '', { agentId = '', agentName = '', intent = '' } = {}) => {
  const query = {}
  if (serverId) query.server = serverId
  if (agentId) query.agent = agentId
  if (agentName) query.agent_name = agentName
  if (intent) query.intent = intent
  return { name: 'MCPManage', query }
}

export const buildAgentExtensionsRoute = (agentId = '', { serverId = '', focus = '', from = '' } = {}) => {
  const query = {}
  if (serverId) query.server = serverId
  if (focus) query.focus = focus
  if (from) query.from = from
  return {
    name: 'AgentExtensions',
    params: { id: agentId },
    query
  }
}

const buildWarningAction = (server) => {
  if (!server?.id) return null
  const recoveryActions = Array.isArray(server?.recovery?.actions) ? server.recovery.actions.filter((action) => action?.type) : []
  if (recoveryActions.length > 0) {
    const first = recoveryActions[0]
    return { type: first.type, label: first.label || '处理问题' }
  }
  if (server.status !== 'active') {
    return { type: 'manage', label: '前往管理' }
  }
  if (!server.availability?.bindable) {
    if (server.availability?.reason === 'catalog_empty') {
      return { type: 'refresh', label: '刷新 Catalog' }
    }
    if (server.availability?.reason === 'connection_failed') {
      return { type: 'test', label: '测试连接' }
    }
    return { type: 'manage', label: '前往管理' }
  }
  if (server.catalog?.isStale) {
    return { type: 'refresh', label: '刷新 Catalog' }
  }
  if (server.connection?.status === 'untested') {
    return { type: 'test', label: '测试连接' }
  }
  return null
}

export const buildMCPBindingWarnings = (servers = [], selectedIds = []) => {
  const selectedIdSet = new Set(Array.isArray(selectedIds) ? selectedIds.filter(Boolean) : [])
  return (Array.isArray(servers) ? servers : [])
    .filter((server) => selectedIdSet.has(server?.id))
    .flatMap((server) => {
      if (!server?.id) return []
      if (server.recovery?.recoverable && server.recovery?.status !== 'healthy') {
        return [{
          id: `${server.id}-${server.recovery.status || 'recovery'}`,
          serverId: server.id,
          message: `${server.name}：${server.recovery.summary || server.availability?.summary || '需要恢复操作。'}`,
          action: buildWarningAction(server),
          severity: server.recovery.severity || 'info',
          impactSummary: server.recovery.impact?.summary || ''
        }]
      }
      if (server.status !== 'active') {
        return [{
          id: `${server.id}-disabled`,
          serverId: server.id,
          message: `${server.name} 已禁用，保存时不会允许继续绑定。`,
          action: buildWarningAction(server)
        }]
      }
      if (!server.availability?.bindable) {
        return [{
          id: `${server.id}-unavailable`,
          serverId: server.id,
          message: `${server.name} 当前不可绑定：${server.availability?.summary || '请先刷新 catalog 或修复连接。'}`,
          action: buildWarningAction(server)
        }]
      }
      if (server.catalog?.isStale) {
        return [{
          id: `${server.id}-stale`,
          serverId: server.id,
          message: `${server.name} 的 catalog 已过期，建议先刷新后再投入生产。`,
          action: buildWarningAction(server)
        }]
      }
      if (server.connection?.status === 'untested') {
        return [{
          id: `${server.id}-untested`,
          serverId: server.id,
          message: `${server.name} 还没有完成连接验证，建议先测试连接。`,
          action: buildWarningAction(server)
        }]
      }
      return []
    })
}

export const governanceFocusLabel = (server) => {
  if (server?.recovery?.status === 'blocked') return '阻塞恢复'
  if (server?.catalog?.isStale) return 'Catalog 过期'
  if (server?.connection?.status === 'untested') return '待验证'
  if (server?.recovery?.recoverable) return '待治理'
  return '健康'
}
