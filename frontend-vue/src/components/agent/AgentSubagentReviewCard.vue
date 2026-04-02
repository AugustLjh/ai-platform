<template>
  <section v-if="isVisible" class="review-card">
    <div class="review-head">
      <div>
        <div class="review-kicker">{{ reviewModeLabel(reviewResult.mode) }} 结果</div>
        <h4>{{ reviewDecisionLabel(reviewResult.decision) }}</h4>
      </div>
      <span :class="['decision-pill', reviewResult.decision]">{{ reviewDecisionLabel(reviewResult.decision) }}</span>
    </div>

    <p v-if="reviewResult.summary" class="review-summary">{{ reviewResult.summary }}</p>
    <p v-if="reviewResult.conclusion" class="review-conclusion">{{ reviewResult.conclusion }}</p>

    <div class="fact-grid">
      <div class="fact-card">
        <span>结论</span>
        <strong>{{ reviewDecisionLabel(reviewResult.decision) }}</strong>
      </div>
      <div v-if="reviewResult.findingCount > 0" class="fact-card">
        <span>Findings</span>
        <strong>{{ reviewResult.findingCount }} 条</strong>
      </div>
      <div v-if="reviewResult.blockingFindingCount > 0" class="fact-card">
        <span>阻塞问题</span>
        <strong>{{ reviewResult.blockingFindingCount }} 条</strong>
      </div>
      <div v-if="reviewResult.testGaps.length > 0" class="fact-card">
        <span>测试缺口</span>
        <strong>{{ reviewResult.testGaps.length }} 项</strong>
      </div>
      <div v-if="reviewResult.childStatus" class="fact-card">
        <span>Child 状态</span>
        <strong>{{ reviewResult.childStatus }}</strong>
      </div>
    </div>

    <div v-if="previewFindings.length > 0" class="finding-list">
      <article v-for="(finding, index) in previewFindings" :key="`${finding.title}-${index}`" class="finding-item">
        <div class="finding-head">
          <strong>{{ finding.title }}</strong>
          <span :class="['severity-pill', finding.severity]">{{ finding.severity }}</span>
        </div>
        <p>{{ finding.description }}</p>
        <div v-if="finding.path || finding.line" class="finding-meta">
          <span v-if="finding.path" class="mono">{{ finding.path }}</span>
          <span v-if="finding.line">L{{ finding.line }}</span>
        </div>
      </article>
    </div>

    <div v-if="reviewResult.testGaps.length > 0" class="gap-list">
      <span v-for="(gap, index) in previewTestGaps" :key="`${gap}-${index}`" class="gap-chip">{{ gap }}</span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { reviewDecisionLabel, reviewModeLabel } from '@/utils/agentRunTree'

const props = defineProps({
  reviewResult: {
    type: Object,
    default: () => ({})
  }
})

const isVisible = computed(() => (
  Boolean(props.reviewResult?.required) ||
  ['reviewer', 'judge'].includes(props.reviewResult?.mode)
))

const previewFindings = computed(() => (
  Array.isArray(props.reviewResult?.findings) ? props.reviewResult.findings.slice(0, 3) : []
))

const previewTestGaps = computed(() => (
  Array.isArray(props.reviewResult?.testGaps) ? props.reviewResult.testGaps.slice(0, 3) : []
))
</script>

<style scoped>
.review-card {
  margin-top: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.96) 100%);
}

.review-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.review-kicker {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 700;
  color: #0f766e;
  margin-bottom: 4px;
}

.review-head h4 {
  margin: 0;
  color: #0f172a;
}

.review-summary,
.review-conclusion {
  margin-top: 10px;
  color: #334155;
  line-height: 1.6;
}

.review-conclusion {
  color: #475569;
}

.fact-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.fact-card {
  border-radius: 14px;
  padding: 10px 12px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.fact-card span {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.fact-card strong {
  color: #0f172a;
}

.decision-pill,
.severity-pill,
.gap-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}

.decision-pill.approved,
.decision-pill.approved_with_findings {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.decision-pill.changes_requested,
.decision-pill.needs_input,
.severity-pill.medium {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.decision-pill.rejected,
.decision-pill.failed,
.decision-pill.cancelled,
.severity-pill.high,
.severity-pill.critical {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.decision-pill.not_required,
.decision-pill.inconclusive,
.severity-pill.low,
.severity-pill.info,
.gap-chip {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.finding-list {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.finding-item {
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.finding-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.finding-item p {
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.6;
}

.finding-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 12px;
  color: #64748b;
}

.gap-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mono {
  font-family: var(--font-mono);
}
</style>
