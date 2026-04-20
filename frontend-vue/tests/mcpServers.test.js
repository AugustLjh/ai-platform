import test from 'node:test'
import assert from 'node:assert/strict'

import {
  bindingUsageLabel,
  buildAgentExtensionsRoute,
  buildMCPBindingWarnings,
  buildMCPManageRoute,
  normalizeMCPBulkFollowUpPlan,
  normalizeMCPBulkPreview,
  normalizeMCPBindingUsage,
  normalizeMCPEvent,
  normalizeMCPGovernanceSummary,
  normalizeMCPRecovery
} from '../src/utils/mcpServers.js'

test('normalizeMCPBindingUsage keeps agent samples and counts', () => {
  const usage = normalizeMCPBindingUsage({
    agent_count: 3,
    active_agent_count: 2,
    inactive_agent_count: 1,
    summary: '当前有 3 个 agent 正在使用这个 server。',
    more_count: 1,
    agents: [
      { agent_id: 'agent-1', name: 'Docs Agent', status: 'active' },
      { agent_id: 'agent-2', name: 'Review Agent', status: 'disabled' }
    ]
  })

  assert.equal(usage.agentCount, 3)
  assert.equal(usage.activeAgentCount, 2)
  assert.equal(usage.inactiveAgentCount, 1)
  assert.equal(usage.moreCount, 1)
  assert.equal(usage.agents[0].agentId, 'agent-1')
  assert.equal(usage.agents[1].status, 'disabled')
})

test('normalizeMCPRecovery keeps actions and impact summary', () => {
  const recovery = normalizeMCPRecovery({
    status: 'blocked',
    severity: 'critical',
    summary: '最近一次连接测试失败。',
    failure_mode: 'connection_failed',
    recoverable: true,
    actions: [
      { type: 'test', label: '重新测试连接', priority: 'high' },
      { type: 'refresh', label: '连接恢复后刷新 Catalog', priority: 'medium' }
    ],
    impact: {
      agent_count: 4,
      active_agent_count: 3,
      inactive_agent_count: 1,
      summary: '当前影响 4 个已绑定 agent，其中 3 个处于 active 状态。'
    }
  })

  assert.equal(recovery.status, 'blocked')
  assert.equal(recovery.actions[0].type, 'test')
  assert.equal(recovery.impact.activeAgentCount, 3)
  assert.equal(recovery.impact.summary, '当前影响 4 个已绑定 agent，其中 3 个处于 active 状态。')
})

test('normalizeMCPEvent normalizes audit event payloads', () => {
  const event = normalizeMCPEvent({
    id: 'evt-1',
    tenant_id: 'tenant-1',
    server_id: 'server-1',
    server_name: 'Docs MCP',
    event_type: 'catalog.refreshed',
    action_type: 'refresh',
    status: 'succeeded',
    failure_mode: 'catalog_ready',
    summary: 'MCP catalog 已刷新。',
    details: { catalog: { tool_count: 3 } },
    actor_user_id: 'user-1',
    created_at: '2026-04-15T12:00:00Z'
  })

  assert.equal(event.serverId, 'server-1')
  assert.equal(event.actionType, 'refresh')
  assert.equal(event.failureMode, 'catalog_ready')
  assert.equal(event.details.catalog.tool_count, 3)
})

test('normalizeMCPGovernanceSummary keeps counts and recent events', () => {
  const summary = normalizeMCPGovernanceSummary({
    total_servers: 5,
    recovering_servers: 3,
    blocked_servers: 1,
    stale_servers: 2,
    untested_servers: 1,
    impacted_agents: 7,
    active_impacted_agents: 5,
    recent_event_count: 6,
    recent_events: [
      {
        id: 'evt-1',
        server_id: 'server-1',
        server_name: 'Docs MCP',
        action_type: 'test',
        status: 'failed',
        summary: '连接测试失败。'
      }
    ],
    failure_mode_counts: {
      connection_failed: 2
    },
    action_type_counts: {
      refresh: 4
    },
    event_status_counts: {
      failed: 3
    },
    event_filters: {
      server_id: 'server-1',
      action_type: 'refresh',
      status: 'failed',
      failure_mode: 'connection_failed',
      limit: 20
    }
  })

  assert.equal(summary.totalServers, 5)
  assert.equal(summary.recoveringServers, 3)
  assert.equal(summary.recentEventCount, 6)
  assert.equal(summary.recentEvents[0].serverName, 'Docs MCP')
  assert.equal(summary.failureModeCounts.connection_failed, 2)
  assert.equal(summary.actionTypeCounts.refresh, 4)
  assert.equal(summary.eventStatusCounts.failed, 3)
  assert.equal(summary.eventFilters.serverId, 'server-1')
  assert.equal(summary.eventFilters.actionType, 'refresh')
})

test('normalizeMCPBulkPreview keeps confirmation and recommendations', () => {
  const preview = normalizeMCPBulkPreview({
    action: 'refresh',
    preview_only: true,
    ordered_by: 'impact_and_recovery',
    risk_summary: '本次批量刷新将覆盖 5 个已绑定 agent，其中 3 个处于 active 状态。',
    requires_confirmation: true,
    confirmation_message: '建议先核对排序靠前的阻塞项与高影响 server，再执行批量恢复。',
    recommendations: [
      {
        order: 1,
        server_id: 'server-1',
        server_name: 'Docs MCP',
        action: 'refresh',
        priority: 'high',
        reason: '最近一次连接测试失败，且影响 3 个 active agent。',
        failure_mode: 'connection_failed',
        recovery_status: 'blocked',
        impacted_agents: 4,
        active_impacted_agents: 3,
        suggested_follow_ups: [
          { type: 'test', label: '重新测试连接', priority: 'high' }
        ]
      }
    ]
  })

  assert.equal(preview.previewOnly, true)
  assert.equal(preview.previewToken, '')
  assert.equal(preview.requiresConfirmation, true)
  assert.equal(preview.recommendations[0].serverName, 'Docs MCP')
  assert.equal(preview.recommendations[0].activeImpactedAgents, 3)
  assert.equal(preview.recommendations[0].suggestedFollowUps[0].type, 'test')
})

