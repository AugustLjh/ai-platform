import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeRuntimeStatus } from '../src/utils/runtimeStatus.js'

test('normalizeRuntimeStatus preserves workspace lifecycle history and trend', () => {
  const status = normalizeRuntimeStatus({
    workspace_lifecycle: {
      enabled: true,
      history: [
        {
          generated_at: '2026-05-16T00:00:00+00:00',
          inspection: { workspace_count: 2 },
          cleanup: null,
          alerts: []
        }
      ],
      trend: {
        status: 'stable',
        window_size: 1,
        first_generated_at: '2026-05-16T00:00:00+00:00',
        last_generated_at: '2026-05-16T00:00:00+00:00',
        summary: 'workspace lifecycle trend baseline captured',
        delta: {
          health_score: 0,
          expired_count: 0,
          stale_lock_count: 0
        }
      }
    }
  })

  assert.equal(status.workspaceLifecycle.history.length, 1)
  assert.equal(status.workspaceLifecycle.history[0].generatedAt, '2026-05-16T00:00:00+00:00')
  assert.equal(status.workspaceLifecycle.trend.status, 'stable')
  assert.equal(status.workspaceLifecycle.trend.windowSize, 1)
  assert.equal(status.workspaceLifecycle.trend.delta.expired_count, 0)
})

test('normalizeRuntimeStatus preserves browser session health alerts history and trend', () => {
  const status = normalizeRuntimeStatus({
    providers: {
      web: {
        browser_sessions: {
          session_count: 2,
          active_session_count: 1,
          expired_session_count: 1,
          oldest_session_age_seconds: 120,
          session_ttl_seconds: 60,
          network_error_count: 1,
          console_message_count: 3,
          sessions: [{ session_id: 'browser-session-1', network_error_count: 1 }],
          expired_session_ids: ['browser-session-1'],
          health: {
            status: 'warning',
            score: 73,
            summary: 'browser sessions need attention',
            issues: [{ code: 'expired_browser_sessions', count: 1 }],
            recovery_actions: [{ key: 'close_stale_browser_sessions' }]
          },
          alerts: [{ type: 'expired_browser_sessions', count: 1, threshold: 0 }],
          history: [
            {
              sampled_at: '2026-05-16T00:00:00+00:00',
              session_count: 1,
              active_session_count: 1,
              expired_session_count: 0,
              network_error_count: 0,
              console_message_count: 0,
              health: { status: 'healthy', score: 100 }
            }
          ],
          trend: {
            status: 'worsening',
            window_size: 2,
            first_sampled_at: '2026-05-16T00:00:00+00:00',
            last_sampled_at: '2026-05-16T00:01:00+00:00',
            summary: 'browser session risk is increasing',
            delta: {
              expired_session_count: 1,
              network_error_count: 1,
              health_score: -27
            }
          }
        }
      }
    }
  })

  assert.equal(status.web.browserSessions.expiredSessionCount, 1)
  assert.equal(status.web.browserSessions.networkErrorCount, 1)
  assert.equal(status.web.browserSessions.health.status, 'warning')
  assert.equal(status.web.browserSessions.health.recoveryActions[0].key, 'close_stale_browser_sessions')
  assert.equal(status.web.browserSessions.alerts[0].type, 'expired_browser_sessions')
  assert.equal(status.web.browserSessions.history[0].sampledAt, '2026-05-16T00:00:00+00:00')
  assert.equal(status.web.browserSessions.trendPoints.length, 1)
  assert.equal(status.web.browserSessions.trendPoints[0].risk, 0)
  assert.equal(status.web.browserSessions.trend.status, 'worsening')
  assert.equal(status.web.browserSessions.trend.delta.health_score, -27)
})

test('normalizeRuntimeStatus preserves observability provider summary', () => {
  const status = normalizeRuntimeStatus({
    providers: {
      observability: {
        enabled: true,
        configured: true,
        enabled_tools: ['db_query_readonly', 'service_logs'],
        available_tools: ['service_logs'],
        db_configured: false,
        redis_configured: true,
        redis_host: '127.0.0.1',
        redis_port: 6379,
        allowed_http_domains: ['internal.example.com'],
        allow_loopback_http: true,
        default_health_url: 'http://127.0.0.1:8000/health',
        metrics_url_configured: true,
        allowed_metric_names: ['runtime_*'],
        max_metric_lines: 2500,
        max_metric_samples: 200,
        log_roots: ['/tmp/logs'],
        max_rows: 100,
        max_output_chars: 40000,
        timeout_seconds: 10,
        audit_report: {
          status: 'warning',
          enabled: true,
          available_tools: ['db_query_readonly', 'metrics_query'],
          checks: [
            { key: 'metrics_allowlist', status: 'warning', severity: 'medium', summary: 'Metrics allowlist is empty.' }
          ],
          recommendations: ['Configure AGENT_OBSERVABILITY_METRIC_ALLOWLIST']
        }
      }
    }
  })

  assert.equal(status.observability.configured, true)
  assert.equal(status.observability.enabled, true)
  assert.deepEqual(status.observability.enabledTools, ['db_query_readonly', 'service_logs'])
  assert.deepEqual(status.observability.availableTools, ['service_logs'])
  assert.equal(status.observability.redisConfigured, true)
  assert.equal(status.observability.redisPort, 6379)
  assert.equal(status.observability.metricsUrlConfigured, true)
  assert.deepEqual(status.observability.allowedMetricNames, ['runtime_*'])
  assert.equal(status.observability.maxMetricLines, 2500)
  assert.equal(status.observability.maxMetricSamples, 200)
  assert.equal(status.observability.auditReport.status, 'warning')
  assert.equal(status.observability.auditReport.checks[0].key, 'metrics_allowlist')
})

