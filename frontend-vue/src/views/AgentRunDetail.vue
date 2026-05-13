<template>
  <div class="agent-chat-page">
    <header class="chat-topbar">
      <div class="topbar-main">
        <router-link :to="workspaceLink" class="back-link">返回智能体会话</router-link>
        <div class="topbar-copy">
          <div class="topbar-kicker">Agent Session</div>
          <h1>{{ agent?.name || '智能体会话' }}</h1>
          <p>{{ topbarSummary }}</p>
        </div>
      </div>

      <div class="topbar-side">
        <span :class="['status-chip', run?.status]">{{ statusLabel }}</span>
        <div class="topbar-meta">
          <span v-if="run?.updatedAt">更新于 {{ formatTime(run.updatedAt) }}</span>
          <span v-if="run?.id" class="mono">#{{ shortRunId }}</span>
        </div>
        <div class="topbar-actions">
          <button type="button" class="btn btn-secondary" @click="refreshRun">刷新</button>
          <button
            v-if="canCancel"
            type="button"
            class="btn btn-danger"
            @click="cancelRun"
          >
            停止运行
          </button>
        </div>
      </div>
    </header>

    <div v-if="showGlobalError" class="error-banner">
      {{ errorMessage }}
    </div>

    <section :class="['workspace-status-card', { muted: !workspaceBound }]">
      <div>
        <div class="workspace-kicker">Workspace</div>
        <h2>{{ workspaceTitle }}</h2>
        <p>{{ workspaceDescription }}</p>
      </div>
      <div v-if="workspaceBound" class="workspace-meta-grid">
        <span>来源 {{ workspaceSourceLabel }}</span>
        <span>文件 {{ workspaceSnapshot?.file_count ?? 0 }}</span>
        <span>大小 {{ formatBytes(workspaceSnapshot?.total_size_bytes) }}</span>
        <span>快照 {{ workspaceSnapshotTime }}</span>
      </div>
      <div v-else class="workspace-recovery">
        <span>当前降级为 project-context/上传文件问答。</span>
        <router-link v-if="run?.agentDefinitionId" :to="workspaceLink" class="workspace-link">返回会话绑定项目</router-link>
      </div>
    </section>

    <section class="chat-stage">
      <div ref="threadRef" class="chat-thread">
        <div v-if="currentPrompt" class="message-row user">
          <article class="message-card user-card">
            <div class="message-head">
              <span class="message-role">你</span>
              <span v-if="run?.createdAt" class="message-time">{{ formatTime(run.createdAt) }}</span>
            </div>
            <div class="user-bubble">
              <div class="plain-text">{{ currentPrompt }}</div>
            </div>
          </article>
        </div>

        <div v-if="hasAssistantBubble" class="message-row assistant">
          <article :class="['message-card', 'assistant-card', assistantToneClass]">
            <div class="message-head">
              <span class="message-role">{{ assistantTitle }}</span>
              <span v-if="run?.updatedAt" class="message-time">{{ formatTime(run.updatedAt) }}</span>
            </div>

            <div v-if="showStreamingBubble" class="assistant-streaming">
              <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <div class="streaming-copy">
                <strong>{{ streamingTitle }}</strong>
                <p>{{ streamingDescription }}</p>
              </div>
            </div>

            <div
              v-else-if="assistantUsesMarkdown"
              class="markdown agent-markdown"
              v-html="assistantHtml"
            ></div>

            <pre v-else class="plain-text plain-pre">{{ assistantContent }}</pre>
          </article>
        </div>

        <div v-if="showDetailHint" class="message-row assistant detail-row">
          <button
            type="button"
            class="detail-toggle"
            @click="detailsOpen = !detailsOpen"
          >
            <span>执行细节</span>
            <span>{{ steps.length }} 步 · {{ toolCalls.length }} 次工具 · {{ runTreeInvocations.length }} 次委派 · {{ runEvents.length }} 个事件</span>
          </button>
        </div>

        <div v-if="showSubagentClarification" class="message-row assistant">
          <AgentSubagentClarificationCard :run="run" />
        </div>

        <div v-if="showStructuredSurface" class="message-row assistant detail-row">
          <button
            type="button"
            class="detail-toggle surface-toggle"
            @click="surfaceOpen = !surfaceOpen"
          >
            <span>结构化结果</span>
            <span>{{ surfaceOpen ? '点击收起结果面板' : `默认收起 · ${structuredResultCount} 个结果面板` }}</span>
          </button>
        </div>

        <div v-if="showStructuredSurface && surfaceOpen" class="result-surface">
          <AgentArtifactPanel
            :artifacts="surfaceArtifacts"
            :final-output-json="surfaceOutputJson"
            :surface-meta="executionSurface"
          />
        </div>
      </div>

      <footer class="composer-shell">
        <template v-if="canResume">
          <div class="composer-copy">
            <strong>{{ composerTitle }}</strong>
            <span>{{ composerDescription }}</span>
          </div>

          <form class="composer-form" @submit.prevent="resumeRun">
            <textarea
              v-model="resumeMessage"
              class="composer-input"
              rows="1"
              :placeholder="composerPlaceholder"
            ></textarea>

            <button
              type="submit"
              class="btn btn-primary composer-submit"
              :disabled="resumeLoading"
            >
              {{ resumeLoading ? '发送中...' : '发送并继续' }}
            </button>
          </form>
        </template>

        <template v-else>
          <div class="composer-copy">
            <strong>{{ readOnlyTitle }}</strong>
            <span>{{ readOnlyDescription }}</span>
          </div>

          <div class="composer-actions-readonly">
            <router-link :to="workspaceLink" class="btn btn-secondary">返回智能体会话</router-link>
            <button
              v-if="canCancel"
              type="button"
              class="btn btn-danger"
              @click="cancelRun"
            >
              停止运行
            </button>
          </div>
        </template>
      </footer>
    </section>

    <section v-if="showDetailHint && detailsOpen" class="details-panel">
      <div class="details-panel-head">
        <div>
          <h2>执行细节</h2>
          <p>默认收起，仅在需要排查运行过程时展开查看。</p>
        </div>
        <button type="button" class="details-close" @click="detailsOpen = false">收起</button>
      </div>

      <div class="details-grid">
        <AgentArtifactPanel
          :artifacts="artifacts"
          :final-output-json="run?.finalOutputJson"
          :surface-meta="executionSurface"
        />
        <AgentPlanPanel :plan="plan" />
      </div>
      <AgentRunTree v-if="currentRunTree" :root="currentRunTree" />
      <AgentSubagentProtocolPanel v-if="runTreeInvocations.length > 0" :items="runTreeInvocations" />
      <AgentSubagentInvocationPanel v-if="runTreeInvocations.length > 0" :items="runTreeInvocations" />
      <AgentTimeline :events="runEvents" />
      <AgentStepList :steps="steps" :tool-calls="toolCalls" />
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentArtifactPanel from '@/components/agent/AgentArtifactPanel.vue'
import AgentPlanPanel from '@/components/agent/AgentPlanPanel.vue'
import AgentStepList from '@/components/agent/AgentStepList.vue'
import AgentTimeline from '@/components/agent/AgentTimeline.vue'
import AgentRunTree from '@/components/agent/AgentRunTree.vue'
import AgentSubagentProtocolPanel from '@/components/agent/AgentSubagentProtocolPanel.vue'
import AgentSubagentInvocationPanel from '@/components/agent/AgentSubagentInvocationPanel.vue'
import AgentSubagentClarificationCard from '@/components/agent/AgentSubagentClarificationCard.vue'
import { useAgentsStore } from '@/store/agents'
import { useToastStore } from '@/store/toast'
import { getRunAnswerText } from '@/utils/agentArtifacts'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const resumeMessage = ref('')
const resumeLoading = ref(false)
const detailsOpen = ref(false)
const surfaceOpen = ref(false)
const threadRef = ref(null)

