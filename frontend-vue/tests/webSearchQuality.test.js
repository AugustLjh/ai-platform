import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatWebSearchPolicySnapshot,
  normalizeWebSearchQualityEvaluation,
  summarizeWebSearchQualityEvaluation,
  webSearchQualityTone
} from '../src/utils/webSearchQuality.js'

test('normalizeWebSearchQualityEvaluation preserves summary and case metrics', () => {
  const evaluation = normalizeWebSearchQualityEvaluation({
    protocol_version: 'managed-web.search-quality-suite.v1',
    status: 'passed',
    total: 2,
    passed: 2,
    warning: 0,
    failed: 0,
    average_score: 1,
    summary: '2 passed / 0 warning / 0 failed',
    accepted_count: 2,
    rejected_count: 1,
    check_count: 3,
    passed_check_count: 3,
    failed_check_count: 0,
    rejection_reason_counts: { 'duplicate search result': 1 },
    case_summaries: [
      {
        name: 'boundary',
        status: 'passed',
        score: 1,
        summary: 'case summary',
        accepted_count: 1,
        rejected_count: 0,
        failed_check_count: 0
      }
    ],
    results: [
      {
        name: 'boundary',
        status: 'passed',
        score: 1,
        summary: 'case summary',
        policy_snapshot: { allowed_domains: ['docs.example.com'] },
        accepted_count: 1,
        rejected_count: 0,
        checks: [{ name: 'accepted_count', passed: true, weight: 1 }]
      }
    ]
  })

  assert.equal(evaluation.protocolVersion, 'managed-web.search-quality-suite.v1')
  assert.equal(evaluation.summary, '2 passed / 0 warning / 0 failed')
  assert.equal(evaluation.results[0].policySnapshot.allowed_domains[0], 'docs.example.com')
  assert.equal(evaluation.results[0].checkCount, 1)
  assert.equal(evaluation.acceptedCount, 2)
  assert.equal(evaluation.caseSummaries[0].summary, 'case summary')
})

test('summarizeWebSearchQualityEvaluation and webSearchQualityTone expose readable governance status', () => {
  const summary = summarizeWebSearchQualityEvaluation({
    status: 'warning',
    passed: 1,
    warning: 1,
    failed: 0,
    averageScore: 0.75,
    acceptedCount: 2,
    rejectedCount: 1,
    passedCheckCount: 3,
    failedCheckCount: 0
  })

  assert.equal(summary, 'warning · 1 passed / 1 warning / 0 failed · avg 0.75 · accepted 2 · rejected 1 · checks 3')
  assert.equal(webSearchQualityTone('passed'), 'ready')
  assert.equal(webSearchQualityTone('failed'), 'danger')
})

test('formatWebSearchPolicySnapshot renders allowlist and rejection controls', () => {
  const summary = formatWebSearchPolicySnapshot({
    allowedDomains: ['docs.example.com'],
    deniedDomains: ['evil.example.net'],
    searchAllowedSchemes: ['https'],
    searchRequireUrl: true,
    searchRequireTitle: true,
    searchRequireSnippet: false,
    searchRejectDisallowedDomains: true,
    searchRejectDuplicates: true
  })

  assert.ok(summary.includes('允许域名 docs.example.com'))
  assert.ok(summary.includes('拒绝域名 evil.example.net'))
  assert.ok(summary.includes('scheme https'))
  assert.ok(summary.includes('拒绝重复结果'))
})
