import test from 'node:test'
import assert from 'node:assert/strict'

import { summarizeEvaluationHistory } from '../src/utils/evaluationHistory.js'

test('summarizeEvaluationHistory prefers server-side comparison summary metadata', () => {
  const summary = summarizeEvaluationHistory(
    [
      { status: 'passed', summary: { average_score: 1.0 }, createdAt: '2026-05-20T10:00:00Z' },
      { status: 'warning', summary: { average_score: 0.5 }, createdAt: '2026-05-19T10:00:00Z' }
    ],
    {
      historyComparison: {
        current: { current_passed: 3, current_total: 3 },
        delta: { score: 0.5 },
        summary: 'score improved by +0.50 · 2 more passed cases',
        trend: {
          summary: 'recent 2-run trend improving · avg score 0.75 · best 1.00 · vs oldest +0.50'
        }
      }
    },
    (value) => value || ''
  )

  assert.equal(summary, 'passed · avg 1.00 · 3/3 · score improved by +0.50 · 2 more passed cases · recent 2-run trend improving · avg score 0.75 · best 1.00 · vs oldest +0.50 · 2026-05-20T10:00:00Z')
})

test('summarizeEvaluationHistory falls back to local score delta without comparison metadata', () => {
  const summary = summarizeEvaluationHistory(
    [
      { status: 'warning', summary: { average_score: 0.75 }, createdAt: '2026-05-20T10:00:00Z' },
      { status: 'passed', summary: { average_score: 1.0 }, createdAt: '2026-05-19T10:00:00Z' }
    ],
    null,
    (value) => value || ''
  )

  assert.equal(summary, 'warning · avg 0.75 · 较上次 -0.25 · 2026-05-20T10:00:00Z')
})

test('summarizeEvaluationHistory falls back to history summary trend when comparison metadata is partial', () => {
  const history = [
    { status: 'passed', summary: { average_score: 0.9 }, createdAt: '2026-05-20T10:00:00Z' },
    { status: 'warning', summary: { average_score: 0.7 }, createdAt: '2026-05-19T10:00:00Z' }
  ]
  const summary = summarizeEvaluationHistory(history, {
    historySummary: {
      trend: {
        summary: 'recent 2-run trend improving · avg score 0.80 · best 0.90'
      }
    }
  }, (value) => value || '')

  assert.equal(summary, 'passed · avg 0.90 · 较上次 +0.20 · recent 2-run trend improving · avg score 0.80 · best 0.90 · 2026-05-20T10:00:00Z')
})

test('summarizeEvaluationHistory includes production readiness evidence fields', () => {
  const summary = summarizeEvaluationHistory(
    [
      { status: 'failed', summary: { average_score: 0.6 }, createdAt: '2026-05-21T10:00:00Z' },
      { status: 'failed', summary: { average_score: 0.4 }, createdAt: '2026-05-20T10:00:00Z' }
    ],
    {
      historyComparison: {
        current: {
          current_passed: 12,
          current_total: 20,
          readiness: 'blocked',
          blocking_check_count: 3,
          evidence_quality_score: 0.75
        },
        delta: { score: 0.2 },
        summary: 'score improved by +0.20 · 2 fewer readiness blockers · evidence quality +0.25'
      }
    },
    (value) => value || ''
  )

  assert.equal(summary, 'failed · avg 0.60 · 12/20 · blocked · blockers 3 · evidence 0.75 · score improved by +0.20 · 2 fewer readiness blockers · evidence quality +0.25 · 2026-05-21T10:00:00Z')
})