const run = computed(() => agentsStore.currentRun)
const agent = computed(() => agentsStore.currentAgent)
const runEvents = computed(() => agentsStore.runEvents)
const steps = computed(() => agentsStore.steps)
const toolCalls = computed(() => agentsStore.toolCalls)
const plan = computed(() => agentsStore.plan)
const artifacts = computed(() => agentsStore.artifacts)
const executionSurface = computed(() => agentsStore.executionSurface)
const currentRunTree = computed(() => agentsStore.currentRunTree)
const runTreeInvocations = computed(() => agentsStore.currentRunInvocations)
const errorMessage = computed(() => agentsStore.error || '')

const statusMap = {
  queued: '排队中',
  running: '运行中',
  waiting_user: '等待补充',
  completed: '已完成',
  failed: '运行失败',
  cancelled: '已取消'
}

const currentPrompt = computed(() => run.value?.input?.message || run.value?.input?.prompt || '')
const workspaceLink = computed(() => run.value?.agentDefinitionId ? `/agents/${run.value.agentDefinitionId}` : '/agents')
const shortRunId = computed(() => (run.value?.id || '').slice(0, 8))
const statusLabel = computed(() => statusMap[run.value?.status] || run.value?.status || '未知状态')
const canCancel = computed(() => ['queued', 'running'].includes(run.value?.status))
const canResume = computed(() => ['waiting_user', 'failed', 'cancelled'].includes(run.value?.status))
const showGlobalError = computed(() => Boolean(errorMessage.value) && run.value?.status !== 'failed')
const workspaceContext = computed(() => {
  const context = run.value?.context || {}
  const fromContext = context.workspace && typeof context.workspace === 'object' ? context.workspace : null
  if (fromContext) return fromContext
  const artifact = artifacts.value.find((item) => item.artifactType === 'workspace_summary')
  return artifact?.payload && typeof artifact.payload === 'object' ? artifact.payload : null
})
const workspaceBound = computed(() => Boolean(workspaceContext.value?.root || workspaceContext.value?.id))
const workspaceSnapshot = computed(() => workspaceContext.value?.snapshot || null)
const workspaceTitle = computed(() => workspaceBound.value ? '已绑定隔离 workspace' : '未绑定 workspace')
const workspaceDescription = computed(() => {
  if (!workspaceBound.value) {
    return '只读代码、Git diff 和项目文件引用工具当前不可用。'
  }
  const source = workspaceSourceLabel.value
  return `${source} 已进入当前 run 的受控 workspace，文件读取和 Git 结果会作为可复盘 artifact 展示。`
})
const workspaceSourceLabel = computed(() => {
  const source = workspaceContext.value?.source || {}
  const type = String(source.type || '').trim()
  if (type === 'upload_bundle') return '上传文件包'
  if (type === 'local_path') return '项目副本'
  if (type === 'existing') return '已登记项目目录'
  return type || '未记录'
})
const workspaceSnapshotTime = computed(() => {
  const value = workspaceSnapshot.value?.snapshot_at
  return value ? formatTime(value) : '未生成'
})
const showDetailHint = computed(() => (
  steps.value.length > 0 ||
  toolCalls.value.length > 0 ||
  runEvents.value.length > 0 ||
  Boolean(plan.value) ||
  artifacts.value.length > 0 ||
  Boolean(run.value?.finalOutputJson) ||
  Boolean(currentRunTree.value?.invocations?.length)
))
const surfaceArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType !== 'answer'))
const surfaceOutputJson = computed(() => surfaceArtifacts.value.length > 0 ? null : run.value?.finalOutputJson || null)
const showStructuredSurface = computed(() => surfaceArtifacts.value.length > 0 || Boolean(surfaceOutputJson.value))
const structuredResultCount = computed(() => surfaceArtifacts.value.length + (surfaceOutputJson.value ? 1 : 0))
const showSubagentClarification = computed(() => Boolean(
  run.value?.status === 'waiting_user' &&
  run.value?.context &&
  (run.value.context.pending_subagent_clarification || run.value.context.pendingSubagentClarification)
))

