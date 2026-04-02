<template>
  <div class="agent-chat-page">
    <header class="chat-topbar">
      <div class="topbar-main">
        <router-link to="/agents" class="back-link">返回智能体列表</router-link>
        <div class="topbar-copy">
          <div class="topbar-kicker">Agent Chat</div>
          <h1>{{ agent?.name || '智能体会话' }}</h1>
          <p>{{ topbarSummary }}</p>
        </div>
      </div>

      <div class="topbar-side">
        <span :class="['status-chip', effectiveStatus]">{{ statusLabel }}</span>
        <div class="topbar-meta">
          <span v-if="currentRun?.updatedAt">更新于 {{ formatTime(currentRun.updatedAt) }}</span>
          <span v-else>尚未开始运行</span>
        </div>
        <div class="topbar-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="composerDisabled"
            @click="startNewConversation"
          >
            新会话
          </button>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="!currentSessionId"
            @click="clearContext"
          >
            清理上下文
          </button>
          <button type="button" class="btn btn-secondary" @click="refreshConversation">刷新</button>
          <router-link :to="basicSettingsLink" class="btn btn-secondary">基础设置</router-link>
          <router-link :to="extensionsLink" class="btn btn-secondary">扩展绑定</router-link>
          <router-link :to="runsLink" class="btn btn-secondary">运行记录</router-link>
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

    <section class="chat-stage">
      <div ref="threadRef" class="chat-thread">
        <div v-if="!currentRun" class="empty-chat-card">
          <div class="empty-chat-kicker">准备开始</div>
          <h2>{{ agent?.name || '这个智能体' }}</h2>
          <p>{{ agent?.description || '发送第一条消息后，这里会以聊天形式展示该智能体的执行结果。' }}</p>

          <div class="starter-list">
            <button
              v-for="prompt in starterPrompts"
              :key="prompt"
              type="button"
              class="starter-chip"
              @click="composerMessage = prompt"
            >
              {{ prompt }}
            </button>
          </div>
        </div>

        <div
          v-for="message in conversationMessages"
          :key="message.key"
          :class="['message-row', message.role]"
        >
          <article :class="messageCardClass(message)">
            <div class="message-head">
              <span class="message-role">{{ message.role === 'user' ? '你' : message.title }}</span>
              <span v-if="message.timestamp" class="message-time">{{ formatTime(message.timestamp) }}</span>
            </div>

            <div v-if="message.streaming" class="assistant-streaming">
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

            <template v-else-if="message.role === 'assistant'">
              <div
                v-if="message.renderMarkdown"
                class="markdown agent-markdown"
                v-html="message.html"
              ></div>

              <pre v-else class="plain-text plain-pre">{{ message.content }}</pre>
            </template>

            <div v-else class="user-bubble">
              <div class="plain-text">{{ message.content }}</div>
            </div>
          </article>
        </div>

        <div v-if="showDetailHint" class="message-row assistant detail-row">
          <button
            type="button"
            class="detail-toggle"
            @click="detailsOpen = !detailsOpen"
          >
            <span>执行细节</span>
            <span>{{ steps.length }} 步 · {{ toolCalls.length }} 次工具 · {{ runEvents.length }} 个事件</span>
          </button>
        </div>

        <div v-if="showStructuredSurface" class="result-surface">
          <AgentArtifactPanel
            :artifacts="surfaceArtifacts"
            :final-output-json="surfaceOutputJson"
            :surface-meta="executionSurface"
          />
        </div>
      </div>

      <footer class="composer-shell">
        <div class="composer-copy">
          <strong>{{ composerTitle }}</strong>
          <span>{{ composerDescription }}</span>
        </div>

        <div class="input-container">
          <div class="input-inner">
            <form class="input-form" @submit.prevent="submitMessage">
              <div class="input-wrapper">
                <textarea
                  ref="textareaRef"
                  v-model="composerMessage"
                  class="message-input"
                  rows="1"
                  :placeholder="composerPlaceholder"
                  :disabled="composerDisabled"
                  @compositionstart="isComposing = true"
                  @compositionend="isComposing = false"
                  @keydown.enter.exact.prevent="handleEnterSend"
                  @input="autoResize"
                ></textarea>

                <button
                  type="submit"
                  class="btn-send"
                  :disabled="composerDisabled || submitLoading || !composerMessage.trim()"
                  :aria-label="submitButtonLabel"
                  :title="submitButtonLabel"
                >
                  <span v-if="!submitLoading" class="send-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                      <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </span>
                  <span v-else class="spinner"></span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </footer>
    </section>

    <section v-if="showDetailHint && detailsOpen" class="details-panel">
      <div class="details-panel-head">
        <div>
          <h2>执行细节</h2>
          <p>默认收起，仅在需要排查运行过程时展开查看。</p>
        </div>
        <div class="details-head-actions">
          <button
            v-if="currentRun?.id"
            type="button"
            class="details-link"
            @click="openRunDetail"
          >
            查看运行详情页
          </button>
          <button type="button" class="details-close" @click="detailsOpen = false">收起</button>
        </div>
      </div>

      <div class="details-grid">
        <AgentArtifactPanel
          :artifacts="artifacts"
          :final-output-json="currentRun?.finalOutputJson"
          :surface-meta="executionSurface"
        />
        <AgentPlanPanel :plan="plan" />
      </div>
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
import { useAgentsStore } from '@/store/agents'
import { useToastStore } from '@/store/toast'
import { getRunAnswerText } from '@/utils/agentArtifacts'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const composerMessage = ref('')
const isComposing = ref(false)
const submitLoading = ref(false)
const detailsOpen = ref(false)
const threadRef = ref(null)
const textareaRef = ref(null)
const draftSessionId = ref('')

