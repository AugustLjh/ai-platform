<template>
  <section class="protocol-panel">
    <div class="panel-head">
      <div>
        <h3>父子协议</h3>
        <p>把 handoff task、约束、child question 和评审结论收口到同一视图中。</p>
      </div>
      <span class="panel-count">{{ entries.length }}</span>
    </div>

    <div v-if="entries.length === 0" class="empty-state">
      当前没有可展示的委派协议。
    </div>

    <div v-else class="protocol-list">
      <article v-for="entry in entries" :key="entry.id" class="protocol-card">
        <div class="protocol-head">
          <div>
            <div class="protocol-title">{{ entry.target }}</div>
            <div class="protocol-meta">
              <span v-if="entry.protocolVersion" class="mono">{{ entry.protocolVersion }}</span>
              <span v-if="entry.childRunId" class="mono">child {{ entry.childRunId.slice(0, 8) }}</span>
            </div>
          </div>
          <span :class="['status-pill', entry.status]">{{ entry.status }}</span>
        </div>

        <div v-if="entry.taskMessage" class="protocol-block">
          <span class="block-label">Handoff Task</span>
          <p>{{ entry.taskMessage }}</p>
        </div>

        <div v-if="entry.delegateReason" class="protocol-block muted-block">
          <span class="block-label">Delegate Reason</span>
          <p>{{ entry.delegateReason }}</p>
        </div>

        <div v-if="entry.question" class="protocol-block question-block">
          <span class="block-label">Child Waiting User</span>
          <p>{{ entry.question }}</p>
        </div>

        <div v-if="entry.constraints.length > 0" class="constraint-list">
          <span class="block-label">Constraints</span>
          <ul>
            <li v-for="constraint in entry.constraints" :key="constraint">{{ constraint }}</li>
          </ul>
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
import { buildInvocationProtocolEntry } from '@/utils/agentRunTree'

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

.protocol-block {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(240, 249, 255, 0.7);
}

.muted-block {
  background: rgba(248, 250, 252, 0.9);
}

.question-block {
  background: rgba(255, 251, 235, 0.9);
  border: 1px solid rgba(245, 158, 11, 0.18);
}

.block-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.protocol-block p {
  margin: 0;
  color: #334155;
  line-height: 1.6;
}

.constraint-list {
  margin-top: 12px;
}

.constraint-list ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #475569;
  display: grid;
  gap: 6px;
}
</style>
