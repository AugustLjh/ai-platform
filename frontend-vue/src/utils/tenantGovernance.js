export const normalizeTenantGovernance = (raw = {}) => ({
  tenantId: raw.tenant_id || raw.tenantId || '',
  generatedAt: raw.generated_at || raw.generatedAt || null,
  windowHours: Number(raw.window_hours || raw.windowHours || 0),
  enforcementEnabled: Boolean(raw.enforcement_enabled || raw.enforcementEnabled),
  status: raw.status || 'healthy',
  summary: raw.summary || '',
  config: raw.config && typeof raw.config === 'object' ? { ...raw.config } : {},
  usage: {
    runs: raw.usage?.runs && typeof raw.usage.runs === 'object' ? { ...raw.usage.runs } : {},
    tools: raw.usage?.tools && typeof raw.usage.tools === 'object' ? { ...raw.usage.tools } : {},
    subagents: raw.usage?.subagents && typeof raw.usage.subagents === 'object' ? { ...raw.usage.subagents } : {},
    workspaces: raw.usage?.workspaces && typeof raw.usage.workspaces === 'object' ? { ...raw.usage.workspaces } : {}
  },
  metrics: Array.isArray(raw.metrics) ? raw.metrics.map((metric) => ({
    key: metric.key || '',
    label: metric.label || '',
    used: Number(metric.used || 0),
    limit: Number(metric.limit || 0),
    remaining: metric.remaining == null ? null : Number(metric.remaining),
    unit: metric.unit || '',
    utilizationPercent: Number(metric.utilization_percent || metric.utilizationPercent || 0),
    status: metric.status || 'healthy',
    enforced: Boolean(metric.enforced)
  })) : [],
  blockingMetrics: Array.isArray(raw.blocking_metrics || raw.blockingMetrics)
    ? [...(raw.blocking_metrics || raw.blockingMetrics)]
    : [],
  warningMetrics: Array.isArray(raw.warning_metrics || raw.warningMetrics)
    ? [...(raw.warning_metrics || raw.warningMetrics)]
    : [],
  recoveryActions: Array.isArray(raw.recovery_actions || raw.recoveryActions)
    ? [...(raw.recovery_actions || raw.recoveryActions)]
    : []
})