const starterPrompts = [
  '请介绍一下你能帮我做什么',
  '帮我拆解这个任务并给出执行建议',
  '请根据我的目标给我一个行动方案'
]

const agent = computed(() => agentsStore.currentAgent)
const currentRun = computed(() => {
  if (!agentsStore.currentRun?.id) {
    return null
  }
  if (agentsStore.currentRun.agentDefinitionId !== agent.value?.id) {
    return null
  }
  return agentsStore.currentRun
})
const runEvents = computed(() => agentsStore.runEvents)
const steps = computed(() => agentsStore.steps)
const toolCalls = computed(() => agentsStore.toolCalls)
const plan = computed(() => agentsStore.plan)
const artifacts = computed(() => agentsStore.artifacts)
const executionSurface = computed(() => agentsStore.executionSurface)
const errorMessage = computed(() => agentsStore.error || '')

const statusMap = {
  idle: '待开始',
  queued: '排队中',
  running: '运行中',
  waiting_user: '等待补充',
  completed: '已完成',
  failed: '运行失败',
  cancelled: '已取消'
}

const basicSettingsLink = computed(() => agent.value?.id ? `/agents/${agent.value.id}/settings/basic` : '/agents')
const extensionsLink = computed(() => agent.value?.id ? `/agents/${agent.value.id}/settings/extensions` : '/agents')
const runsLink = computed(() => agent.value?.id ? `/agents/${agent.value.id}/runs` : '/agents')
const effectiveStatus = computed(() => currentRun.value?.status || 'idle')
const statusLabel = computed(() => statusMap[effectiveStatus.value] || effectiveStatus.value || '未知状态')
const canCancel = computed(() => ['queued', 'running'].includes(currentRun.value?.status))
const canResume = computed(() => ['waiting_user', 'failed', 'cancelled', 'completed'].includes(currentRun.value?.status))
const showGlobalError = computed(() => Boolean(errorMessage.value) && currentRun.value?.status !== 'failed')
const showDetailHint = computed(() => (
  steps.value.length > 0 ||
  toolCalls.value.length > 0 ||
  runEvents.value.length > 0 ||
  Boolean(plan.value) ||
  artifacts.value.length > 0 ||
  Boolean(currentRun.value?.finalOutputJson)
))
const composerDisabled = computed(() => ['queued', 'running'].includes(currentRun.value?.status))
const surfaceArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType !== 'answer'))
const surfaceOutputJson = computed(() => surfaceArtifacts.value.length > 0 ? null : currentRun.value?.finalOutputJson || null)
const showStructuredSurface = computed(() => surfaceArtifacts.value.length > 0 || Boolean(surfaceOutputJson.value))
const requestedSessionId = computed(() => {
  const value = String(route.query.session || '').trim()
  return value || ''
})
const currentSessionId = computed(() => {
  const value = String(currentRun.value?.sessionId || requestedSessionId.value || draftSessionId.value || '').trim()
  return value || ''
})

