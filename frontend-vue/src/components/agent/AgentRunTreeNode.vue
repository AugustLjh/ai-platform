<template>
  <li class="tree-node">
    <article :class="['run-card', `depth-${node.depth || 0}`, { root: isRoot }]">
      <div class="run-card-head">
        <div>
          <div class="run-label">{{ isRoot ? '主 Run' : `Child Run · 深度 ${node.depth}` }}</div>
          <h4>{{ runTitle }}</h4>
        </div>
        <span :class="['status-chip', run.status]">{{ statusLabel }}</span>
      </div>

      <p v-if="runSummary" class="run-summary">{{ runSummary }}</p>

      <div class="run-meta">
        <span v-if="run.id" class="mono">#{{ run.id.slice(0, 8) }}</span>
        <span v-if="run.agentDefinitionId" class="mono">agent {{ run.agentDefinitionId.slice(0, 8) }}</span>
        <span v-if="run.updatedAt">{{ formatTime(run.updatedAt) }}</span>
      </div>
    </article>

    <ol v-if="node.invocations?.length" class="invocation-children">
      <li v-for="edge in node.invocations" :key="edge.invocation.id" class="edge-item">
        <div class="edge-connector"></div>
        <article class="edge-card">
          <div class="edge-head">
            <strong>{{ summarizeInvocationTarget(edge.invocation) }}</strong>
            <span :class="['status-pill', edge.invocation.status]">{{ edge.invocation.status }}</span>
          </div>
          <p v-if="summarizeInvocationTask(edge.invocation)" class="edge-task">
            {{ summarizeInvocationTask(edge.invocation) }}
          </p>
          <p v-if="summarizeInvocationReview(edge.invocation)" class="edge-review">
            {{ summarizeInvocationReview(edge.invocation) }}
          </p>
          <div class="edge-meta">
            <span v-if="edge.invocation.publicationId" class="mono">pub {{ edge.invocation.publicationId.slice(0, 8) }}</span>
            <span v-if="edge.invocation.childRunId" class="mono">child {{ edge.invocation.childRunId.slice(0, 8) }}</span>
          </div>
        </article>

        <ol v-if="edge.childRun" class="child-list">
          <AgentRunTreeNode :node="edge.childRun" />
        </ol>
      </li>
    </ol>
  </li>
</template>

<script setup>
import { computed } from 'vue'
import { summarizeInvocationReview, summarizeInvocationTarget, summarizeInvocationTask } from '@/utils/agentRunTree'

defineOptions({
  name: 'AgentRunTreeNode'
})

const props = defineProps({
  node: {
    type: Object,
    required: true
  },
  isRoot: {
    type: Boolean,
    default: false
  }
})

const statusMap = {
  queued: '排队中',
  running: '运行中',
  waiting_user: '等待补充',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消'
}

const run = computed(() => props.node?.run || {})

const runTitle = computed(() => {
  const input = run.value?.input || {}
  return input.message || input.prompt || run.value?.finalOutputText || '未命名运行'
})

const runSummary = computed(() => {
  if (run.value?.status === 'failed') {
    return run.value?.errorMessage || '子任务执行失败。'
  }
  if (run.value?.status === 'waiting_user') {
    return run.value?.finalOutputText || '子任务暂停，等待父 run 转译后继续。'
  }
  return run.value?.finalOutputText || ''
})

const statusLabel = computed(() => statusMap[run.value?.status] || run.value?.status || '未知状态')

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
.tree-node {
  list-style: none;
  display: grid;
  gap: 12px;
}

.run-card,
.edge-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 14px 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.run-card.root {
  background: linear-gradient(180deg, #f5fffb 0%, #ecfdf5 100%);
  border-color: rgba(16, 163, 127, 0.2);
}

.run-card-head,
.edge-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.run-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-weight: 700;
  color: #0f766e;
  margin-bottom: 6px;
}

.run-card h4 {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
  color: #0f172a;
}

.run-summary,
.edge-task,
.edge-review {
  margin-top: 10px;
  color: #475569;
  line-height: 1.6;
  word-break: break-word;
}

.edge-review {
  color: #0f766e;
  font-weight: 600;
}

.run-meta,
.edge-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 10px;
  font-size: 12px;
  color: #64748b;
}

.mono {
  font-family: var(--font-mono);
}

.status-chip,
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

.status-chip.queued,
.status-pill.queued {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.status-chip.running,
.status-pill.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.status-chip.waiting_user,
.status-pill.waiting_user {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.status-chip.completed,
.status-pill.completed {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.status-chip.failed,
.status-pill.failed,
.status-chip.cancelled,
.status-pill.cancelled {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.invocation-children,
.child-list {
  list-style: none;
  display: grid;
  gap: 12px;
  margin-left: 18px;
}

.edge-item {
  display: grid;
  gap: 12px;
}

.edge-connector {
  width: 2px;
  min-height: 12px;
  margin-left: 14px;
  background: linear-gradient(180deg, rgba(16, 163, 127, 0.35) 0%, rgba(16, 163, 127, 0.08) 100%);
}

.edge-card {
  background: linear-gradient(180deg, #fffef8 0%, #fff7ed 100%);
  border-color: rgba(245, 158, 11, 0.22);
}
</style>
