<template>
  <div class="agent-page">
    <AgentPageHeader
      :agent-id="agent?.id || ''"
      kicker="Agent Runs"
      :title="agent?.name || '运行记录'"
      :description="agent?.description || '查看这个智能体的运行历史，并进入单次 run 详情。'"
    >
      <template #actions>
        <router-link v-if="agent?.id" :to="`/agents/${agent.id}`" class="btn btn-secondary">回到聊天</router-link>
        <button type="button" class="btn btn-primary" @click="reloadPage">刷新记录</button>
      </template>
    </AgentPageHeader>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">总运行数</span>
        <strong>{{ agentRuns.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">运行中</span>
        <strong>{{ activeRuns.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">等待补充</span>
        <strong>{{ waitingRuns.length }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">已完成</span>
        <strong>{{ completedRuns.length }}</strong>
      </article>
    </section>

    <section class="card">
      <div class="section-head">
        <div>
          <h2>运行历史</h2>
          <p>这里展示当前智能体的历史 runs。进入详情页后可查看步骤、工具调用与事件时间线。</p>
        </div>
      </div>

      <div v-if="agentRuns.length === 0" class="panel-empty">
        这个智能体还没有 run。先回到聊天页发起第一条消息。
      </div>

      <div v-else class="runs-list">
        <article v-for="run in agentRuns" :key="run.id" class="run-card">
          <div class="run-card-top">
            <div>
              <span :class="['status-pill', `status-${run.status}`]">{{ statusLabel(run.status) }}</span>
              <h3>{{ run.input?.message || run.input?.prompt || '无输入摘要' }}</h3>
            </div>
            <div class="run-meta">
              <span>{{ formatTime(run.updatedAt || run.createdAt) }}</span>
              <span class="mono">#{{ shortRunId(run.id) }}</span>
            </div>
          </div>

          <div class="run-facts">
            <span>会话 {{ run.sessionId || '未关联' }}</span>
            <span>创建于 {{ formatTime(run.createdAt) }}</span>
            <span v-if="run.finishedAt">结束于 {{ formatTime(run.finishedAt) }}</span>
          </div>

          <p v-if="runPreview(run)" class="run-preview">{{ trimPreview(runPreview(run)) }}</p>
          <p v-else-if="run.errorMessage" class="run-preview error">{{ trimPreview(run.errorMessage) }}</p>

          <div class="run-actions">
            <router-link :to="`/agents/runs/${run.id}`" class="btn btn-primary">查看详情</router-link>
            <router-link :to="`/agents/${run.agentDefinitionId}?session=${run.sessionId}`" class="btn btn-secondary">
              打开会话
            </router-link>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AgentPageHeader from '@/components/agent/AgentPageHeader.vue'
import { useAgentsStore } from '@/store/agents'
import { useToastStore } from '@/store/toast'
import { getRunAnswerText } from '@/utils/agentArtifacts'

const route = useRoute()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const agent = computed(() => agentsStore.currentAgent)
const agentRuns = computed(() => agentsStore.currentAgentRuns)
const errorMessage = computed(() => agentsStore.error || '')
const activeRuns = computed(() => agentRuns.value.filter((run) => ['queued', 'running'].includes(run.status)))
const waitingRuns = computed(() => agentRuns.value.filter((run) => run.status === 'waiting_user'))
const completedRuns = computed(() => agentRuns.value.filter((run) => run.status === 'completed'))

const loadPage = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) return

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchRuns()
  ])
}

const reloadPage = async () => {
  try {
    await loadPage()
    toastStore.showToast({ type: 'success', message: '运行记录已刷新' })
  } catch (error) {
    console.error('Failed to reload agent runs:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '刷新失败' })
  }
}

const statusLabel = (status) => {
  const mapping = {
    queued: '排队中',
    running: '运行中',
    waiting_user: '等待补充',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[status] || status || '未知状态'
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

const shortRunId = (runId) => String(runId || '').slice(0, 8)
const runPreview = (run) => getRunAnswerText(run || {})

const trimPreview = (value) => {
  const text = String(value || '').trim()
  if (text.length <= 180) {
    return text
  }
  return `${text.slice(0, 177)}...`
}

watch(() => route.params.id, async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to reload runs page:', error)
  }
})

onMounted(async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to load runs page:', error)
  }
})
</script>

<style scoped>
.agent-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  padding: 20px;
  border-radius: 24px;
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.1);
  box-shadow: var(--shadow-sm);
}

.summary-label {
  display: block;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
}

.summary-card strong {
  display: block;
  margin-top: 12px;
  font-size: 34px;
}

.card {
  background: white;
  border-radius: 28px;
  padding: 24px;
  border: 1px solid rgba(16, 163, 127, 0.1);
  box-shadow: var(--shadow-sm);
}

.section-head h2 {
  font-size: 22px;
}

.section-head p {
  margin-top: 6px;
  color: var(--gray-600);
}

.error-banner {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.panel-empty {
  margin-top: 18px;
  color: var(--gray-500);
}

.runs-list {
  margin-top: 20px;
  display: grid;
  gap: 16px;
}

.run-card {
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.8);
}

.run-card-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.run-card-top h3 {
  margin-top: 12px;
  font-size: 18px;
  color: var(--gray-900);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.status-queued {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.status-running {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.status-waiting_user {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.status-completed {
  background: rgba(13, 148, 136, 0.12);
  color: #0f766e;
}

.status-failed,
.status-cancelled {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.run-meta {
  display: grid;
  gap: 6px;
  justify-items: end;
  color: var(--gray-500);
  font-size: 13px;
}

.run-facts {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  color: var(--gray-600);
  font-size: 13px;
}

.run-preview {
  margin-top: 14px;
  color: var(--gray-700);
  line-height: 1.6;
}

.run-preview.error {
  color: #b91c1c;
}

.run-actions {
  margin-top: 18px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

@media (max-width: 1100px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 780px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .run-card-top {
    flex-direction: column;
  }

  .run-meta {
    justify-items: start;
  }
}
</style>