test('normalizeMCPBulkPreview keeps token and selected server ids', () => {
  const preview = normalizeMCPBulkPreview({
    action: 'test',
    preview_token: 'preview-token',
    generated_at: '2026-04-15T11:00:00Z',
    expires_at: '2026-04-15T11:15:00Z',
    selected_server_ids: ['server-1', 'server-2']
  })

  assert.equal(preview.previewToken, 'preview-token')
  assert.equal(preview.generatedAt, '2026-04-15T11:00:00Z')
  assert.equal(preview.expiresAt, '2026-04-15T11:15:00Z')
  assert.deepEqual(preview.selectedServerIds, ['server-1', 'server-2'])
})

test('normalizeMCPBulkPreview allows redacted persisted preview token state', () => {
  const preview = normalizeMCPBulkPreview({
    action: 'refresh',
    preview_token: '',
    risk_summary: 'persisted preview summary'
  })

  assert.equal(preview.previewToken, '')
  assert.equal(preview.riskSummary, 'persisted preview summary')
})

test('normalizeMCPBulkFollowUpPlan keeps stage summaries and failed server ids', () => {
  const followUp = normalizeMCPBulkFollowUpPlan({
    status: 'needs_follow_up',
    summary: '仍有 2 个 server 需要继续收敛。',
    requires_manual_review: true,
    manual_review_reason: '失败结果仍影响 active agent，建议人工确认治理顺序。',
    recommended_actions: ['先重新测试连接'],
    compensation_actions: ['把失败 server 拆出独立补救批次'],
    rollback_actions: ['必要时回退到 disabled'],
    failed_server_ids: ['server-1'],
    recovery_stage_counts: [
      {
        key: 'blocked',
        label: '阻塞项处理',
        count: 1,
        priority: 'high',
        summary: '仍有 1 个 server 处于阻塞态。'
      }
    ]
  })

  assert.equal(followUp.status, 'needs_follow_up')
  assert.equal(followUp.requiresManualReview, true)
  assert.equal(followUp.manualReviewReason, '失败结果仍影响 active agent，建议人工确认治理顺序。')
  assert.equal(followUp.compensationActions[0], '把失败 server 拆出独立补救批次')
  assert.equal(followUp.rollbackActions[0], '必要时回退到 disabled')
  assert.equal(followUp.failedServerIds[0], 'server-1')
  assert.equal(followUp.recoveryStageCounts[0].label, '阻塞项处理')
})

test('bindingUsageLabel renders readable agent counts', () => {
  assert.equal(bindingUsageLabel(null), '未绑定')
  assert.equal(bindingUsageLabel({ agentCount: 2 }), '2 个 agent')
})

test('buildMCPBindingWarnings returns remediation actions for stale and unavailable servers', () => {
  const warnings = buildMCPBindingWarnings([
    {
      id: 'server-1',
      name: 'Docs MCP',
      status: 'active',
      recovery: {
        status: 'needs_catalog',
        severity: 'high',
        summary: '当前没有可供 agent 使用的缓存工具，需先建立或重建 catalog。',
        recoverable: true,
        actions: [{ type: 'refresh', label: '刷新 Catalog' }],
        impact: { summary: '当前影响 2 个已绑定 agent。' }
      },
      availability: { bindable: false, summary: '请先刷新 catalog。', reason: 'catalog_empty' },
      catalog: { isStale: false },
      connection: { status: 'healthy' }
    },
    {
      id: 'server-2',
      name: 'Review MCP',
      status: 'active',
      recovery: {
        status: 'stale',
        severity: 'medium',
        summary: '当前仍能绑定，但缓存 catalog 已过期。',
        recoverable: true,
        actions: [{ type: 'refresh', label: '刷新 Catalog' }]
      },
      availability: { bindable: true, summary: '可用', reason: '' },
      catalog: { isStale: true },
      connection: { status: 'healthy' }
    }
  ], ['server-1', 'server-2'])

  assert.equal(warnings.length, 2)
  assert.equal(warnings[0].action.type, 'refresh')
  assert.equal(warnings[0].impactSummary, '当前影响 2 个已绑定 agent。')
  assert.equal(warnings[1].action.type, 'refresh')
})

test('buildMCPManageRoute and buildAgentExtensionsRoute preserve navigation context', () => {
  assert.deepEqual(buildMCPManageRoute('server-1', {
    agentId: 'agent-1',
    agentName: 'Docs Agent',
    intent: 'refresh'
  }), {
    name: 'MCPManage',
    query: {
      server: 'server-1',
      agent: 'agent-1',
      agent_name: 'Docs Agent',
      intent: 'refresh'
    }
  })

  assert.deepEqual(buildAgentExtensionsRoute('agent-1', {
    serverId: 'server-1',
    focus: 'mcp',
    from: 'mcp'
  }), {
    name: 'AgentExtensions',
    params: { id: 'agent-1' },
    query: {
      server: 'server-1',
      focus: 'mcp',
      from: 'mcp'
    }
  })
})
