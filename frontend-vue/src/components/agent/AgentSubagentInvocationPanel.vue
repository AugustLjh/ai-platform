<template>
  <section class="invocation-panel">
    <div class="panel-head">
      <div>
        <h3>委派明细</h3>
        <p>聚合展示 handoff、policy snapshot、child run 状态和最终结果摘要。</p>
      </div>
      <span class="panel-count">{{ items.length }}</span>
    </div>

    <div v-if="items.length === 0" class="empty-state">
      当前没有发生 subagent 委派。
    </div>

    <div v-else class="invocation-list">
      <article v-for="item in items" :key="item.invocation.id" class="invocation-card">
        <div class="invocation-head">
          <div>
            <div class="invocation-title">{{ summarizeInvocationTarget(item.invocation) }}</div>
            <div class="invocation-subtitle">
              <span v-if="item.parentRun?.id" class="mono">parent {{ item.parentRun.id.slice(0, 8) }}</span>
              <span v-if="item.childRun?.run?.id" class="mono">child {{ item.childRun.run.id.slice(0, 8) }}</span>
              <span v-if="item.invocation.publicationId" class="mono">pub {{ item.invocation.publicationId.slice(0, 8) }}</span>
            </div>
          </div>
          <span :class="['status-pill', item.invocation.status]">{{ item.invocation.status }}</span>
        </div>

        <p v-if="summarizeInvocationTask(item.invocation)" class="invocation-task">
          {{ summarizeInvocationTask(item.invocation) }}
        </p>

        <div class="fact-grid">
          <div v-if="constraintCount(item.invocation)" class="fact-card">
            <span>约束</span>
            <strong>{{ constraintCount(item.invocation) }} 条</strong>
          </div>
          <div v-if="reviewRequirement(item.invocation)" class="fact-card">
            <span>评审要求</span>
            <strong>{{ reviewRequirement(item.invocation) }}</strong>
          </div>
          <div v-if="summarizeInvocationReview(item.invocation)" class="fact-card">
            <span>评审结论</span>
            <strong>{{ summarizeInvocationReview(item.invocation) }}</strong>
          </div>
          <div v-if="knowledgeSummary(item.invocation)" class="fact-card">
            <span>知识权限</span>
            <strong>{{ knowledgeSummary(item.invocation) }}</strong>
          </div>
          <div v-if="childStatusSummary(item)" class="fact-card">
            <span>Child 状态</span>
            <strong>{{ childStatusSummary(item) }}</strong>
          </div>
        </div>

        <div class="meta-line">
          <span v-if="item.invocation.startedAt">开始于 {{ formatTime(item.invocation.startedAt) }}</span>
          <span v-if="item.invocation.completedAt">结束于 {{ formatTime(item.invocation.completedAt) }}</span>
        </div>

        <AgentSubagentReviewCard :review-result="getInvocationReviewResult(item.invocation)" />
        <pre v-if="resultSummary(item.invocation)" class="result-preview">{{ resultSummary(item.invocation) }}</pre>
      </article>
    </div>
  </section>
</template>

<script setup>
import AgentSubagentReviewCard from './AgentSubagentReviewCard.vue'
import {
  getInvocationReviewResult,
  summarizeInvocationReview,
  summarizeInvocationTarget,
  summarizeInvocationTask
} from '@/utils/agentRunTree'

defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

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

const getPolicySnapshot = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  return requestPayload.policy_snapshot || requestPayload.policySnapshot || {}
}

const constraintCount = (invocation) => {
  const requestPayload = invocation?.requestPayload || {}
  const constraints = Array.isArray(requestPayload.constraints) ? requestPayload.constraints : []
  return constraints.length
}

const reviewRequirement = (invocation) => {
  const reviewPolicy = getPolicySnapshot(invocation).review_policy || {}
  if (reviewPolicy.requires_judge) return '需要 judge'
  if (reviewPolicy.requires_reviewer || reviewPolicy.required) return '需要 reviewer'
  if (reviewPolicy.mode === 'judge') return 'Judge 能力'
  if (reviewPolicy.mode === 'reviewer') return 'Reviewer 能力'
  return ''
}

const knowledgeSummary = (invocation) => {
  const policy = getPolicySnapshot(invocation).knowledge_policy || {}
  const mode = String(policy.mode || policy.access || '').trim()
  if (!mode) return ''
  return mode
}

const childStatusSummary = (item) => {
  if (item?.childRun?.run?.status) return item.childRun.run.status
  const resultPayload = item?.invocation?.resultPayload || {}
  return resultPayload.status || ''
}

const resultSummary = (invocation) => {
  const resultPayload = invocation?.resultPayload || {}
  const finalResult = resultPayload.final_result || resultPayload.finalResult || {}
  const reviewResult = getInvocationReviewResult(invocation)
  const textualSummary = finalResult.summary || finalResult.final_output_text || finalResult.final_output || ''
  if (reviewResult.required || ['reviewer', 'judge'].includes(reviewResult.mode)) {
    if (textualSummary && textualSummary !== reviewResult.conclusion && textualSummary !== reviewResult.summary) {
      return textualSummary
    }
    return resultPayload.error || invocation?.errorMessage || ''
  }
  return reviewResult.conclusion || textualSummary || resultPayload.error || invocation?.errorMessage || ''
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
  max-height: 420px;
  overflow: auto;
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
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #64748b;
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono);
}

.invocation-task {
  margin-top: 12px;
  color: #475569;
  line-height: 1.6;
}

.fact-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.fact-card {
  border-radius: 14px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.8);
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

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}

.status-pill.queued {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.status-pill.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.status-pill.waiting_user {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.status-pill.completed {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.status-pill.failed,
.status-pill.cancelled {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.result-preview {
  margin-top: 12px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
  color: #334155;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
