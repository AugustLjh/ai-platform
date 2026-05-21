<template>
  <article class="verification-card" :class="statusClass">
    <div class="verification-head">
      <div>
        <div class="verification-kicker">{{ kindLabel }}</div>
        <h4>{{ artifact.name || 'Verification Report' }}</h4>
      </div>
      <span class="status-pill">{{ statusLabel }}</span>
    </div>

    <p v-if="summary" class="verification-summary">{{ summary }}</p>

    <dl v-if="structuredStats.length" class="verification-facts verification-structured-facts">
      <div v-for="item in structuredStats" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>

    <section v-if="structuredFindings.length" class="verification-block">
      <strong>结构化问题</strong>
      <ul class="finding-list">
        <li v-for="finding in structuredFindings" :key="finding.key">
          <span class="finding-severity">{{ finding.severity }}</span>
          <span class="finding-main">{{ finding.title }}</span>
          <span v-if="finding.location" class="finding-location">{{ finding.location }}</span>
        </li>
      </ul>
    </section>

    <section v-if="coverageFiles.length" class="verification-block">
      <strong>Coverage 明细</strong>
      <div class="coverage-table" role="table" aria-label="Coverage details">
        <div class="coverage-row coverage-head" role="row">
          <span>文件</span>
          <span>覆盖率</span>
          <span>Missing</span>
        </div>
        <div v-for="file in coverageFiles" :key="file.path" class="coverage-row" role="row">
          <span>{{ file.path }}</span>
          <span>{{ formatPercent(file.coverage_percent ?? file.coveragePercent) }}</span>
          <span>{{ file.missing ?? 'N/A' }}</span>
        </div>
      </div>
    </section>

    <dl class="verification-facts">
      <div>
        <dt>退出码</dt>
        <dd>{{ exitCodeLabel }}</dd>
      </div>
      <div>
        <dt>耗时</dt>
        <dd>{{ durationLabel }}</dd>
      </div>
      <div>
        <dt>目录</dt>
        <dd>{{ payload.cwd || '.' }}</dd>
      </div>
      <div>
        <dt>Runner</dt>
        <dd>{{ runnerLabel }}</dd>
      </div>
    </dl>

    <section v-if="commandText" class="verification-block">
      <strong>Command</strong>
      <pre>{{ commandText }}</pre>
    </section>

    <section v-if="stdout" class="verification-block">
      <strong>stdout</strong>
      <pre>{{ stdout }}</pre>
    </section>

    <section v-if="stderr" class="verification-block">
      <strong>stderr</strong>
      <pre>{{ stderr }}</pre>
    </section>

    <p v-if="payload.truncated" class="verification-note">
      日志已截断，完整输出需查看原始执行 artifact。
    </p>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  artifact: {
    type: Object,
    required: true
  }
})