const createSessionId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `00000000-0000-4000-8000-${Date.now().toString(16).padStart(12, '0').slice(-12)}`
}

const topbarSummary = computed(() => {
  if (!currentRun.value && requestedSessionId.value) {
    return '当前是一个新的空白会话。发送第一条消息后，会从全新上下文开始执行。'
  }
  if (!currentRun.value) {
    return '这是该智能体的聊天入口。发送第一条消息后，会进入持续上下文的多轮对话。'
  }
  if (currentRun.value.status === 'waiting_user') {
    return '智能体已暂停，等待你补充消息后继续执行。'
  }
  if (currentRun.value.status === 'running' || currentRun.value.status === 'queued') {
    return '当前会话正在执行，主视图只保留对话内容，过程细节按需展开。'
  }
  return '后续消息会继续当前会话，不再是一次性单轮 run。'
})

const activeStep = computed(() => (
  steps.value.find((step) => step.status === 'running') ||
  steps.value[steps.value.length - 1] ||
  null
))

const streamingTitle = computed(() => currentRun.value?.status === 'queued' ? '正在排队' : '智能体正在处理中')
const streamingDescription = computed(() => {
  if (currentRun.value?.status === 'queued') {
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
  const answer = getRunAnswerText(currentRun.value || {})
  if (answer) {
    return answer
  }
  if (currentRun.value?.status === 'failed') {
    return currentRun.value.errorMessage || '运行失败，请补充输入后重试。'
  }
  if (currentRun.value?.status === 'cancelled') {
    return currentRun.value.errorMessage || '运行已取消。'
  }
  return ''
})

const assistantTitle = computed(() => {
  if (currentRun.value?.status === 'waiting_user') {
    return '智能体提问'
  }
  if (currentRun.value?.status === 'failed') {
    return '运行错误'
  }
  if (currentRun.value?.status === 'cancelled') {
    return '运行状态'
  }
  return agent.value?.name || '智能体'
})

const assistantToneClass = computed(() => {
  if (currentRun.value?.status === 'waiting_user') {
    return 'tone-question'
  }
  if (currentRun.value?.status === 'failed') {
    return 'tone-error'
  }
  if (currentRun.value?.status === 'cancelled') {
    return 'tone-muted'
  }
  return 'tone-default'
})

const composerTitle = computed(() => {
  if (!currentRun.value && requestedSessionId.value) {
    return '开始新会话'
  }
  if (!currentRun.value) {
    return '开始对话'
  }
  if (currentRun.value.status === 'waiting_user') {
    return '补充消息'
  }
  if (currentRun.value.status === 'failed') {
    return '修正后重试'
  }
  if (currentRun.value.status === 'cancelled') {
    return '继续当前运行'
  }
  if (currentRun.value.status === 'queued' || currentRun.value.status === 'running') {
    return '当前运行进行中'
  }
  return '继续对话'
})

const composerDescription = computed(() => {
  if (!currentRun.value && requestedSessionId.value) {
    return '这会创建一个新的独立会话，不会继续上一轮 run。'
  }
  if (!currentRun.value) {
    return '输入第一条消息后，这个智能体会进入持续上下文的会话。'
  }
  if (currentRun.value.status === 'waiting_user') {
    return '像聊天一样补充上下文，发送后会在当前 run 内继续执行。'
  }
  if (currentRun.value.status === 'failed') {
    return '补充错误上下文后重试，或者重新描述你的需求。'
  }
  if (currentRun.value.status === 'cancelled') {
    return '补充一条消息后继续当前 run。'
  }
  if (currentRun.value.status === 'queued' || currentRun.value.status === 'running') {
    return '等待当前运行结束后，再开始新的消息。'
  }
  return '继续发送消息会沿用当前 run 的上下文继续对话。'
})

const composerPlaceholder = computed(() => {
  if (!currentRun.value && requestedSessionId.value) {
    return '输入新会话的第一条消息...'
  }
  if (!currentRun.value) {
    return '输入消息...'
  }
  if (currentRun.value.status === 'waiting_user') {
    return '输入补充信息...'
  }
  if (currentRun.value.status === 'failed') {
    return '补充修正信息，或重新描述你的需求'
  }
  if (currentRun.value.status === 'cancelled') {
    return '可选：输入补充信息后继续'
  }
  if (currentRun.value.status === 'queued' || currentRun.value.status === 'running') {
    return '当前运行进行中'
  }
  return '输入消息... (Enter 发送，Shift+Enter 换行)'
})

const submitButtonLabel = computed(() => canResume.value ? '发送并继续' : '发送')

const buildThreadMessages = () => {
  const items = []
  const existingConversation = Array.isArray(currentRun.value?.context?.conversation)
    ? currentRun.value.context.conversation
    : []

  for (const [index, entry] of existingConversation.entries()) {
    const role = entry?.role === 'assistant' ? 'assistant' : 'user'
    const content = String(entry?.content || '').trim()
    if (!content) {
      continue
    }
    items.push({
      key: `context-${index}`,
      role,
      title: role === 'assistant' ? (agent.value?.name || '智能体') : '你',
      content,
      renderMarkdown: role === 'assistant',
      html: role === 'assistant' ? renderMarkdown(content) : '',
      toneClass: 'tone-default',
      timestamp: null,
      streaming: false
    })
  }

  const appendIfNeeded = (message) => {
    const lastMessage = items[items.length - 1]
    if (
      lastMessage &&
      lastMessage.role === message.role &&
      lastMessage.content === message.content &&
      !lastMessage.streaming &&
      !message.streaming
    ) {
      return
    }
    items.push(message)
  }

  const status = currentRun.value?.status || ''
  const liveUserMessage = String(currentRun.value?.input?.message || currentRun.value?.input?.prompt || '').trim()
  const lastContextMessage = items[items.length - 1] || null
  const lastAssistantMessage = [...items].reverse().find((message) => message.role === 'assistant') || null
  const shouldAppendResolvedTurn = Boolean(
    liveUserMessage &&
    assistantContent.value &&
    ['completed', 'waiting_user'].includes(status) &&
    lastAssistantMessage?.content !== assistantContent.value.trim()
  )

  if (
    liveUserMessage &&
    (
      shouldAppendResolvedTurn ||
      ['queued', 'running', 'failed', 'cancelled'].includes(status)
    ) &&
    !(lastContextMessage?.role === 'user' && lastContextMessage.content === liveUserMessage)
  ) {
    appendIfNeeded({
      key: `live-user-${currentRun.value?.updatedAt || currentRun.value?.id || 'draft'}`,
      role: 'user',
      title: '你',
      content: liveUserMessage,
      renderMarkdown: false,
      html: '',
      toneClass: '',
      timestamp: items.length === 0 ? currentRun.value?.createdAt || null : null,
      streaming: false
    })
  }

  if (['queued', 'running'].includes(status) && !assistantContent.value) {
    items.push({
      key: `live-stream-${currentRun.value?.updatedAt || currentRun.value?.id || 'stream'}`,
      role: 'assistant',
      title: assistantTitle.value,
      content: '',
      renderMarkdown: false,
      html: '',
      toneClass: assistantToneClass.value,
      timestamp: currentRun.value?.updatedAt || null,
      streaming: true
    })
    return items
  }

  const liveAssistantMessage = assistantContent.value.trim()
  if (liveAssistantMessage && lastAssistantMessage?.content !== liveAssistantMessage) {
    appendIfNeeded({
      key: `live-assistant-${currentRun.value?.updatedAt || currentRun.value?.id || 'reply'}`,
      role: 'assistant',
      title: assistantTitle.value,
      content: liveAssistantMessage,
      renderMarkdown: Boolean(currentRun.value?.finalOutputText || currentRun.value?.finalOutput),
      html: (currentRun.value?.finalOutputText || currentRun.value?.finalOutput) ? renderMarkdown(liveAssistantMessage) : '',
      toneClass: assistantToneClass.value,
      timestamp: currentRun.value?.updatedAt || null,
      streaming: false
    })
  }

  return items
}

const conversationMessages = computed(() => buildThreadMessages())
const conversationSignature = computed(() => JSON.stringify(
  conversationMessages.value.map((message) => ({
    role: message.role,
    content: message.content,
    streaming: message.streaming,
    timestamp: message.timestamp
  }))
))

const messageCardClass = (message) => {
  if (message.role === 'user') {
    return ['message-card', 'user-card']
  }
  return ['message-card', 'assistant-card', message.toneClass || 'tone-default']
}

const loadConversation = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) {
    router.push('/agents')
    return
  }

  agentsStore.stopRunStream()
  agentsStore.resetRunState()
  detailsOpen.value = false

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchRuns()
  ])

  const latestRun = agentsStore.sortedRuns.find((run) => {
    if (run.agentDefinitionId !== agentId) {
      return false
    }
    if (requestedSessionId.value) {
      return run.sessionId === requestedSessionId.value
    }
    return true
  })
  if (latestRun?.id) {
    draftSessionId.value = latestRun.sessionId || requestedSessionId.value || ''
    await agentsStore.openRun(latestRun.id, { stream: true })
    return
  }

  draftSessionId.value = requestedSessionId.value || createSessionId()
}

