<template>
  <section class="invocation-panel">
    <div class="panel-head">
      <div>
        <h3>委派明细</h3>
        <p>聚合展示 handoff、policy snapshot、child run 状态、恢复语义与最终结果摘要。</p>
      </div>
      <span class="panel-count">{{ totalEntries }}</span>
    </div>

    <div v-if="totalEntries === 0" class="empty-state">
      当前没有发生 subagent 委派。
    </div>

    <div v-else class="invocation-list">
      <article
        v-for="entry in entries"
        :key="entry.id"
        :class="['invocation-card', { attention: entry.needsAttention, danger: entry.attentionTone === 'danger' }]"
      >
        <div class="invocation-head">
          <div>
            <div class="invocation-title">{{ entry.target }}</div>
            <div class="invocation-subtitle">
              <span v-if="entry.parentRunId" class="mono">parent {{ entry.parentRunId.slice(0, 8) }}</span>
              <span v-if="entry.childRunId" class="mono">child {{ entry.childRunId.slice(0, 8) }}</span>
              <span v-if="entry.publicationId" class="mono">pub {{ entry.publicationId.slice(0, 8) }}</span>
            </div>
          </div>
          <span :class="['status-pill', entry.status, entry.attentionTone]">{{ entry.statusLabel }}</span>
        </div>

        <p v-if="entry.attentionSummary" class="invocation-attention">{{ entry.attentionSummary }}</p>
        <p v-if="entry.taskMessage" class="invocation-task">{{ entry.taskMessage }}</p>

        <div class="fact-grid">
          <div v-if="entry.constraints.length > 0" class="fact-card">
            <span>约束</span>
            <strong>{{ entry.constraints.length }} 条</strong>
          </div>
          <div v-if="entry.reviewRequirement" class="fact-card">
            <span>评审要求</span>
            <strong>{{ entry.reviewRequirement }}</strong>
          </div>
          <div v-if="entry.reviewSummary" class="fact-card">
            <span>评审结论</span>
            <strong>{{ entry.reviewSummary }}</strong>
          </div>
          <div v-if="entry.knowledgeSummary" class="fact-card">
            <span>知识权限</span>
            <strong>{{ entry.knowledgeSummary }}</strong>
          </div>
          <div v-if="entry.governanceSummary" class="fact-card">
            <span>治理限制</span>
            <strong>{{ entry.governanceSummary }}</strong>
          </div>
          <div v-if="entry.recoverySummary" class="fact-card">
            <span>恢复语义</span>
            <strong>{{ entry.recoverySummary }}</strong>
          </div>
        </div>

        <div v-if="entry.governance.warnings.length > 0" class="warning-list">
          <div
            v-for="warning in entry.governance.warnings"
            :key="warning"
            class="warning-chip"
          >
            {{ warning }}
          </div>
        </div>

        <div v-if="entry.constraints.length > 0" class="meta-section">
          <span class="meta-label">Constraints</span>
          <div class="meta-chip-list">
            <span v-for="itemText in entry.constraints" :key="itemText" class="meta-chip">
              {{ itemText }}
            </span>
          </div>
        </div>

        <div v-if="entry.governance.enforcement.hardLimits.length > 0" class="meta-section">
          <span class="meta-label">硬限制</span>
          <div class="meta-chip-list">
            <span v-for="itemText in entry.governance.enforcement.hardLimits" :key="itemText" class="meta-chip">
              {{ itemText }}
            </span>
          </div>
        </div>

        <div v-if="entry.governanceBudgetLines.length > 0" class="meta-section">
          <span class="meta-label">Budget</span>
          <div class="meta-chip-list">
            <span v-for="itemText in entry.governanceBudgetLines" :key="itemText" class="meta-chip budget">
              {{ itemText }}
            </span>
          </div>
        </div>

        <div v-if="entry.waitingUserPathSummary" class="meta-note">
          waiting-user 链路：{{ entry.waitingUserPathSummary }}
        </div>

        <div v-if="entry.governance.enforcement.note" class="meta-note">
          {{ entry.governance.enforcement.note }}
        </div>

        <div v-if="entry.governance.blockers.length > 0" class="meta-section danger-section">
          <span class="meta-label">阻塞原因</span>
          <div class="meta-chip-list">
            <span v-for="blocker in entry.governance.blockers" :key="`${blocker.code}-${blocker.message}`" class="meta-chip danger-chip">
              {{ blocker.message || blocker.code }}
            </span>
          </div>
        </div>

        <div v-if="entry.governance.recovery.actions.length > 0" class="meta-section recovery-section">
          <span class="meta-label">恢复建议</span>
          <div class="meta-chip-list">
            <span v-for="itemText in entry.governance.recovery.actions" :key="itemText" class="meta-chip recovery-chip">
              {{ itemText }}
            </span>
          </div>
        </div>

        <div class="meta-line">
          <span v-if="entry.startedAt">开始于 {{ formatTime(entry.startedAt) }}</span>
          <span v-if="entry.completedAt">结束于 {{ formatTime(entry.completedAt) }}</span>
        </div>

        <div v-if="entry.promotedArtifacts.length > 0" class="meta-section">
          <span class="meta-label">已提升产物</span>
          <div class="meta-chip-list">
            <span v-for="artifact in entry.promotedArtifacts" :key="artifactKey(artifact)" class="meta-chip">
              {{ artifactLabel(artifact) }}
            </span>
          </div>
        </div>

        <AgentSubagentReviewCard :review-result="entry.reviewResult" />
        <pre v-if="entry.resultSummary" class="result-preview">{{ entry.resultSummary }}</pre>
      </article>

      <article
        v-for="entry in resolvedEntries"
        :key="`resolved-${entry.id}`"
        class="invocation-card resolved-card"
      >
        <div class="invocation-head">
          <div>
            <div class="invocation-title">{{ entry.targetName }}</div>
            <div class="invocation-subtitle">
              <span v-if="entry.parentStepId" class="mono">step {{ entry.parentStepId.slice(0, 8) }}</span>
              <span v-if="entry.childRunId" class="mono">child {{ entry.childRunId.slice(0, 8) }}</span>
            </div>
          </div>
          <span :class="['status-pill', entry.status]">已收敛</span>
        </div>

        <p v-if="entry.summary" class="invocation-task">{{ entry.summary }}</p>
        <div class="fact-grid">
          <div v-if="entry.finalOutputText" class="fact-card">
            <span>最终文本</span>
            <strong>{{ entry.finalOutputText }}</strong>
          </div>
          <div v-if="entry.promotedArtifacts.length > 0" class="fact-card">
            <span>提升产物</span>
            <strong>{{ entry.promotedArtifacts.length }} 个</strong>
          </div>
          <div v-if="entry.reviewResult.decision" class="fact-card">
            <span>决策</span>
            <strong>{{ entry.reviewResult.decision }}</strong>
          </div>
          <div v-if="entry.progress.summary" class="fact-card">
            <span>进度</span>
            <strong>{{ entry.progress.summary }}</strong>
          </div>
        </div>

        <div v-if="entry.promotedArtifacts.length > 0" class="meta-section">
          <span class="meta-label">已提升产物</span>
          <div class="meta-chip-list">
            <span v-for="artifact in entry.promotedArtifacts" :key="artifactKey(artifact)" class="meta-chip">
              {{ artifactLabel(artifact) }}
            </span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import AgentSubagentReviewCard from './AgentSubagentReviewCard.vue'
