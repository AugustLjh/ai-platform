<template>
  <section class="plan-panel">
    <div class="panel-head">
      <div>
        <h3>执行计划</h3>
        <p>展示 planner 当前生成的结构化动作。</p>
      </div>
      <span class="panel-badge">{{ actionType }}</span>
    </div>

    <div v-if="!plan" class="empty-state">
      planner 尚未生成计划。
    </div>

    <template v-else>
      <div class="plan-card">
        <div class="plan-label">Action</div>
        <div class="plan-action">
          <strong>{{ plan.action?.title || '未命名动作' }}</strong>
          <span>{{ plan.action?.type || 'unknown' }}</span>
        </div>
      </div>

      <div v-if="plan.reasoning" class="plan-card">
        <div class="plan-label">Reasoning</div>
        <p>{{ plan.reasoning }}</p>
      </div>

      <div v-if="plan.action?.content" class="plan-card">
        <div class="plan-label">Content</div>
        <p>{{ plan.action.content }}</p>
      </div>

      <div v-if="plan.action?.question" class="plan-card">
        <div class="plan-label">Question</div>
        <p>{{ plan.action.question }}</p>
      </div>

      <div v-if="plan.action?.tool_name" class="plan-card">
        <div class="plan-label">Tool</div>
        <p>{{ plan.action.tool_name }}</p>
        <pre>{{ JSON.stringify(plan.action.tool_arguments || {}, null, 2) }}</pre>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  plan: {
    type: Object,
    default: null
  }
})

const actionType = computed(() => props.plan?.action?.type || '未生成')
</script>

<style scoped>
.plan-panel {
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.14);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
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

.panel-badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
  font-size: 12px;
  font-weight: 700;
}

.empty-state {
  padding: 20px;
  border-radius: var(--radius-lg);
  background: var(--gray-50);
  color: var(--gray-500);
  text-align: center;
}

.plan-card {
  border: 1px solid var(--gray-200);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcfb 100%);
}

.plan-card + .plan-card {
  margin-top: 12px;
}

.plan-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
  font-weight: 700;
  margin-bottom: 8px;
}

.plan-action {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.plan-action strong {
  color: var(--gray-900);
}

.plan-action span,
.plan-card p {
  color: var(--gray-700);
}

pre {
  margin-top: 10px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: rgba(13, 13, 13, 0.04);
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  font-family: var(--font-mono);
}
</style>
