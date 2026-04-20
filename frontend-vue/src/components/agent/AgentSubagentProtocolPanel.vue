<template>
  <section class="protocol-panel">
    <div class="panel-head">
      <div>
        <h3>父子协议</h3>
        <p>把 handoff task、约束、child question、治理限制和恢复语义收口到同一视图中。</p>
      </div>
      <span class="panel-count">{{ entries.length }}</span>
    </div>

    <div v-if="entries.length === 0" class="empty-state">
      当前没有可展示的委派协议。
    </div>

    <div v-else class="protocol-list">
      <article
        v-for="entry in entries"
        :key="entry.id"
        :class="['protocol-card', { attention: entry.needsAttention, danger: entry.attentionTone === 'danger' }]"
      >
        <div class="protocol-head">
          <div>
            <div class="protocol-title">{{ entry.target }}</div>
            <div class="protocol-meta">
              <span v-if="entry.protocolVersion" class="mono">{{ entry.protocolVersion }}</span>
              <span v-if="entry.childRunId" class="mono">child {{ entry.childRunId.slice(0, 8) }}</span>
            </div>
          </div>
          <span :class="['status-pill', entry.status, entry.attentionTone]">{{ entry.statusLabel }}</span>
        </div>

        <p v-if="entry.attentionSummary" class="protocol-attention">{{ entry.attentionSummary }}</p>

        <div v-if="entry.taskMessage" class="protocol-block">
          <span class="block-label">Handoff Task</span>
          <p>{{ entry.taskMessage }}</p>
        </div>

        <div v-if="entry.delegateReason" class="protocol-block muted-block">
          <span class="block-label">Delegate Reason</span>
          <p>{{ entry.delegateReason }}</p>
        </div>

        <div v-if="entry.progress.hasData" class="protocol-block progress-block">
          <div class="protocol-inline-head">
            <span class="block-label">Progress</span>
            <span :class="['mini-pill', `state-${entry.progress.state}`]">
              {{ progressStateLabel(entry.progress.state) }}
            </span>
          </div>
          <p v-if="entry.progress.summary">{{ entry.progress.summary }}</p>
          <div v-if="entry.progress.completedItems.length > 0" class="list-block">
            <span class="list-label">Completed</span>
            <ul>
              <li v-for="item in entry.progress.completedItems" :key="`done-${item}`">{{ item }}</li>
            </ul>
          </div>
          <div v-if="entry.progress.pendingItems.length > 0" class="list-block">
            <span class="list-label">Pending</span>
            <ul>
              <li v-for="item in entry.progress.pendingItems" :key="`pending-${item}`">{{ item }}</li>
            </ul>
          </div>
          <p v-if="entry.progress.nextAction" class="next-action">Next: {{ entry.progress.nextAction }}</p>
        </div>

        <div v-if="entry.clarification.hasData || entry.question" class="protocol-block question-block">
          <div class="protocol-inline-head">
            <span class="block-label">Clarification</span>
            <span :class="['mini-pill', `clarification-${entry.clarification.state || 'required'}`]">
              {{ clarificationStateLabel(entry.clarification.state || 'required') }}
            </span>
          </div>
          <p>{{ entry.clarification.question || entry.question }}</p>
          <p v-if="entry.clarification.reason" class="secondary-copy">{{ entry.clarification.reason }}</p>
          <div v-if="entry.clarification.requiredFields.length > 0" class="list-block">
            <span class="list-label">Required Fields</span>
            <ul>
              <li v-for="field in entry.clarification.requiredFields" :key="field">{{ field }}</li>
            </ul>
          </div>
          <p v-if="entry.clarification.responseHint" class="next-action">Hint: {{ entry.clarification.responseHint }}</p>
          <p v-if="entry.waitingUserPathSummary" class="secondary-copy">waiting-user 链路：{{ entry.waitingUserPathSummary }}</p>
        </div>

        <div v-if="entry.constraints.length > 0" class="constraint-list">
          <span class="block-label">Constraints</span>
          <ul>
            <li v-for="constraint in entry.constraints" :key="constraint">{{ constraint }}</li>
          </ul>
        </div>

        <div v-if="entry.governance.hasData" class="governance-block">
          <div class="protocol-inline-head">
            <span class="block-label">Governance</span>
            <span v-if="entry.governance.protocolVersion" class="mini-pill governance-pill">
              {{ entry.governance.protocolVersion }}
            </span>
          </div>
          <p v-if="entry.governanceSummary">{{ entry.governanceSummary }}</p>
          <div v-if="entry.governance.enforcement.hardLimits.length > 0" class="list-block">
            <span class="list-label">Hard Limits</span>
            <ul>
              <li v-for="limit in entry.governance.enforcement.hardLimits" :key="limit">{{ limit }}</li>
            </ul>
          </div>
          <div v-if="entry.governance.enforcement.advisoryLimits.length > 0" class="list-block">
            <span class="list-label">Advisory</span>
            <ul>
              <li v-for="limit in entry.governance.enforcement.advisoryLimits" :key="limit">{{ limit }}</li>
            </ul>
          </div>
          <div v-if="entry.governanceBudgetLines.length > 0" class="list-block">
            <span class="list-label">Budget Usage</span>
            <ul>
              <li v-for="line in entry.governanceBudgetLines" :key="line">{{ line }}</li>
            </ul>
          </div>
          <div v-if="entry.governance.history.attemptCount > 0" class="list-block">
            <span class="list-label">Observed History</span>
            <ul>
              <li>已尝试 {{ entry.governance.history.attemptCount }} 次</li>
              <li v-if="entry.governance.history.failedAttemptCount > 0">失败 {{ entry.governance.history.failedAttemptCount }} 次</li>
              <li v-if="entry.governance.history.activeChildCount > 0">未决 child {{ entry.governance.history.activeChildCount }} 个</li>
              <li v-if="entry.governance.history.waitingUserCount > 0">等待用户 {{ entry.governance.history.waitingUserCount }} 次</li>
            </ul>
          </div>
          <p v-if="entry.governance.waitingUserPropagation" class="secondary-copy">
            waiting-user 策略：{{ entry.governance.waitingUserPropagation }}
          </p>
          <p v-if="entry.recoverySummary" class="next-action">{{ entry.recoverySummary }}</p>
          <p v-if="entry.governance.enforcement.note" class="next-action">{{ entry.governance.enforcement.note }}</p>
        </div>

        <div class="protocol-foot">
          <span v-if="entry.reviewSummary">{{ entry.reviewSummary }}</span>
          <span v-if="entry.startedAt">开始 {{ formatTime(entry.startedAt) }}</span>
          <span v-if="entry.completedAt">结束 {{ formatTime(entry.completedAt) }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import {
  buildInvocationProtocolEntry,
  clarificationStateLabel,
  progressStateLabel
} from '@/utils/agentRunTree'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const entries = computed(() => props.items.map((item) => buildInvocationProtocolEntry(item)))

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
.protocol-panel {
  background: white;
  border: 1px solid rgba(14, 116, 144, 0.14);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
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
  background: rgba(14, 116, 144, 0.1);
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

.protocol-list {
  display: grid;
  gap: 14px;
}

.protocol-card {
  border-radius: 18px;
  border: 1px solid rgba(14, 116, 144, 0.12);
  background: linear-gradient(180deg, #f9fdff 0%, #ffffff 100%);
  padding: 16px;
}

.protocol-card.attention {
  border-color: rgba(245, 158, 11, 0.25);
}

.protocol-card.danger {
  border-color: rgba(239, 68, 68, 0.22);
  background: linear-gradient(180deg, #fffafa 0%, #ffffff 100%);
}

.protocol-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.protocol-title {
  font-weight: 700;
  color: #0f172a;
}

.protocol-meta,
.protocol-foot {
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

.protocol-attention {
  margin: 12px 0 0;
  color: #92400e;
  font-weight: 600;
  line-height: 1.6;
}

.protocol-block {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(14, 116, 144, 0.08);
}

.muted-block {
  background: rgba(248, 250, 252, 0.92);
}

.progress-block {
  background: rgba(236, 253, 245, 0.72);
  border-color: rgba(16, 185, 129, 0.16);
}

.question-block {
  background: rgba(255, 251, 235, 0.72);
  border-color: rgba(245, 158, 11, 0.18);
}

.governance-block {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.protocol-inline-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.block-label,
.list-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.protocol-block p,
.governance-block p {
  margin: 0;
  color: #334155;
  line-height: 1.7;
  white-space: pre-wrap;
}

.list-block {
  margin-top: 10px;
}

.list-block ul,
.constraint-list ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #334155;
  line-height: 1.7;
}

.constraint-list {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px dashed rgba(15, 23, 42, 0.12);
}

.secondary-copy,
.next-action {
  margin-top: 8px !important;
  color: #475569 !important;
  font-size: 13px;
}

.mini-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
}

.mini-pill.state-blocked,
.mini-pill.clarification-required {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.mini-pill.state-completed,
.mini-pill.clarification-resolved {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.mini-pill.state-in_progress,
.mini-pill.state-requested {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.mini-pill.state-failed {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.governance-pill {
  background: rgba(14, 116, 144, 0.1);
  color: #0f766e;
}
</style>
