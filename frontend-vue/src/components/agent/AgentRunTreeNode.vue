<template>
  <li class="tree-node">
    <article :class="['run-card', `depth-${node.depth || 0}`, { root: isRoot, attention: runView.hasNestedAttention }]">
      <div class="run-card-head">
        <div>
          <div class="run-label">{{ isRoot ? '主 Run' : `Child Run · 深度 ${node.depth}` }}</div>
          <h4>{{ runView.title }}</h4>
        </div>
        <span :class="['status-chip', run.status]">{{ runView.statusLabel }}</span>
      </div>

      <p v-if="runView.summary" class="run-summary">{{ runView.summary }}</p>

      <div class="run-meta">
        <span v-if="run.id" class="mono">#{{ run.id.slice(0, 8) }}</span>
        <span v-if="run.agentDefinitionId" class="mono">agent {{ run.agentDefinitionId.slice(0, 8) }}</span>
        <span v-if="run.updatedAt">{{ formatTime(run.updatedAt) }}</span>
        <span v-if="runView.childInvocationCount > 0">child {{ runView.childInvocationCount }} 个</span>
        <span v-if="runView.attentionChildCount > 0" class="attention-text">需关注 {{ runView.attentionChildCount }} 个</span>
      </div>
    </article>

    <ol v-if="visibleEdges.length" class="invocation-children">
      <li v-for="edge in visibleEdges" :key="edge.invocation.id" class="edge-item">
        <div :class="['edge-connector', { attention: edge.entry.needsAttention }]"></div>
        <article :class="['edge-card', { attention: edge.entry.needsAttention, collapsed: edge.isCollapsed }]">
          <div class="edge-head">
            <div class="edge-main">
              <strong>{{ edge.entry.target }}</strong>
              <p v-if="edge.entry.attentionSummary" class="edge-attention">{{ edge.entry.attentionSummary }}</p>
            </div>
            <span :class="['status-pill', edge.entry.status, edge.entry.attentionTone]">{{ edge.entry.statusLabel }}</span>
          </div>

          <p v-if="edge.entry.taskMessage" class="edge-task">
            {{ edge.entry.taskMessage }}
          </p>

          <div class="edge-facts">
            <span v-if="edge.entry.reviewSummary" class="fact-pill review">{{ edge.entry.reviewSummary }}</span>
            <span v-if="edge.entry.governanceSummary" class="fact-pill governance">{{ edge.entry.governanceSummary }}</span>
            <span v-if="edge.entry.waitingUserPathSummary" class="fact-pill warning">链路 {{ edge.entry.waitingUserPathSummary }}</span>
            <span v-if="edge.entry.recoverySummary" class="fact-pill muted">{{ edge.entry.recoverySummary }}</span>
          </div>

          <div class="edge-meta">
            <span v-if="edge.invocation.publicationId" class="mono">pub {{ edge.invocation.publicationId.slice(0, 8) }}</span>
            <span v-if="edge.entry.childRunId" class="mono">child {{ edge.entry.childRunId.slice(0, 8) }}</span>
          </div>

          <button
            v-if="edge.canCollapse"
            type="button"
            class="collapse-toggle"
            @click="toggleCollapsed(edge.invocation.id)"
          >
            {{ edge.isCollapsed ? '展开普通链路' : '收起普通链路' }}
          </button>
        </article>

        <ol v-if="edge.childRun && !edge.isCollapsed" class="child-list">
          <AgentRunTreeNode :node="edge.childRun" />
        </ol>
      </li>
    </ol>

    <button
      v-if="hiddenEdgeCount > 0"
      type="button"
      class="hidden-toggle"
      @click="showAllEdges = !showAllEdges"
    >
      {{ showAllEdges ? '收起普通链路' : `展开其余 ${hiddenEdgeCount} 条普通链路` }}
    </button>
  </li>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  buildInvocationProtocolEntry,
  buildRunTreeNodeView
} from '@/utils/agentRunTree'

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

const collapsedEdgeIds = ref(new Set())
const showAllEdges = ref(false)

const run = computed(() => props.node?.run || {})
const runView = computed(() => buildRunTreeNodeView(props.node || {}))

const normalizedEdges = computed(() => (
  (props.node?.invocations || []).map((edge) => {
    const entry = buildInvocationProtocolEntry({
      invocation: edge.invocation,
      childRun: edge.childRun,
      parentRun: run.value
    })
    return {
      ...edge,
      entry,
      canCollapse: !entry.needsAttention && Boolean(edge.childRun),
      isCollapsed: collapsedEdgeIds.value.has(edge.invocation.id)
    }
  })
))

const visibleEdges = computed(() => {
  if (showAllEdges.value) return normalizedEdges.value
  const attentionEdges = normalizedEdges.value.filter((edge) => edge.entry.needsAttention)
  const defaultEdges = normalizedEdges.value.filter((edge) => !edge.entry.needsAttention)
  return [...attentionEdges, ...defaultEdges.slice(0, 2)]
})

const hiddenEdgeCount = computed(() => Math.max(0, normalizedEdges.value.length - visibleEdges.value.length))

const toggleCollapsed = (id) => {
  const next = new Set(collapsedEdgeIds.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  collapsedEdgeIds.value = next
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

.run-card.attention {
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.18);
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
.edge-attention {
  margin-top: 10px;
  color: #475569;
  line-height: 1.6;
  word-break: break-word;
}

.edge-main {
  min-width: 0;
}

.edge-attention {
  margin-bottom: 0;
  color: #92400e;
  font-weight: 600;
}

.edge-facts,
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

.attention-text {
  color: #b45309;
  font-weight: 700;
}

.fact-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(148, 163, 184, 0.12);
  color: #334155;
  font-weight: 600;
}

.fact-pill.review {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.fact-pill.governance {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.fact-pill.warning {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.fact-pill.muted {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
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
.status-pill.queued,
.status-pill.pending {
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
.status-pill.cancelled,
.status-pill.danger {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.status-pill.warning {
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.24);
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

.edge-connector.attention {
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.45) 0%, rgba(245, 158, 11, 0.08) 100%);
}

.edge-card {
  background: linear-gradient(180deg, #fffef8 0%, #fff7ed 100%);
}

.edge-card.attention {
  border-color: rgba(245, 158, 11, 0.28);
}

.edge-card.collapsed {
  opacity: 0.92;
}

.collapse-toggle,
.hidden-toggle {
  justify-self: start;
  border: none;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-weight: 700;
  padding: 8px 12px;
  cursor: pointer;
}

.hidden-toggle {
  margin-left: 18px;
}
</style>