const payload = computed(() => props.artifact?.payload || {})
const status = computed(() => String(payload.value.status || 'unknown').trim())
const statusClass = computed(() => `status-${status.value || 'unknown'}`)
const summary = computed(() => String(payload.value.summary || '').trim())
const stdout = computed(() => String(payload.value.logs?.stdout || '').trim())
const stderr = computed(() => String(payload.value.logs?.stderr || '').trim())
const commandText = computed(() => Array.isArray(payload.value.command) ? payload.value.command.join(' ') : '')
const structuredReport = computed(() => {
  const report = payload.value.structuredReport || payload.value.structured_report
  return report && typeof report === 'object' && !Array.isArray(report) ? report : null
})
const structuredReports = computed(() => Array.isArray(structuredReport.value?.reports) ? structuredReport.value.reports : [])
const exitCodeLabel = computed(() => payload.value.exitCode === null || payload.value.exitCode === undefined ? '未记录' : String(payload.value.exitCode))
const durationLabel = computed(() => {
  const value = Number(payload.value.durationMs)
  if (!Number.isFinite(value) || value <= 0) return '未记录'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
})
const runnerLabel = computed(() => {
  const runner = payload.value.runner || {}
  return runner.backend || runner.image || runner.container_id || '未记录'
})
const statusLabel = computed(() => {
  const labels = {
    completed: '通过',
    failed: '失败',
    timeout: '超时',
    cancelled: '已取消',
    unknown: '未知'
  }
  return labels[status.value] || status.value
})
const kindLabel = computed(() => {
  const labels = {
    browser_verify: '浏览器验证',
    test: '测试验证',
    lint: 'Lint 验证',
    build: '构建验证',
    shell: 'Sandbox 执行',
    typecheck: '类型检查',
    coverage: 'Coverage 验证',
    dependency_audit: '依赖审计'
  }
  return labels[payload.value.kind] || '验证报告'
})
const formatPercent = (value) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return 'N/A'
  return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`
}
const structuredStats = computed(() => {
  const stats = []
  for (const report of structuredReports.value) {
    if (!report || typeof report !== 'object') continue
    const reportSummary = report.summary && typeof report.summary === 'object' ? report.summary : {}
    if (report.kind === 'test') {
      const tests = Number(reportSummary.tests ?? 0)
      const failed = Number(reportSummary.failures ?? reportSummary.failed ?? 0)
      const errors = Number(reportSummary.errors ?? 0)
      const skipped = Number(reportSummary.skipped ?? 0)
      if (tests || failed || errors || skipped) {
        stats.push({ label: '测试统计', value: `${tests || 'N/A'} tests, ${failed} failed, ${errors} errors, ${skipped} skipped` })
      }
    }
    if (report.kind === 'coverage') {
      const percent = reportSummary.coverage_percent ?? reportSummary.coveragePercent
      stats.push({ label: '总覆盖率', value: formatPercent(percent) })
    }
    if (['lint', 'typecheck', 'dependency_audit'].includes(report.kind)) {
      const count = reportSummary.finding_count ?? reportSummary.findingCount
      if (count !== undefined && count !== null) stats.push({ label: '问题数', value: String(count) })
    }
  }
  return stats.slice(0, 4)
})
const structuredFindings = computed(() => {
  const items = []
  for (const report of structuredReports.value) {
    const candidates = [
      ...(Array.isArray(report?.failures) ? report.failures : []),
      ...(Array.isArray(report?.findings) ? report.findings : [])
    ]
    for (const finding of candidates) {
      if (!finding || typeof finding !== 'object') continue
      const path = finding.path || finding.source || ''
      const line = finding.line ? `:${finding.line}` : ''
      items.push({
        key: `${report.kind}-${items.length}-${finding.title || finding.message || path}`,
        severity: String(finding.severity || finding.type || 'info'),
        title: String(finding.title || finding.message || 'Finding'),
        location: path ? `${path}${line}` : ''
      })
    }
  }
  return items.slice(0, 8)
})
const coverageFiles = computed(() => {
  const report = structuredReports.value.find((item) => item?.kind === 'coverage' && Array.isArray(item.files))
  return report ? report.files.slice(0, 8) : []
})
</script>

<style scoped>
.verification-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: #ffffff;
}

.verification-card.status-completed {
  border-color: rgba(22, 163, 74, 0.24);
}

.verification-card.status-failed,
.verification-card.status-timeout {
  border-color: rgba(220, 38, 38, 0.24);
}

.verification-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.verification-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--primary-700);
}

.verification-head h4 {
  margin-top: 6px;
  font-size: 17px;
}

.status-pill {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.status-completed .status-pill {
  background: rgba(22, 163, 74, 0.12);
  color: #166534;
}

.status-failed .status-pill,
.status-timeout .status-pill {
  background: rgba(220, 38, 38, 0.12);
  color: #991b1b;
}

.verification-summary {
  margin-top: 10px;
  color: var(--gray-700);
  line-height: 1.6;
}

.verification-facts {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
}

.verification-structured-facts {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.verification-facts div {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  padding: 10px 12px;
  background: #fcfdfd;
  min-width: 0;
}

.verification-facts dt {
  color: var(--gray-500);
  font-size: 12px;
}

.verification-facts dd {
  margin-top: 6px;
  color: #0f172a;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.verification-block {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.verification-block strong {
  font-size: 12px;
  color: var(--gray-600);
}

.finding-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.finding-list li {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 10px;
  align-items: baseline;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.04);
}

.finding-severity {
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.1);
  color: #991b1b;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.finding-main {
  color: #0f172a;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.finding-location {
  grid-column: 2;
  color: var(--gray-500);
  font-family: var(--font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.coverage-table {
  display: grid;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  overflow: hidden;
}

.coverage-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px 90px;
  gap: 10px;
  padding: 9px 12px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  font-size: 12px;
}

.coverage-row:first-child {
  border-top: 0;
}

.coverage-head {
  background: rgba(15, 23, 42, 0.04);
  color: var(--gray-600);
  font-weight: 800;
}

.coverage-row span {
  overflow-wrap: anywhere;
}

pre {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.04);
  overflow: auto;
  max-height: 260px;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
}

.verification-note {
  margin-top: 12px;
  color: var(--gray-500);
  font-size: 12px;
}
</style>