import { buildInvocationProtocolEntry } from '@/utils/agentRunTree'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  },
  resolvedItems: {
    type: Array,
    default: () => []
  }
})

const entries = computed(() => (
  props.items.map((item) => {
    const entry = buildInvocationProtocolEntry(item)
    return {
      ...entry,
      parentRunId: item.parentRun?.id || '',
      publicationId: item.invocation?.publicationId || '',
      promotedArtifacts: item.invocation?.resultPayload?.final_result?.artifacts || item.invocation?.resultPayload?.finalResult?.artifacts || []
    }
  })
))

const resolvedEntries = computed(() => (
  props.resolvedItems.map((item) => ({
    id: item.id || item.invocationId || item.childRunId,
    targetName: item.target?.name || item.target?.slug || '已收敛子任务',
    childRunId: item.childRunId || '',
    parentStepId: item.parentStepId || '',
    status: item.stepStatus || item.status || 'completed',
    summary: item.summary || '',
    finalOutputText: item.finalOutputText || '',
    promotedArtifacts: item.promotedArtifacts || [],
    progress: item.progress || { summary: '', state: 'unknown' },
    reviewResult: item.reviewResult || { decision: '' }
  }))
))

const totalEntries = computed(() => entries.value.length + resolvedEntries.value.length)