const topbarSummary = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return '智能体已暂停，等待你补充消息后继续执行。'
  }
  if (run.value?.status === 'running' || run.value?.status === 'queued') {
    return '当前会话正在执行，主视图只保留对话内容，过程细节按需展开。'
  }
  if (run.value?.status === 'completed') {
    return '运行完成，当前页按聊天线程展示输入与最终回复。'
  }
  if (run.value?.status === 'failed') {
    return '运行中断，你可以在底部补充信息或直接重试。'
  }
  if (run.value?.status === 'cancelled') {
    return '运行已停止，可以在底部补充输入后继续。'
  }
  return '查看当前智能体会话。'
})

const activeStep = computed(() => (
  steps.value.find((step) => step.status === 'running') ||
  steps.value[steps.value.length - 1] ||
  null
))

const streamingTitle = computed(() => {
  if (run.value?.status === 'queued') {
    return '正在排队'
  }
  return '智能体正在处理中'
})

const streamingDescription = computed(() => {
  if (run.value?.status === 'queued') {
    return '请求已提交，正在等待开始执行。'
  }
  if (activeStep.value?.title) {
    return `当前阶段：${activeStep.value.title}`
  }
  if (activeStep.value?.kind) {
    return `当前阶段：${activeStep.value.kind}`
  }
  return '正在分析问题并生成回复。'
})

