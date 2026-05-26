import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeTenantGovernance } from '../src/utils/tenantGovernance.js'

test('normalizeTenantGovernance preserves quota metrics and recovery actions', () => {
  const governance = normalizeTenantGovernance({
    tenant_id: 'tenant-1',
    generated_at: '2026-05-18T12:00:00Z',
    window_hours: 24,
    enforcement_enabled: true,
    status: 'blocked',
    summary: 'tenant quota exceeded for active_runs',
    usage: {
      runs: { active_runs: 12, runs_in_window: 30 },
      tools: { tool_calls_in_window: 95, network_tool_calls_in_window: 25 },
      subagents: { invocations_in_window: 4 },
      workspaces: { workspace_count: 3, total_size_bytes: 2048 }
    },
    metrics: [
      {
        key: 'active_runs',
        label: 'Active runs',
        used: 12,
        limit: 10,
        remaining: 0,
        unit: 'runs',
        utilization_percent: 120,
        status: 'exceeded',
        enforced: true
      },
      {
        key: 'workspace_bytes',
        label: 'Workspace bytes',
        used: 2048,
        limit: 0,
        unit: 'bytes',
        status: 'unlimited'
      }
    ],
    blocking_metrics: [{ key: 'active_runs' }],
    recovery_actions: [{ key: 'review_active_runs', label: 'Review active runs' }]
  })

  assert.equal(governance.tenantId, 'tenant-1')
  assert.equal(governance.windowHours, 24)
  assert.equal(governance.enforcementEnabled, true)
  assert.equal(governance.usage.runs.active_runs, 12)
  assert.equal(governance.metrics[0].utilizationPercent, 120)
  assert.equal(governance.metrics[0].enforced, true)
  assert.equal(governance.metrics[1].status, 'unlimited')
  assert.equal(governance.blockingMetrics[0].key, 'active_runs')
  assert.equal(governance.recoveryActions[0].key, 'review_active_runs')
})
