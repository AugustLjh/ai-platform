import test from 'node:test'
import assert from 'node:assert/strict'

import {
  bindingUsageLabel,
  buildAgentExtensionsRoute,
  buildMCPBindingWarnings,
  buildMCPManageRoute,
  normalizeMCPBindingUsage
} from '../src/utils/mcpServers.js'

test('normalizeMCPBindingUsage keeps agent samples and counts', () => {
  const usage = normalizeMCPBindingUsage({
    agent_count: 3,
    summary: '当前有 3 个 agent 正在使用这个 server。',
    more_count: 1,
    agents: [
      { agent_id: 'agent-1', name: 'Docs Agent', status: 'active' },
      { agent_id: 'agent-2', name: 'Review Agent', status: 'disabled' }
    ]
  })

  assert.equal(usage.agentCount, 3)
  assert.equal(usage.moreCount, 1)
  assert.equal(usage.agents[0].agentId, 'agent-1')
  assert.equal(usage.agents[1].status, 'disabled')
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
      availability: { bindable: false, summary: '请先刷新 catalog。', reason: 'catalog_empty' },
      catalog: { isStale: false },
      connection: { status: 'healthy' }
    },
    {
      id: 'server-2',
      name: 'Review MCP',
      status: 'active',
      availability: { bindable: true, summary: '可用', reason: '' },
      catalog: { isStale: true },
      connection: { status: 'healthy' }
    }
  ], ['server-1', 'server-2'])

  assert.equal(warnings.length, 2)
  assert.equal(warnings[0].action.type, 'refresh')
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