const scrollThreadToBottom = async () => {
  await nextTick()
  if (!threadRef.value) return
  threadRef.value.scrollTop = threadRef.value.scrollHeight
}

const autoResize = async () => {
  await nextTick()
  if (!textareaRef.value) return
  textareaRef.value.style.height = 'auto'
  textareaRef.value.style.height = `${Math.min(textareaRef.value.scrollHeight, 180)}px`
}

const handleEnterSend = (event) => {
  if (isComposing.value || event?.isComposing || event?.keyCode === 229) {
    return
  }
  submitMessage()
}

const refreshConversation = async () => {
  try {
    await loadConversation()
    toastStore.showToast({ type: 'success', message: '会话已刷新' })
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to refresh conversation:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '刷新会话失败' })
  }
}

const startNewConversation = async () => {
  if (!agent.value?.id || composerDisabled.value) {
    return
  }

  const nextSessionId = createSessionId()
  draftSessionId.value = nextSessionId
  composerMessage.value = ''
  detailsOpen.value = false
  agentsStore.stopRunStream()
  agentsStore.resetRunState()
  agentsStore.error = null

  try {
    await router.replace({
      path: route.path,
      query: {
        ...route.query,
        session: nextSessionId
      }
    })
    await autoResize()
    await scrollThreadToBottom()
    toastStore.showToast({ type: 'success', message: '已切换到新会话' })
  } catch (error) {
    console.error('Failed to start a new conversation:', error)
    toastStore.showToast({ type: 'error', message: '切换新会话失败' })
  }
}

