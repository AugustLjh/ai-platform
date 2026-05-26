import test from 'node:test'
import assert from 'node:assert/strict'

import { buildBrowserSessionTrendPoints, formatBrowserSessionHistoryLabel } from '../src/utils/browserSessions.js'

test('buildBrowserSessionTrendPoints preserves history samples as risk points', () => {
  const points = buildBrowserSessionTrendPoints([
    {
      sampledAt: '2026-05-18T12:00:00+08:00',
      sessionCount: 3,
      activeSessionCount: 2,
      expiredSessionCount: 1,
      networkErrorCount: 2,
      consoleMessageCount: 6,
      health: { status: 'warning', score: 73 }
    }
  ])

  assert.equal(points.length, 1)
  assert.equal(points[0].risk, 38)
  assert.equal(points[0].score, 73)
})

test('formatBrowserSessionHistoryLabel renders a readable summary', () => {
  const label = formatBrowserSessionHistoryLabel(
    {
      sampledAt: '2026-05-18T12:00:00+08:00',
      activeSessionCount: 2,
      sessionCount: 3,
      expiredSessionCount: 1,
      networkErrorCount: 2,
      consoleMessageCount: 6,
      health: { status: 'warning', score: 73 }
    },
    (value) => value
  )

  assert.match(label, /活跃 2\/3/)
  assert.match(label, /健康 warning 73\/100/)
})
