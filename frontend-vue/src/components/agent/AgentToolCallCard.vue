<template>
  <article class="tool-card">
    <div class="tool-card-head">
      <div>
        <div class="tool-name">{{ toolCall.toolName }}</div>
        <div class="tool-meta">
          <span>{{ toolKindLabel }}</span>
          <span>调用于 {{ formatTime(toolCall.updatedAt || toolCall.createdAt) }}</span>
        </div>
      </div>
      <span :class="['tool-status', toolCall.status]">{{ statusLabel }}</span>
    </div>

    <div v-if="hasArguments" class="tool-section">
      <div class="tool-section-label">参数</div>
      <pre>{{ formattedArguments }}</pre>
    </div>

    <div v-if="hasResult" class="tool-section">
      <div class="tool-section-label">结果</div>
      <AgentToolResultPreview :result="toolCall.result" :tool-call="toolCall" />
    </div>

    <div v-if="hasError" class="tool-section">
      <div class="tool-section-label">错误</div>
      <pre>{{ toolCall.error }}</pre>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import AgentToolResultPreview from './AgentToolResultPreview.vue'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const statusMap = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}

const statusLabel = computed(() => statusMap[props.toolCall.status] || props.toolCall.status || '未知')
const toolKindLabel = computed(() => {
  if (props.toolCall.toolKind === 'mcp') return 'MCP Tool'
  if (props.toolCall.toolKind === 'knowledge') return 'Knowledge Tool'
  return 'Builtin Tool'
})
const formattedArguments = computed(() => JSON.stringify(props.toolCall.arguments || {}, null, 2))
const hasArguments = computed(() => Object.keys(props.toolCall.arguments || {}).length > 0)
const hasResult = computed(() => props.toolCall.result && Object.keys(props.toolCall.result).length > 0)
const hasError = computed(() => !!props.toolCall.error)

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
.tool-card {
  border: 1px solid rgba(12, 123, 97, 0.12);
  background: linear-gradient(180deg, #ffffff 0%, #f6fbf9 100%);
  border-radius: var(--radius-lg);
  padding: 16px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.tool-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.tool-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--gray-900);
  word-break: break-word;
  overflow-wrap: anywhere;
}

.tool-meta {
  font-size: 12px;
  color: var(--gray-500);
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tool-status {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.tool-status.pending {
  background: var(--gray-100);
  color: var(--gray-700);
}

.tool-status.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.tool-status.completed {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.tool-status.failed {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.tool-status.cancelled {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.tool-section {
  margin-top: 14px;
}

.tool-section-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--gray-600);
  text-transform: uppercase;
  margin-bottom: 8px;
}

pre {
  margin: 0;
  padding: 12px;
  border-radius: var(--radius-md);
  background: rgba(13, 13, 13, 0.04);
  color: var(--gray-800);
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
}
</style>