const assistantContent = computed(() => {
  const answer = getRunAnswerText(run.value || {})
  if (answer) {
    return answer
  }
  if (run.value?.status === 'failed') {
    return run.value?.errorMessage || '运行失败，请补充输入后重试。'
  }
  if (run.value?.status === 'cancelled') {
    return run.value?.errorMessage || '运行已取消。'
  }
  return ''
})

const assistantUsesMarkdown = computed(() => Boolean(run.value?.finalOutputText || run.value?.finalOutput))
const assistantHtml = computed(() => renderMarkdown(assistantContent.value || ''))
const showStreamingBubble = computed(() => ['queued', 'running'].includes(run.value?.status) && !assistantContent.value)
const hasAssistantBubble = computed(() => showStreamingBubble.value || Boolean(assistantContent.value))

const assistantTitle = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return '智能体提问'
  }
  if (run.value?.status === 'failed') {
    return '运行错误'
  }
  if (run.value?.status === 'cancelled') {
    return '运行状态'
  }
  return agent.value?.name || '智能体'
})

const assistantToneClass = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return 'tone-question'
  }
  if (run.value?.status === 'failed') {
    return 'tone-error'
  }
  if (run.value?.status === 'cancelled') {
    return 'tone-muted'
  }
  return 'tone-default'
})

const composerTitle = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return '补充消息'
  }
  if (run.value?.status === 'failed') {
    return '重试运行'
  }
  return '继续运行'
})

const composerDescription = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return '像聊天一样补充上下文，发送后会在当前 run 内继续执行。'
  }
  if (run.value?.status === 'failed') {
    return '可以补充说明后继续，也可以直接留空重试当前 run。'
  }
  return '补充一条消息后继续当前 run。'
})

const composerPlaceholder = computed(() => {
  if (run.value?.status === 'waiting_user') {
    return '输入补充信息...'
  }
  if (run.value?.status === 'failed') {
    return '可选：补充错误上下文或修正要求'
  }
  return '可选：输入新的补充消息'
})

const readOnlyTitle = computed(() => {
  if (run.value?.status === 'completed') {
    return '当前运行已完成'
  }
  if (run.value?.status === 'running' || run.value?.status === 'queued') {
    return '当前运行进行中'
  }
  return '当前运行不可继续输入'
})

const readOnlyDescription = computed(() => {
  if (run.value?.status === 'completed') {
    return '如需继续追问，请返回智能体会话开始新的运行。'
  }
  if (run.value?.status === 'running' || run.value?.status === 'queued') {
    return '等待智能体完成当前请求，必要时可手动停止运行。'
  }
  return '返回智能体会话发起新的请求。'
})

const loadRun = async () => {
  const runId = String(route.params.run_id || '')
  if (!runId) {
    router.push('/agents')
    return
  }

  surfaceOpen.value = false
  const currentRun = await agentsStore.openRun(runId, { stream: true })
  if (currentRun?.agentDefinitionId) {
    await agentsStore.fetchAgent(currentRun.agentDefinitionId)
  }
}

const scrollThreadToBottom = async () => {
  await nextTick()
  if (!threadRef.value) return
  threadRef.value.scrollTop = threadRef.value.scrollHeight
}

const refreshRun = async () => {
  try {
    await loadRun()
    toastStore.showToast({ type: 'success', message: '运行状态已刷新' })
  } catch (error) {
    console.error('Failed to refresh run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '刷新运行失败' })
  }
}

const cancelRun = async () => {
  if (!run.value?.id) return
  try {
    await agentsStore.cancelRun(run.value.id)
    toastStore.showToast({ type: 'success', message: '运行已停止' })
  } catch (error) {
    console.error('Failed to cancel run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '停止运行失败' })
  }
}

const resumeRun = async () => {
  if (!run.value?.id) return
  if (run.value?.status === 'waiting_user' && !resumeMessage.value.trim()) {
    toastStore.showToast({ type: 'error', message: '请先补充消息' })
    return
  }

  resumeLoading.value = true
  try {
    const patch = resumeMessage.value.trim()
      ? { message: resumeMessage.value.trim() }
      : {}
    await agentsStore.resumeRun(run.value.id, patch)
    toastStore.showToast({ type: 'success', message: '已继续执行' })
    resumeMessage.value = ''
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to resume run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '继续运行失败' })
  } finally {
    resumeLoading.value = false
  }
}