const artifactLabel = (artifact) => {
  if (!artifact || typeof artifact !== 'object') return '未命名产物'
  return artifact.title || artifact.name || artifact.artifact_type || artifact.artifactType || '未命名产物'
}

const artifactKey = (artifact) => {
  if (!artifact || typeof artifact !== 'object') return 'artifact'
  return [
    artifact.artifact_type || artifact.artifactType || '',
    artifact.title || artifact.name || '',
    artifact.uri || '',
    artifact.path || ''
  ].join(':')
}

const formatTime = (value) => {
  if (!value) return '未知时间'
  return new Date(value).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<style scoped>
.invocation-panel {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  max-height: min(72vh, 840px);
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.panel-head h3 {
  margin: 0 0 6px;
  font-size: 18px;
}

.panel-head p {
  color: var(--gray-600);
  font-size: 14px;
}

.panel-count {
  min-width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.empty-state {
  padding: 20px;
  border-radius: var(--radius-lg);
  background: var(--gray-50);
  color: var(--gray-500);
  text-align: center;
}

.invocation-list {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.invocation-card {
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(180deg, #fffef8 0%, #fffbeb 100%);
  max-height: 480px;
  overflow: auto;
}

.invocation-card.attention {
  border-color: rgba(245, 158, 11, 0.3);
}

.invocation-card.danger {
  border-color: rgba(239, 68, 68, 0.22);
  background: linear-gradient(180deg, #fffafa 0%, #fff5f5 100%);
}

.invocation-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.invocation-title {
  font-weight: 700;
  color: #0f172a;
}

.invocation-subtitle,
.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.status-pill.pending,
.status-pill.queued {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.status-pill.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.status-pill.waiting_user,
.status-pill.warning {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.status-pill.completed {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.status-pill.failed,
.status-pill.cancelled,
.status-pill.danger {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.invocation-attention,
.invocation-task {
  margin-top: 10px;
  line-height: 1.6;
  color: #475569;
  white-space: pre-wrap;
}

.invocation-attention {
  color: #92400e;
  font-weight: 600;
}

.fact-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.fact-card {
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(15, 23, 42, 0.06);
  padding: 12px;
}

.fact-card span {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 4px;
}

.fact-card strong {
  color: #0f172a;
  line-height: 1.5;
}

.warning-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.warning-chip,
.meta-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
}

.warning-chip {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.danger-chip {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.recovery-chip {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.meta-section {
  margin-top: 12px;
}

.meta-label {
  display: block;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.meta-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-chip {
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
}

.meta-chip.budget {
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
}

.meta-note {
  margin-top: 12px;
  color: #475569;
  font-size: 13px;
  line-height: 1.6;
}

.result-preview {
  margin-top: 12px;
  border-radius: 16px;
  padding: 12px;
  background: rgba(15, 23, 42, 0.04);
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
