<template>
  <article class="artifact-card">
    <div class="artifact-head">
      <div>
        <div class="artifact-kicker">审查发现</div>
        <h4>{{ artifact.name || 'Review Findings' }}</h4>
      </div>
      <span class="artifact-count">{{ findings.length }}</span>
    </div>

    <div v-if="findings.length === 0" class="artifact-empty">
      当前没有可展示的发现。
    </div>

    <div v-else class="finding-list">
      <section v-for="(finding, index) in findings" :key="`${finding.title}-${index}`" class="finding-card">
        <div class="finding-head">
          <strong>{{ finding.title || `Finding ${index + 1}` }}</strong>
          <span :class="['severity-pill', severityClass(finding.severity)]">{{ severityLabel(finding.severity) }}</span>
        </div>
        <p v-if="finding.description" class="finding-description">{{ finding.description }}</p>
        <div v-if="finding.path || finding.line" class="finding-meta">
          <span v-if="finding.path">{{ finding.path }}</span>
          <span v-if="finding.line">Line {{ finding.line }}</span>
        </div>
        <pre v-if="finding.code">{{ finding.code }}</pre>
      </section>
    </div>
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

const findings = computed(() => Array.isArray(props.artifact?.payload?.items) ? props.artifact.payload.items : [])

const severityLabel = (value) => {
  const mapping = {
    critical: 'Critical',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    info: 'Info'
  }
  return mapping[String(value || '').toLowerCase()] || value || 'Info'
}

const severityClass = (value) => {
  const normalized = String(value || 'info').toLowerCase()
  return ['critical', 'high', 'medium', 'low'].includes(normalized) ? normalized : 'info'
}
</script>

<style scoped>
.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
  max-height: min(52vh, 520px);
  overflow: auto;
}

.artifact-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.artifact-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: #b45309;
}

.artifact-head h4 {
  margin-top: 6px;
  font-size: 17px;
}

.artifact-count {
  min-width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  font-weight: 700;
}

.artifact-empty {
  margin-top: 12px;
  color: var(--gray-500);
  font-size: 14px;
}

.finding-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
}

.finding-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  padding: 14px;
  background: white;
}

.finding-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.severity-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.severity-pill.critical,
.severity-pill.high {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.severity-pill.medium {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.severity-pill.low,
.severity-pill.info {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.finding-description {
  margin-top: 10px;
  color: var(--gray-700);
  line-height: 1.6;
}

.finding-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  color: var(--gray-500);
  font-size: 12px;
}

pre {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.04);
  overflow: auto;
  max-height: 220px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
</style>
