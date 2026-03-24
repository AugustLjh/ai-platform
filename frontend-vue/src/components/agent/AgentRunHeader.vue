<template>
  <section class="run-header">
    <div class="run-header-main">
      <div class="run-kicker">Agent Run</div>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
      <div class="run-meta">
        <span :class="['status-chip', run?.status]">{{ statusLabel }}</span>
        <span v-if="run?.createdAt">创建于 {{ formatTime(run.createdAt) }}</span>
        <span v-if="run?.updatedAt">更新于 {{ formatTime(run.updatedAt) }}</span>
      </div>
    </div>

    <div class="run-header-actions">
      <button type="button" class="btn btn-secondary" @click="$emit('refresh')">刷新</button>
      <button
        v-if="canResume"
        type="button"
        class="btn btn-primary"
        @click="$emit('resume')"
      >
        继续执行
      </button>
      <button
        v-if="canCancel"
        type="button"
        class="btn btn-danger"
        @click="$emit('cancel')"
      >
        取消运行
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  run: {
    type: Object,
    default: null
  },
  agentName: {
    type: String,
    default: ''
  }
})

defineEmits(['refresh', 'cancel', 'resume'])

const statusMap = {
  queued: '排队中',
  running: '运行中',
  waiting_user: '等待用户输入',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}

const title = computed(() => props.agentName || '智能体运行详情')
const subtitle = computed(() => props.run?.input?.message || props.run?.input?.prompt || '查看运行过程、步骤与工具调用明细。')
const statusLabel = computed(() => statusMap[props.run?.status] || props.run?.status || '未知状态')
const canCancel = computed(() => ['queued', 'running'].includes(props.run?.status))
const canResume = computed(() => ['waiting_user', 'failed', 'cancelled'].includes(props.run?.status))

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
.run-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(110, 231, 183, 0.35) 0%, rgba(110, 231, 183, 0) 32%),
    linear-gradient(135deg, #0f172a 0%, #124d42 100%);
  color: white;
  box-shadow: var(--shadow-lg);
}

.run-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
  margin-bottom: 10px;
}

.run-header h1 {
  font-size: 30px;
  line-height: 1.1;
}

.run-header p {
  margin-top: 10px;
  max-width: 760px;
  color: rgba(255, 255, 255, 0.8);
}

.run-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-top: 16px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.78);
}

.status-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.18);
  color: white;
  font-weight: 700;
}

.run-header-actions {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.run-header-actions .btn-primary {
  background: white;
  color: var(--primary-700);
}

.run-header-actions .btn-secondary {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.run-header-actions .btn-danger {
  background: rgba(127, 29, 29, 0.92);
}

@media (max-width: 900px) {
  .run-header {
    flex-direction: column;
  }
}
</style>
