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

export const bindingUsageLabel = (bindingUsage) => {
  const count = Number(bindingUsage?.agentCount || 0)
  if (count <= 0) return '未绑定'
  return `${count} 个 agent`
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
