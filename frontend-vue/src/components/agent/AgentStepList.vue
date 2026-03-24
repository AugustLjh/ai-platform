<template>
  <section class="step-panel">
    <div class="panel-head">
      <div>
        <h3>执行步骤</h3>
        <p>按 step 维度查看 planner 与工具执行情况。</p>
      </div>
      <span class="panel-count">{{ steps.length }}</span>
    </div>

    <div v-if="steps.length === 0" class="empty-state">
      这个 run 还没有生成步骤。
    </div>

    <div v-else class="step-list">
      <article v-for="step in steps" :key="step.id" class="step-card">
        <div class="step-card-head">
          <div>
            <div class="step-index">STEP {{ step.stepIndex || '?' }}</div>
            <h4>{{ step.title || step.kind || '未命名步骤' }}</h4>
          </div>
          <span :class="['step-status', step.status]">{{ statusLabel(step.status) }}</span>
        </div>

        <p class="step-kind">{{ step.kind || 'unknown' }}</p>

        <div v-if="step.question" class="step-question">
          {{ step.question }}
        </div>

        <div v-if="step.output" class="step-output">
          <div class="step-output-label">输出</div>
          <pre>{{ formatJSON(step.output) }}</pre>
        </div>

        <div v-if="toolCallsByStep(step.id).length > 0" class="tool-call-list">
          <AgentToolCallCard
            v-for="toolCall in toolCallsByStep(step.id)"
            :key="toolCall.id"
            :tool-call="toolCall"
          />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import AgentToolCallCard from './AgentToolCallCard.vue'

const props = defineProps({
  steps: {
    type: Array,
    default: () => []
  },
  toolCalls: {
    type: Array,
    default: () => []
  }
})

const statusMap = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}

const statusLabel = (status) => statusMap[status] || status || '未知'
const formatJSON = (value) => JSON.stringify(value || {}, null, 2)
const toolCallsByStep = (stepId) => props.toolCalls.filter((toolCall) => toolCall.stepId === stepId)
</script>

<style scoped>
.step-panel {
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.14);
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
  font-size: 18px;
  margin: 0 0 6px;
}

.panel-head p {
  color: var(--gray-600);
  font-size: 14px;
}

.panel-count {
  min-width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
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

.step-list {
  display: grid;
  gap: 16px;
}

.step-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
}

.step-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.step-index {
  font-size: 11px;
  letter-spacing: 0.08em;
  font-weight: 700;
  color: var(--primary-700);
}

.step-card h4 {
  font-size: 17px;
  margin-top: 4px;
}

.step-status {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.step-status.pending {
  background: var(--gray-100);
  color: var(--gray-700);
}

.step-status.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.step-status.completed {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.step-status.failed,
.step-status.cancelled {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.step-kind {
  margin-top: 10px;
  color: var(--gray-500);
  font-size: 13px;
}

.step-question {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: rgba(245, 158, 11, 0.12);
  color: #92400e;
  font-size: 14px;
}

.step-output {
  margin-top: 14px;
}

.step-output-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--gray-600);
  margin-bottom: 8px;
}

pre {
  margin: 0;
  padding: 12px;
  border-radius: var(--radius-md);
  background: rgba(13, 13, 13, 0.04);
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  font-family: var(--font-mono);
}

.tool-call-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}
</style>
