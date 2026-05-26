import { buildBrowserSessionTrendPoints } from './browserSessions.js'
import { normalizeWebSearchQualityEvaluation } from './webSearchQuality.js'

const cloneObject = (value) => (value && typeof value === 'object' ? { ...value } : {})

export const normalizeRuntimeStatus = (raw = {}) => {
  const providers = raw?.providers && typeof raw.providers === 'object' ? raw.providers : {}
  const workspace = providers.workspace && typeof providers.workspace === 'object' ? providers.workspace : {}
  const sandbox = providers.sandbox && typeof providers.sandbox === 'object' ? providers.sandbox : {}
  const web = providers.web && typeof providers.web === 'object' ? providers.web : {}
  const browser = providers.browser && typeof providers.browser === 'object' ? providers.browser : {}
  const observability = providers.observability && typeof providers.observability === 'object' ? providers.observability : {}
  const inspection = workspace.inspection && typeof workspace.inspection === 'object' ? workspace.inspection : {}
  const lifecycle = raw?.workspace_lifecycle && typeof raw.workspace_lifecycle === 'object' ? raw.workspace_lifecycle : {}
  const lifecycleLastRun = lifecycle.last_run && typeof lifecycle.last_run === 'object' ? lifecycle.last_run : null
  const lifecycleHistory = Array.isArray(lifecycle.history) ? lifecycle.history.filter((item) => item && typeof item === 'object') : []
  const lifecycleTrend = lifecycle.trend && typeof lifecycle.trend === 'object' ? lifecycle.trend : null
  const workspaceHealth = inspection.health && typeof inspection.health === 'object' ? inspection.health : {}
  const workspaceLockSummary = inspection.lock_summary && typeof inspection.lock_summary === 'object' ? inspection.lock_summary : {}
  const browserSessions = web.browser_sessions && typeof web.browser_sessions === 'object' ? web.browser_sessions : null
  const browserSessionHealth = browserSessions?.health && typeof browserSessions.health === 'object' ? browserSessions.health : {}
  const browserSessionTrend = browserSessions?.trend && typeof browserSessions.trend === 'object' ? browserSessions.trend : null
  const browserSessionHistory = Array.isArray(browserSessions?.history)
    ? browserSessions.history.filter((item) => item && typeof item === 'object')
    : []
  const ops = raw?.ops && typeof raw.ops === 'object' ? raw.ops : {}
  const opsAlerts = ops.alerts && typeof ops.alerts === 'object' ? ops.alerts : {}
  const opsSlo = ops.slo && typeof ops.slo === 'object' ? ops.slo : {}
  return {
    status: raw.status || 'idle',
    started: Boolean(raw.started),
    configuredProviders: Array.isArray(providers.configured) ? [...providers.configured] : [],
    workspace: {
      enabled: Boolean(workspace.enabled),
      baseRoot: workspace.base_root || workspace.baseRoot || '',
      sourceRoots: Array.isArray(workspace.source_roots || workspace.sourceRoots) ? [...(workspace.source_roots || workspace.sourceRoots)] : [],
      maxFiles: Number(workspace.max_files || workspace.maxFiles || 0),
      maxBytes: Number(workspace.max_bytes || workspace.maxBytes || 0),
      retentionHours: Number(workspace.retention_hours || workspace.retentionHours || 0),
      inspection: {
        workspaceCount: Number(inspection.workspace_count || inspection.workspaceCount || 0),
        expiredCount: Number(inspection.expired_count || inspection.expiredCount || 0),
        quotaExceededCount: Number(inspection.quota_exceeded_count || inspection.quotaExceededCount || 0),
        totalSizeBytes: Number(inspection.total_size_bytes || inspection.totalSizeBytes || 0),
        totalFileCount: Number(inspection.total_file_count || inspection.totalFileCount || 0),
        workspaces: Array.isArray(inspection.workspaces) ? [...inspection.workspaces] : [],
        generatedAt: inspection.generated_at || inspection.generatedAt || null,
        lockSummary: {
          lockCount: Number(workspaceLockSummary.lock_count || workspaceLockSummary.lockCount || 0),
          activeLockCount: Number(workspaceLockSummary.active_lock_count || workspaceLockSummary.activeLockCount || 0),
          staleLockCount: Number(workspaceLockSummary.stale_lock_count || workspaceLockSummary.staleLockCount || 0),
          orphanLockCount: Number(workspaceLockSummary.orphan_lock_count || workspaceLockSummary.orphanLockCount || 0),
          oldestLockAgeSeconds: workspaceLockSummary.oldest_lock_age_seconds || workspaceLockSummary.oldestLockAgeSeconds || null,
          locks: Array.isArray(workspaceLockSummary.locks) ? [...workspaceLockSummary.locks] : []
        },
        health: {
          status: workspaceHealth.status || 'unknown',
          score: Number(workspaceHealth.score || 0),
          summary: workspaceHealth.summary || '',
          issues: Array.isArray(workspaceHealth.issues) ? [...workspaceHealth.issues] : [],
          recoveryActions: Array.isArray(workspaceHealth.recovery_actions || workspaceHealth.recoveryActions)
            ? [...(workspaceHealth.recovery_actions || workspaceHealth.recoveryActions)]
            : []
        }
      },
      bindingPolicies: workspace.binding_policies && typeof workspace.binding_policies === 'object'
        ? { ...workspace.binding_policies }
        : {}
    },
    sandbox: {
      enabled: Boolean(sandbox.enabled),
      configured: Boolean(sandbox.configured),
      runnerConfigured: Boolean(sandbox.runner_configured || sandbox.runnerConfigured),
      runnerBackend: sandbox.runner_backend || sandbox.runnerBackend || '',
      dockerImage: sandbox.docker_image || sandbox.dockerImage || '',
      networkMode: sandbox.network_mode || sandbox.networkMode || '',
      limits: sandbox.limits && typeof sandbox.limits === 'object' ? { ...sandbox.limits } : {},
      isolation: sandbox.isolation && typeof sandbox.isolation === 'object'
        ? {
            status: sandbox.isolation.status || 'unknown',
            productionReady: Boolean(sandbox.isolation.production_ready || sandbox.isolation.productionReady),
            passed: Number(sandbox.isolation.passed || 0),
            failed: Number(sandbox.isolation.failed || 0),
            warning: Number(sandbox.isolation.warning || 0),
            checks: Array.isArray(sandbox.isolation.checks) ? [...sandbox.isolation.checks] : [],
            recoveryActions: Array.isArray(sandbox.isolation.recovery_actions || sandbox.isolation.recoveryActions)
              ? [...(sandbox.isolation.recovery_actions || sandbox.isolation.recoveryActions)]
              : []
          }
        : null
    },
    web: {
      enabled: Boolean(web.enabled),
      configured: Boolean(web.configured),
      networkConfigured: Boolean(web.network_configured || web.networkConfigured),
      allowedDomains: Array.isArray(web.allowed_domains || web.allowedDomains) ? [...(web.allowed_domains || web.allowedDomains)] : [],
      deniedDomains: Array.isArray(web.denied_domains || web.deniedDomains) ? [...(web.denied_domains || web.deniedDomains)] : [],
      searchEndpoint: web.search_endpoint || web.searchEndpoint || '',
      searchQuality: web.search_quality && typeof web.search_quality === 'object'
        ? {
            requireUrl: Boolean(web.search_quality.require_url || web.search_quality.requireUrl),
            requireTitle: Boolean(web.search_quality.require_title || web.search_quality.requireTitle),
            requireSnippet: Boolean(web.search_quality.require_snippet || web.search_quality.requireSnippet),
            allowedSchemes: Array.isArray(web.search_quality.allowed_schemes || web.search_quality.allowedSchemes)
              ? [...(web.search_quality.allowed_schemes || web.search_quality.allowedSchemes)]
              : [],
            rejectDisallowedDomains: Boolean(web.search_quality.reject_disallowed_domains || web.search_quality.rejectDisallowedDomains),
            rejectDuplicates: Boolean(web.search_quality.reject_duplicates || web.search_quality.rejectDuplicates),
            evaluationProtocolVersion: web.search_quality.evaluation_protocol_version || web.search_quality.evaluationProtocolVersion || '',
            evaluation: normalizeWebSearchQualityEvaluation(web.search_quality.evaluation)
          }
        : {
            requireUrl: true,
            requireTitle: true,
            requireSnippet: false,
            allowedSchemes: ['https'],
            rejectDisallowedDomains: true,
            rejectDuplicates: true,
            evaluationProtocolVersion: '',
            evaluation: null
          },
      browserSessions: browserSessions
        ? {
            sessionCount: Number(browserSessions.session_count || browserSessions.sessionCount || 0),
            activeSessionCount: Number(browserSessions.active_session_count || browserSessions.activeSessionCount || 0),
            expiredSessionCount: Number(browserSessions.expired_session_count || browserSessions.expiredSessionCount || 0),
            oldestSessionAgeSeconds: browserSessions.oldest_session_age_seconds || browserSessions.oldestSessionAgeSeconds || null,
            sessionTtlSeconds: Number(browserSessions.session_ttl_seconds || browserSessions.sessionTtlSeconds || 0),
            networkErrorCount: Number(browserSessions.network_error_count || browserSessions.networkErrorCount || 0),
            consoleMessageCount: Number(browserSessions.console_message_count || browserSessions.consoleMessageCount || 0),
            sessions: Array.isArray(browserSessions.sessions) ? [...browserSessions.sessions] : [],
            recoveryActions: Array.isArray(browserSessions.recovery_actions || browserSessions.recoveryActions)
              ? [...(browserSessions.recovery_actions || browserSessions.recoveryActions)]
              : [],
            expiredSessionIds: Array.isArray(browserSessions.expired_session_ids || browserSessions.expiredSessionIds)
              ? [...(browserSessions.expired_session_ids || browserSessions.expiredSessionIds)]
              : [],
            health: {
              status: browserSessionHealth.status || 'unknown',
              score: Number(browserSessionHealth.score || 0),
              summary: browserSessionHealth.summary || '',
              issues: Array.isArray(browserSessionHealth.issues) ? [...browserSessionHealth.issues] : [],
              recoveryActions: Array.isArray(browserSessionHealth.recovery_actions || browserSessionHealth.recoveryActions)
                ? [...(browserSessionHealth.recovery_actions || browserSessionHealth.recoveryActions)]
                : []
            },
            alerts: Array.isArray(browserSessions.alerts) ? [...browserSessions.alerts] : [],
            history: browserSessionHistory.map((item) => ({
              sampledAt: item.sampled_at || item.sampledAt || null,
              sessionCount: Number(item.session_count || item.sessionCount || 0),
              activeSessionCount: Number(item.active_session_count || item.activeSessionCount || 0),
              expiredSessionCount: Number(item.expired_session_count || item.expiredSessionCount || 0),
              networkErrorCount: Number(item.network_error_count || item.networkErrorCount || 0),
              consoleMessageCount: Number(item.console_message_count || item.consoleMessageCount || 0),
              health: item.health && typeof item.health === 'object' ? { ...item.health } : {}
            })),
            trendPoints: buildBrowserSessionTrendPoints(browserSessionHistory),
            trend: browserSessionTrend
              ? {
                  status: browserSessionTrend.status || 'unknown',
                  windowSize: Number(browserSessionTrend.window_size || browserSessionTrend.windowSize || 0),
                  firstSampledAt: browserSessionTrend.first_sampled_at || browserSessionTrend.firstSampledAt || null,
                  lastSampledAt: browserSessionTrend.last_sampled_at || browserSessionTrend.lastSampledAt || null,
                  summary: browserSessionTrend.summary || '',
                  delta: browserSessionTrend.delta && typeof browserSessionTrend.delta === 'object' ? { ...browserSessionTrend.delta } : {}
                }
              : null
          }
        : null
    },
    browser: {
      enabled: Boolean(browser.enabled),
      configured: Boolean(browser.configured),
      backend: browser.backend || '',
      name: browser.name || '',
      runtimeAvailable: Boolean(browser.runtime_available || browser.runtimeAvailable),
      runtimeReason: browser.runtime_reason || browser.runtimeReason || '',
      sessionTtlSeconds: Number(browser.session_ttl_seconds || browser.sessionTtlSeconds || 0)
    },
    observability: {
      enabled: Boolean(observability.enabled),
      configured: Boolean(observability.configured),
      enabledTools: Array.isArray(observability.enabled_tools || observability.enabledTools)
        ? [...(observability.enabled_tools || observability.enabledTools)]
        : [],
      availableTools: Array.isArray(observability.available_tools || observability.availableTools)
        ? [...(observability.available_tools || observability.availableTools)]
        : [],
      dbConfigured: Boolean(observability.db_configured || observability.dbConfigured),
      redisConfigured: Boolean(observability.redis_configured || observability.redisConfigured),
      redisHost: observability.redis_host || observability.redisHost || '',
      redisPort: observability.redis_port || observability.redisPort || null,
      allowedHttpDomains: Array.isArray(observability.allowed_http_domains || observability.allowedHttpDomains)
        ? [...(observability.allowed_http_domains || observability.allowedHttpDomains)]
        : [],
      allowLoopbackHttp: Boolean(observability.allow_loopback_http || observability.allowLoopbackHttp),
      defaultHealthUrl: observability.default_health_url || observability.defaultHealthUrl || '',
      metricsUrlConfigured: Boolean(observability.metrics_url_configured || observability.metricsUrlConfigured),
      allowedMetricNames: Array.isArray(observability.allowed_metric_names || observability.allowedMetricNames)
        ? [...(observability.allowed_metric_names || observability.allowedMetricNames)]
        : [],
      maxMetricLines: Number(observability.max_metric_lines || observability.maxMetricLines || 0),
      maxMetricSamples: Number(observability.max_metric_samples || observability.maxMetricSamples || 0),
      logRoots: Array.isArray(observability.log_roots || observability.logRoots)
        ? [...(observability.log_roots || observability.logRoots)]
        : [],
      maxRows: Number(observability.max_rows || observability.maxRows || 0),
      maxOutputChars: Number(observability.max_output_chars || observability.maxOutputChars || 0),
      timeoutSeconds: Number(observability.timeout_seconds || observability.timeoutSeconds || 0),
      auditReport: observability.audit_report && typeof observability.audit_report === 'object'
        ? {
            status: observability.audit_report.status || 'unknown',
            enabled: Boolean(observability.audit_report.enabled),
            availableTools: Array.isArray(observability.audit_report.available_tools || observability.audit_report.availableTools)
              ? [...(observability.audit_report.available_tools || observability.audit_report.availableTools)]
              : [],
            checks: Array.isArray(observability.audit_report.checks)
              ? observability.audit_report.checks.map((check) => ({
                  key: check.key || '',
                  status: check.status || 'unknown',
                  severity: check.severity || 'medium',
                  summary: check.summary || ''
                }))
              : [],
            recommendations: Array.isArray(observability.audit_report.recommendations || observability.audit_report.recommendations)
              ? [...(observability.audit_report.recommendations || observability.audit_report.recommendations)]
              : []
          }
        : null
    },
    ops: {
      alerts: {
        status: opsAlerts.status || 'healthy',
        activeAlertCount: Number(opsAlerts.active_alert_count || opsAlerts.activeAlertCount || 0),
        totalAlertCount: Number(opsAlerts.total_alert_count || opsAlerts.totalAlertCount || 0),
        bySeverity: opsAlerts.by_severity && typeof opsAlerts.by_severity === 'object' ? { ...opsAlerts.by_severity } : {},
        bySubsystem: opsAlerts.by_subsystem && typeof opsAlerts.by_subsystem === 'object' ? { ...opsAlerts.by_subsystem } : {},
        rulesConfigured: Number(opsAlerts.rules_configured || opsAlerts.rulesConfigured || 0)
      },
      slo: {
        status: opsSlo.status || 'healthy',
        sloCount: Number(opsSlo.slo_count || opsSlo.sloCount || 0),
        breachedCount: Number(opsSlo.breached_count || opsSlo.breachedCount || 0),
        breached: Array.isArray(opsSlo.breached) ? [...opsSlo.breached] : []
      }
    },
    workspaceLifecycle: {
      enabled: Boolean(lifecycle.enabled),
      running: Boolean(lifecycle.running),
      intervalSeconds: Number(lifecycle.interval_seconds || lifecycle.intervalSeconds || 0),
      dryRun: Boolean(lifecycle.dry_run || lifecycle.dryRun),
      maxDeletePerCycle: Number(lifecycle.max_delete_per_cycle || lifecycle.maxDeletePerCycle || 0),
      quotaAlertThresholdBytes: Number(lifecycle.quota_alert_threshold_bytes || lifecycle.quotaAlertThresholdBytes || 0),
      quotaAlertThresholdCount: Number(lifecycle.quota_alert_threshold_count || lifecycle.quotaAlertThresholdCount || 0),
      expiredAlertThreshold: Number(lifecycle.expired_alert_threshold || lifecycle.expiredAlertThreshold || 0),
      lastRunAtMonotonic: lifecycle.last_run_at_monotonic || lifecycle.lastRunAtMonotonic || null,
      lastCompletedAt: lifecycle.last_completed_at || lifecycle.lastCompletedAt || null,
      lastRun: lifecycleLastRun
        ? {
            generatedAt: lifecycleLastRun.generated_at || lifecycleLastRun.generatedAt || null,
            inspection: lifecycleLastRun.inspection && typeof lifecycleLastRun.inspection === 'object'
              ? { ...lifecycleLastRun.inspection }
              : {},
            cleanup: lifecycleLastRun.cleanup && typeof lifecycleLastRun.cleanup === 'object'
              ? { ...lifecycleLastRun.cleanup }
              : null,
            lockSummary: lifecycleLastRun.inspection?.lock_summary && typeof lifecycleLastRun.inspection.lock_summary === 'object'
              ? { ...lifecycleLastRun.inspection.lock_summary }
              : lifecycleLastRun.inspection?.lockSummary && typeof lifecycleLastRun.inspection.lockSummary === 'object'
                ? { ...lifecycleLastRun.inspection.lockSummary }
                : {},
            health: lifecycleLastRun.inspection?.health && typeof lifecycleLastRun.inspection.health === 'object'
              ? { ...lifecycleLastRun.inspection.health }
              : {},
            alerts: Array.isArray(lifecycleLastRun.alerts) ? [...lifecycleLastRun.alerts] : []
          }
        : null,
      history: lifecycleHistory.map((item) => ({
        generatedAt: item.generated_at || item.generatedAt || null,
        inspection: item.inspection && typeof item.inspection === 'object' ? { ...item.inspection } : {},
        cleanup: item.cleanup && typeof item.cleanup === 'object' ? { ...item.cleanup } : null,
        alerts: Array.isArray(item.alerts) ? [...item.alerts] : []
      })),
      trend: lifecycleTrend
        ? {
            status: lifecycleTrend.status || 'unknown',
            windowSize: Number(lifecycleTrend.window_size || lifecycleTrend.windowSize || 0),
            firstGeneratedAt: lifecycleTrend.first_generated_at || lifecycleTrend.firstGeneratedAt || null,
            lastGeneratedAt: lifecycleTrend.last_generated_at || lifecycleTrend.lastGeneratedAt || null,
            summary: lifecycleTrend.summary || '',
            delta: lifecycleTrend.delta && typeof lifecycleTrend.delta === 'object' ? { ...lifecycleTrend.delta } : {}
          }
        : null,
      recentAlerts: Array.isArray(lifecycle.recent_alerts || lifecycle.recentAlerts)
        ? [...(lifecycle.recent_alerts || lifecycle.recentAlerts)]
        : [],
      recoveryActions: Array.isArray(lifecycle.recovery_actions || lifecycle.recoveryActions)
        ? [...(lifecycle.recovery_actions || lifecycle.recoveryActions)]
        : []
    }
  }
}

export const cloneRuntimeStatus = (status = null) => cloneObject(status)