test('normalizeRuntimeStatus keeps observability audit report ready for governance cards', () => {
  const status = normalizeRuntimeStatus({
    providers: {
      observability: {
        enabled: true,
        configured: true,
        available_tools: ['db_query_readonly'],
        audit_report: {
          status: 'healthy',
          enabled: true,
          available_tools: ['db_query_readonly'],
          checks: [
            { key: 'sql_readonly_guard', status: 'pass', severity: 'high', summary: 'ok' }
          ],
          recommendations: ['keep read-only role']
        }
      }
    }
  })

  assert.equal(status.observability.auditReport.enabled, true)
  assert.deepEqual(status.observability.auditReport.availableTools, ['db_query_readonly'])
  assert.equal(status.observability.auditReport.recommendations[0], 'keep read-only role')
})

test('normalizeRuntimeStatus preserves ops alerts and SLO summary', () => {
  const status = normalizeRuntimeStatus({
    ops: {
      alerts: {
        status: 'warning',
        active_alert_count: 2,
        total_alert_count: 4,
        by_severity: { warning: 2 },
        by_subsystem: { workspace: 1, browser: 1 },
        rules_configured: 9
      },
      slo: {
        status: 'breached',
        slo_count: 6,
        breached_count: 1,
        breached: [{ name: 'sandbox_execution_success_rate' }]
      }
    }
  })

  assert.equal(status.ops.alerts.status, 'warning')
  assert.equal(status.ops.alerts.activeAlertCount, 2)
  assert.equal(status.ops.alerts.bySubsystem.workspace, 1)
  assert.equal(status.ops.slo.status, 'breached')
  assert.equal(status.ops.slo.breachedCount, 1)
  assert.equal(status.ops.slo.breached[0].name, 'sandbox_execution_success_rate')
})

test('normalizeRuntimeStatus preserves web search quality evaluation', () => {
  const status = normalizeRuntimeStatus({
    providers: {
      web: {
        enabled: true,
        network_configured: true,
        search_quality: {
          require_url: true,
          require_title: true,
          require_snippet: true,
          allowed_schemes: ['https'],
          reject_disallowed_domains: true,
          reject_duplicates: true,
          evaluation: {
            protocol_version: 'managed-web.search-quality-suite.v1',
            status: 'passed',
            total: 3,
            passed: 3,
            warning: 0,
            failed: 0,
            average_score: 1
          }
        }
      }
    }
  })

  assert.equal(status.web.searchQuality.requireSnippet, true)
  assert.deepEqual(status.web.searchQuality.allowedSchemes, ['https'])
  assert.equal(status.web.searchQuality.evaluation.status, 'passed')
  assert.equal(status.web.searchQuality.evaluation.total, 3)
})

test('normalizeRuntimeStatus preserves web search quality evaluation summary and case details', () => {
  const status = normalizeRuntimeStatus({
    providers: {
      web: {
        search_quality: {
          require_url: true,
          require_title: true,
          require_snippet: false,
          allowed_schemes: ['https'],
          evaluation_protocol_version: 'managed-web.search-quality-suite.v1',
          evaluation: {
            protocol_version: 'managed-web.search-quality-suite.v1',
            status: 'warning',
            total: 1,
            passed: 0,
            warning: 1,
            failed: 0,
            average_score: 0.75,
            summary: '1 passed / 1 warning / 0 failed',
            policy_snapshot: {
              allowed_domains: ['docs.example.com']
            },
            results: [
              {
                name: 'sample',
                status: 'warning',
                score: 0.75,
                summary: 'case summary',
                accepted_count: 1,
                rejected_count: 0,
                checks: [{ name: 'accepted_count', passed: true, weight: 1 }]
              }
            ]
          }
        }
      }
    }
  })

  assert.equal(status.web.searchQuality.evaluationProtocolVersion, 'managed-web.search-quality-suite.v1')
  assert.equal(status.web.searchQuality.evaluation.summary, '1 passed / 1 warning / 0 failed')
  assert.equal(status.web.searchQuality.evaluation.policySnapshot.allowed_domains[0], 'docs.example.com')
  assert.equal(status.web.searchQuality.evaluation.results[0].checkCount, 1)
  assert.equal(status.web.searchQuality.evaluation.results[0].summary, 'case summary')
})