const clearContext = async () => {
  if (!agent.value?.id || !currentSessionId.value) {
    return
  }

  const confirmed = window.confirm('确认清理当前会话的上下文吗？这会删除当前智能体在该会话下的运行记录和关联对话。')
  if (!confirmed) {
    return
  }

  try {
    agentsStore.stopRunStream()
    await agentsStore.clearAgentContext(agent.value.id, currentSessionId.value)
    composerMessage.value = ''
    detailsOpen.value = false
    await loadConversation()
    toastStore.showToast({ type: 'success', message: '上下文已清理' })
    await autoResize()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to clear agent context:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '清理上下文失败' })
  }
}

const submitMessage = async () => {
  const message = composerMessage.value.trim()
  if (!agent.value?.id || !message) {
    toastStore.showToast({ type: 'error', message: '请先输入消息' })
    return
  }
  if (composerDisabled.value) {
    return
  }

  submitLoading.value = true
  try {
    if (currentRun.value?.id) {
      await agentsStore.resumeRun(currentRun.value.id, { message })
      toastStore.showToast({ type: 'success', message: '已继续执行' })
    } else {
      const nextSessionId = requestedSessionId.value || draftSessionId.value || createSessionId()
      const createdRun = await agentsStore.createRun(agent.value.id, {
        input: {
          message
        },
        session_id: nextSessionId,
        metadata: {},
        auto_start: true
      })
      draftSessionId.value = nextSessionId
      await agentsStore.openRun(createdRun.id, { stream: true })
      toastStore.showToast({ type: 'success', message: '已开始运行' })
    }

    composerMessage.value = ''
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
    await agentsStore.fetchRuns()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to submit agent message:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '发送失败' })
  } finally {
    submitLoading.value = false
  }
}