watch(() => route.params.run_id, async () => {
  try {
    await loadRun()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to load run detail:', error)
  }
})

watch(() => run.value?.id, () => {
  surfaceOpen.value = false
})

watch(showStructuredSurface, (visible) => {
  if (!visible) {
    surfaceOpen.value = false
  }
})

watch(
  () => [runEvents.value.length, run.value?.status, run.value?.finalOutput, run.value?.finalOutputText, run.value?.updatedAt],
  () => {
    scrollThreadToBottom()
  }
)

onMounted(async () => {
  try {
    await loadRun()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to initialize run detail:', error)
  }
})

onUnmounted(() => {
  agentsStore.stopRunStream()
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

const formatBytes = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return '0 B'
  if (parsed < 1024) return `${parsed} B`
  if (parsed < 1024 * 1024) return `${(parsed / 1024).toFixed(1)} KB`
  return `${(parsed / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.agent-chat-page {
  min-height: 100%;
  padding: 20px 24px 24px;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 18px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  background:
    radial-gradient(circle at top, rgba(16, 163, 127, 0.08), transparent 34%),
    linear-gradient(180deg, #f4f7f6 0%, #eef3f2 100%);
}

.chat-topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 22px;
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.topbar-main,
.topbar-side {
  display: grid;
  gap: 10px;
}

.topbar-main {
  min-width: 0;
}

.topbar-copy h1 {
  font-size: 28px;
  line-height: 1.08;
  color: #0f172a;
}

.topbar-copy p {
  margin-top: 8px;
  max-width: 780px;
  color: #475569;
  line-height: 1.6;
}

.topbar-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #0f766e;
  margin-bottom: 8px;
}

.back-link {
  width: fit-content;
  text-decoration: none;
  color: #0f766e;
  font-weight: 700;
}

.topbar-side {
  justify-items: end;
  flex-shrink: 0;
}

.topbar-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px 14px;
  color: #64748b;
  font-size: 13px;
}

.topbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.mono {
  font-family: var(--font-mono);
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}

.status-chip.queued {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.status-chip.running {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.status-chip.waiting_user {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.status-chip.completed {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.status-chip.failed,
.status-chip.cancelled {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.error-banner {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.workspace-status-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border-radius: 22px;
  border: 1px solid rgba(15, 118, 110, 0.16);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.06);
}

.workspace-status-card.muted {
  border-color: rgba(245, 158, 11, 0.2);
  background: rgba(255, 251, 235, 0.86);
}

.workspace-kicker {
  color: #0f766e;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.workspace-status-card h2 {
  margin-top: 6px;
  color: #0f172a;
  font-size: 18px;
}

.workspace-status-card p {
  margin-top: 6px;
  color: #64748b;
  line-height: 1.6;
}

.workspace-meta-grid,
.workspace-recovery {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  max-width: 560px;
}

.workspace-meta-grid span,
.workspace-recovery span,
.workspace-link {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 6px 10px;
  border-radius: 12px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}

.workspace-recovery span {
  background: rgba(245, 158, 11, 0.12);
  color: #92400e;
}

.chat-stage {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  border-radius: 30px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background:
    radial-gradient(circle at top left, rgba(110, 231, 183, 0.12), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.98) 100%);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.chat-thread {
  min-height: 0;
  overflow-y: auto;
  padding: 28px 24px 18px;
  display: grid;
  align-content: start;
  gap: 20px;
  min-width: 0;
}

.message-row {
  display: flex;
  min-width: 0;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-card {
  width: min(820px, 100%);
  max-width: 100%;
  min-width: 0;
  border-radius: 26px;
  padding: 18px 20px;
}

.user-card {
  background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
  color: white;
  box-shadow: 0 20px 40px rgba(15, 118, 110, 0.18);
}

.assistant-card {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.06);
}

.assistant-card.tone-question {
  border-color: rgba(245, 158, 11, 0.22);
  background: linear-gradient(180deg, #fffdf7 0%, #ffffff 100%);
}

.assistant-card.tone-error {
  border-color: rgba(239, 68, 68, 0.18);
  background: linear-gradient(180deg, #fff8f8 0%, #ffffff 100%);
}

.assistant-card.tone-muted {
  border-color: rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.message-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.message-role {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.message-time {
  font-size: 12px;
  color: rgba(100, 116, 139, 0.9);
}

.user-card .message-time {
  color: rgba(255, 255, 255, 0.72);
}

.user-bubble {
  padding: 16px 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.1);
}

.plain-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.plain-pre {
  margin: 0;
  font: inherit;
  color: inherit;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  max-width: 100%;
}

.assistant-streaming {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 88px;
}

.streaming-copy strong {
  display: block;
  color: #0f172a;
}

.streaming-copy p {
  margin-top: 6px;
  color: #64748b;
  line-height: 1.6;
}

.typing-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0f766e;
  animation: typing-bounce 1.2s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.3s;
}

.detail-row {
  padding-left: 4px;
}

.detail-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: min(820px, 100%);
  max-width: 100%;
  min-width: 0;
  padding: 12px 16px;
  border: 1px dashed rgba(15, 118, 110, 0.2);
  border-radius: 18px;
  background: rgba(15, 118, 110, 0.04);
  color: #0f172a;
  cursor: pointer;
}

.detail-toggle span:last-child {
  color: #64748b;
  font-size: 13px;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.surface-toggle {
  border-style: solid;
  background: rgba(15, 23, 42, 0.03);
}

.result-surface {
  display: grid;
  gap: 16px;
  max-height: min(76vh, 940px);
  overflow: hidden;
}

.composer-shell {
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  padding: 18px 20px 20px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  display: grid;
  gap: 14px;
  min-width: 0;
}

.composer-copy {
  display: grid;
  gap: 4px;
}

.composer-copy strong {
  color: #0f172a;
}

.composer-copy span {
  color: #64748b;
  line-height: 1.6;
}

.composer-form {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  min-width: 0;
}

.composer-input {
  flex: 1;
  min-width: 0;
  min-height: 56px;
  max-height: 180px;
  resize: vertical;
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 20px;
  padding: 16px 18px;
  background: #f8fafc;
  font: inherit;
  line-height: 1.6;
  color: #0f172a;
}

.composer-input:focus {
  outline: none;
  border-color: rgba(15, 118, 110, 0.42);
  box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.08);
}

.composer-submit {
  min-width: 136px;
  height: 56px;
  border-radius: 18px;
}

.composer-actions-readonly {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.details-panel {
  border-radius: 26px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
  padding: 20px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.06);
  min-width: 0;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
}

.details-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.details-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 16px;
  margin-bottom: 16px;
}

.details-panel-head h2 {
  font-size: 20px;
  color: #0f172a;
}

.details-panel-head p {
  margin-top: 6px;
  color: #64748b;
}

.details-close {
  border: none;
  background: transparent;
  color: #0f766e;
  font-weight: 700;
  cursor: pointer;
}

.agent-markdown {
  color: #0f172a;
  line-height: 1.75;
}

:deep(.agent-markdown > :first-child) {
  margin-top: 0;
}

:deep(.agent-markdown > :last-child) {
  margin-bottom: 0;
}

:deep(.agent-markdown > * + *) {
  margin-top: 1em;
}

:deep(.agent-markdown p) {
  margin: 0;
}

:deep(.agent-markdown ul),
:deep(.agent-markdown ol) {
  padding-left: 1.4em;
}

:deep(.agent-markdown pre) {
  overflow: auto;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  padding: 14px 16px;
  border-radius: 16px;
  background: #0f172a;
  color: #e2e8f0;
}

:deep(.agent-markdown code) {
  font-family: var(--font-mono);
}

:deep(.agent-markdown blockquote) {
  padding-left: 14px;
  border-left: 3px solid rgba(15, 118, 110, 0.24);
  color: #475569;
}

@keyframes typing-bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }

  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

@media (max-width: 960px) {
  .agent-chat-page {
    padding: 16px;
  }

  .chat-topbar,
  .workspace-status-card,
  .details-panel {
    border-radius: 22px;
  }

  .workspace-status-card {
    flex-direction: column;
  }

  .workspace-meta-grid,
  .workspace-recovery {
    justify-content: flex-start;
    max-width: 100%;
  }

  .chat-topbar,
  .details-panel-head {
    flex-direction: column;
  }

  .details-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .topbar-side,
  .topbar-actions {
    justify-items: start;
    justify-content: flex-start;
  }

  .chat-thread {
    padding: 20px 16px 16px;
  }

  .message-card,
  .detail-toggle {
    width: 100%;
  }

  .composer-form {
    flex-direction: column;
    align-items: stretch;
  }

  .composer-submit {
    width: 100%;
  }
}
</style>