const cancelRun = async () => {
  if (!currentRun.value?.id) return
  try {
    await agentsStore.cancelRun(currentRun.value.id)
    await agentsStore.fetchRuns()
    toastStore.showToast({ type: 'success', message: '运行已停止' })
  } catch (error) {
    console.error('Failed to cancel run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '停止运行失败' })
  }
}

const openRunDetail = () => {
  if (!currentRun.value?.id) return
  router.push(`/agents/runs/${currentRun.value.id}`)
}

watch(() => [route.params.id, route.query.session], async () => {
  try {
    await loadConversation()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to reload agent conversation:', error)
  }
})

watch(
  () => conversationSignature.value,
  () => {
    scrollThreadToBottom()
  }
)

watch(composerMessage, () => {
  autoResize()
})

onMounted(async () => {
  try {
    await loadConversation()
    await autoResize()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to initialize agent conversation:', error)
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
</script>

<style scoped>
.agent-chat-page {
  min-height: 100%;
  padding: 20px 24px 24px;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 18px;
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

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}

.status-chip.idle,
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

.chat-stage {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
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
}

.empty-chat-card {
  width: min(760px, 100%);
  padding: 26px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(16, 163, 127, 0.16), transparent 30%),
    linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.06);
}

.empty-chat-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

.empty-chat-card h2 {
  margin-top: 12px;
  font-size: 30px;
  color: #0f172a;
}

.empty-chat-card p {
  margin-top: 10px;
  color: #475569;
  line-height: 1.7;
}

.starter-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.starter-chip {
  border: 1px solid rgba(15, 118, 110, 0.16);
  background: rgba(15, 118, 110, 0.05);
  color: #0f766e;
  border-radius: 999px;
  padding: 10px 14px;
  cursor: pointer;
}

.message-row {
  display: flex;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-card {
  width: min(820px, 100%);
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
}

.composer-shell {
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  padding: 18px 20px 20px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px);
  display: grid;
  gap: 14px;
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
  display: block;
}

.input-container {
  width: 100%;
}

.input-inner {
  display: grid;
  gap: 12px;
}

.input-form {
  width: 100%;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 24px;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.1);
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input-wrapper:focus-within {
  border-color: rgba(15, 118, 110, 0.42);
  box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.08);
}

.message-input {
  flex: 1;
  min-height: 24px;
  max-height: 180px;
  resize: none;
  border: none;
  background: transparent;
  font: inherit;
  line-height: 1.7;
  color: #0f172a;
  padding: 2px 0;
}

.message-input:focus {
  outline: none;
}

.message-input:disabled {
  cursor: not-allowed;
  color: #94a3b8;
}

.btn-send {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 16px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
  color: white;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
  box-shadow: 0 12px 24px rgba(15, 118, 110, 0.2);
}

.btn-send:hover:not(:disabled) {
  transform: translateY(-1px);
}

.btn-send:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  box-shadow: none;
}

.result-surface {
  display: grid;
  gap: 16px;
}

.send-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.details-panel {
  border-radius: 26px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
  padding: 20px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.06);
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

.details-head-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.details-link,
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .agent-chat-page {
    padding: 16px;
  }

  .chat-topbar,
  .details-panel {
    border-radius: 22px;
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

  .empty-chat-card,
  .message-card,
  .detail-toggle {
    width: 100%;
  }

  .input-wrapper {
    padding: 12px 14px;
  }
}
</style>
