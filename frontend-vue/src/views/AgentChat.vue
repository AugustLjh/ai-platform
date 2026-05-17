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
        <details class="topbar-actions-menu">
          <summary class="topbar-actions-toggle">操作</summary>
          <div class="topbar-actions-panel">
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
        </details>
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
              <div v-if="message.attachments && message.attachments.length > 0" class="uploaded-file-list">
                <div
                  v-for="file in message.attachments"
                  :key="`${message.key}-${file.id || file.path || file.name}`"
                  class="uploaded-file-chip"
                >
                  <span class="uploaded-file-name">{{ file.path || file.name }}</span>
                </div>
              </div>
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
            <span>{{ steps.length }} 步 · {{ toolCalls.length }} 次工具 · {{ runTreeInvocations.length }} 次委派 · {{ runEvents.length }} 个事件</span>
          </button>
        </div>

        <div v-if="showSubagentClarification" class="message-row assistant">
          <AgentSubagentClarificationCard :run="currentRun" />
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
        <input
          ref="fileInputRef"
          type="file"
          multiple
          class="upload-input"
          @change="handleFileChange"
        />
        <input
          ref="folderInputRef"
          type="file"
          multiple
          webkitdirectory
          directory
          class="upload-input"
          @change="handleFolderChange"
        />

        <div v-if="uploadError" class="error-banner upload-error">
          {{ uploadError }}
        </div>

        <div v-if="workspaceError" class="error-banner upload-error">
          {{ workspaceError }}
        </div>

        <details class="workspace-bind-shell">
          <summary class="workspace-bind-head">
            <strong>Workspace 绑定</strong>
            <button
              type="button"
              class="workspace-refresh-btn"
              :disabled="workspaceLoading"
              @click.stop.prevent="loadWorkspaceSources"
            >
              {{ workspaceLoading ? '刷新中...' : '刷新目录' }}
            </button>
          </summary>
          <div class="workspace-bind-body">
            <div class="workspace-bind-grid">
              <label class="workspace-option">
                <span>模式</span>
                <select v-model="workspaceMode" class="workspace-select">
                  <option value="none">仅聊天上下文</option>
                  <option value="upload_bundle">使用上传文件创建副本</option>
                  <option value="existing">从允许目录创建副本</option>
                </select>
              </label>

              <label v-if="workspaceMode === 'existing'" class="workspace-option workspace-option-wide">
                <span>项目目录</span>
                <select v-model="selectedWorkspacePath" class="workspace-select">
                  <option value="">请选择允许目录</option>
                  <option
                    v-for="source in workspaceSources"
                    :key="source.path"
                    :value="source.path"
                  >
                    {{ formatWorkspaceSource(source) }}
                  </option>
                </select>
              </label>
            </div>
            <div class="workspace-bind-meta">
              <span v-if="workspaceMode === 'upload_bundle'">上传文件会进入 run 级 workspace 副本。</span>
              <span v-else-if="workspaceMode === 'existing'">项目会复制到 run workspace，不直接写原目录。</span>
              <span v-else>不绑定 workspace，只使用聊天上下文和上传摘要。</span>
              <span v-if="workspaceSummaryText">{{ workspaceSummaryText }}</span>
            </div>
          </div>
        </details>

        <div v-if="bundles.length > 0" class="composer-upload-list">
          <div
            v-for="bundle in bundles"
            :key="bundle.bundle_id"
            class="composer-upload-card"
          >
            <div class="composer-upload-main">
              <strong>{{ bundle.summary?.file_count || bundle.files?.length || 0 }} 个文件</strong>
              <span>{{ formatUploadBundle(bundle) }}</span>
            </div>
            <button
              type="button"
              class="composer-upload-remove"
              @click="removeBundle(bundle.bundle_id)"
            >
              移除
            </button>
          </div>
        </div>

        <div class="input-container">
          <div class="input-inner">
            <div class="composer-tools">
              <button
                type="button"
                class="composer-tool-btn"
                :disabled="uploading"
                aria-label="上传文件"
                title="上传文件"
                @click="openFilePicker"
              >
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M14 3v5h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M12 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                  <path d="M9.5 13.5 12 11l2.5 2.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
              <button
                type="button"
                class="composer-tool-btn"
                :disabled="uploading"
                aria-label="上传文件夹"
                title="上传文件夹"
                @click="openFolderPicker"
              >
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M12 11v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                  <path d="M9.5 13.5 12 11l2.5 2.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>

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

          <div v-if="hasUploads" class="composer-tool-meta">已附加 {{ totalFiles }} 个文件</div>
          <div v-else-if="uploading" class="composer-tool-meta">正在解析文件...</div>
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
import { useUploadBundles } from '@/composables/useUploadBundles'
import { agentsAPI } from '@/api'
import { buildWorkspaceSourcePayload, getAgentWorkspaceBindingPolicy, formatWorkspaceSource } from '@/utils/workspaceBindings'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const composerMessage = ref('')
const isComposing = ref(false)
const submitLoading = ref(false)
const detailsOpen = ref(false)
const surfaceOpen = ref(false)
const threadRef = ref(null)
const textareaRef = ref(null)
const draftSessionId = ref('')
const workspaceMode = ref('none')
const selectedWorkspacePath = ref('')
const workspaceSources = ref([])
const workspaceInspection = ref(null)
const workspaceLoading = ref(false)
const workspaceError = ref('')
const {
  bundles,
  bundleIds,
  totalFiles,
  hasUploads,
  uploading,
  uploadError,
  fileInputRef,
  folderInputRef,
  openFilePicker,
  openFolderPicker,
  handleFileChange,
  handleFolderChange,
  removeBundle,
  clearBundles
} = useUploadBundles()

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
const currentRunTree = computed(() => agentsStore.currentRunTree)
const runTreeInvocations = computed(() => agentsStore.currentRunInvocations)
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
  Boolean(currentRun.value?.finalOutputJson) ||
  Boolean(currentRunTree.value?.invocations?.length)
))
const composerDisabled = computed(() => ['queued', 'running'].includes(currentRun.value?.status))
const surfaceArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType !== 'answer'))
const surfaceOutputJson = computed(() => surfaceArtifacts.value.length > 0 ? null : currentRun.value?.finalOutputJson || null)
const showStructuredSurface = computed(() => surfaceArtifacts.value.length > 0 || Boolean(surfaceOutputJson.value))
const structuredResultCount = computed(() => surfaceArtifacts.value.length + (surfaceOutputJson.value ? 1 : 0))
const showSubagentClarification = computed(() => Boolean(
  currentRun.value?.status === 'waiting_user' &&
  currentRun.value?.context &&
  (currentRun.value.context.pending_subagent_clarification || currentRun.value.context.pendingSubagentClarification)
))
const requestedSessionId = computed(() => {
  const value = String(route.query.session || '').trim()
  return value || ''
})
const currentSessionId = computed(() => {
  const value = String(currentRun.value?.sessionId || requestedSessionId.value || draftSessionId.value || '').trim()
  return value || ''
})
const currentWorkspaceSource = computed(() => {
  const source = currentRun.value?.input?.workspace_source || currentRun.value?.input?.workspace || {}
  return source && typeof source === 'object' ? source : {}
})
const defaultWorkspacePolicy = computed(() => getAgentWorkspaceBindingPolicy(agent.value || {}))
const workspaceSummaryText = computed(() => {
  const inspection = workspaceInspection.value || {}
  const parts = []
  if (typeof inspection.workspace_count === 'number') {
    parts.push(`现有 ${inspection.workspace_count} 个 workspace`)
  }
  if (typeof inspection.expired_count === 'number' && inspection.expired_count > 0) {
    parts.push(`过期 ${inspection.expired_count} 个`)
  }
  if (workspaceMode.value === 'existing' && selectedWorkspacePath.value) {
    parts.push(`将复制 ${selectedWorkspacePath.value}`)
  }
  if (workspaceMode.value === 'upload_bundle' && bundleIds.value.length > 0) {
    parts.push(`将物化 ${bundleIds.value.length} 个上传包`)
  }
  if (!currentRun.value && defaultWorkspacePolicy.value.enabled && workspaceMode.value !== 'none') {
    parts.push('已套用智能体默认绑定策略')
  }
  return parts.join(' · ')
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
  const currentManifestFiles = Array.isArray(currentRun.value?.input?.uploaded_attachments_manifest?.files)
    ? currentRun.value.input.uploaded_attachments_manifest.files
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
      attachments: currentManifestFiles,
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
  surfaceOpen.value = false

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchRuns(),
    loadWorkspaceSources()
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
    syncWorkspaceBindingFromRun()
    return
  }

  draftSessionId.value = requestedSessionId.value || createSessionId()
  syncWorkspaceBindingFromRun()
}

const syncWorkspaceBindingFromRun = () => {
  const source = currentWorkspaceSource.value
  const sourceType = String(source.type || source.source_type || '').trim()
  if (sourceType === 'upload_bundle') {
    workspaceMode.value = 'upload_bundle'
    selectedWorkspacePath.value = ''
    return
  }
  if (sourceType === 'existing' || sourceType === 'bound' || sourceType === 'local_path') {
    workspaceMode.value = 'existing'
    selectedWorkspacePath.value = String(source.root || source.path || '').trim()
    return
  }
  if (!currentRun.value && defaultWorkspacePolicy.value.enabled) {
    workspaceMode.value = defaultWorkspacePolicy.value.mode
    selectedWorkspacePath.value = defaultWorkspacePolicy.value.path
    return
  }
  workspaceMode.value = 'none'
  selectedWorkspacePath.value = ''
}

const loadWorkspaceSources = async () => {
  workspaceLoading.value = true
  workspaceError.value = ''
  try {
    const [{ data: sourcesData }, { data: inspectionData }] = await Promise.all([
      agentsAPI.listWorkspaceSources(),
      agentsAPI.inspectWorkspaces()
    ])
    workspaceSources.value = Array.isArray(sourcesData?.sources) ? sourcesData.sources : []
    workspaceInspection.value = inspectionData || null
  } catch (error) {
    console.error('Failed to load workspace sources:', error)
    workspaceError.value = error?.response?.data?.detail || error?.message || '加载 workspace 目录失败'
  } finally {
    workspaceLoading.value = false
  }
}

const resolveWorkspaceSourcePayload = () => {
  const existingBundleIds = Array.isArray(currentRun.value?.input?.upload_bundle_ids) ? currentRun.value.input.upload_bundle_ids : []
  return buildWorkspaceSourcePayload({
    mode: workspaceMode.value,
    selectedPath: selectedWorkspacePath.value,
    bundleIds: bundleIds.value,
    existingBundleIds
  })
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
  surfaceOpen.value = false
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
    surfaceOpen.value = false
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
    const workspaceSource = resolveWorkspaceSourcePayload()
    const mergedBundleIds = bundleIds.value.length > 0
      ? Array.from(new Set([
          ...(Array.isArray(currentRun.value?.input?.upload_bundle_ids) ? currentRun.value.input.upload_bundle_ids : []),
          ...bundleIds.value
        ]))
      : []
    if (currentRun.value?.id) {
      const inputPatch = { message }
      if (mergedBundleIds.length > 0) {
        inputPatch.upload_bundle_ids = mergedBundleIds
      }
      if (workspaceSource) {
        inputPatch.workspace_source = workspaceSource
      }
      await agentsStore.resumeRun(currentRun.value.id, inputPatch)
      toastStore.showToast({ type: 'success', message: '已继续执行' })
    } else {
      const nextSessionId = requestedSessionId.value || draftSessionId.value || createSessionId()
      const createdRun = await agentsStore.createRun(agent.value.id, {
        input: {
          message,
          ...(bundleIds.value.length > 0 ? { upload_bundle_ids: bundleIds.value } : {}),
          ...(workspaceSource ? { workspace_source: workspaceSource } : {})
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
    clearBundles()
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

const formatUploadBundle = (bundle) => {
  const files = Array.isArray(bundle?.files) ? bundle.files : []
  const names = files.slice(0, 2).map((file) => file.path || file.name).filter(Boolean)
  const rest = files.length - names.length
  return [names.join('，'), rest > 0 ? `等 ${files.length} 个` : '', bundle?.skipped?.length ? `跳过 ${bundle.skipped.length} 个` : '']
    .filter(Boolean)
    .join(' · ')
}

watch(() => [route.params.id, route.query.session], async () => {
  try {
    await loadConversation()
    await scrollThreadToBottom()
  } catch (error) {
    console.error('Failed to reload agent conversation:', error)
  }
})

watch(() => currentRun.value?.id, () => {
  surfaceOpen.value = false
  syncWorkspaceBindingFromRun()
})

watch(showStructuredSurface, (visible) => {
  if (!visible) {
    surfaceOpen.value = false
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
  height: 100%;
  padding: 10px 14px 14px;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 8px;
  background: #f6f7f8;
}

.chat-topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: min(1040px, 100%);
  justify-self: center;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(12px);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
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
  font-size: 20px;
  line-height: 1.2;
  color: #0f172a;
}

.topbar-copy p {
  margin-top: 3px;
  max-width: 540px;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.topbar-kicker {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #0f766e;
  margin-bottom: 3px;
}

.back-link {
  width: fit-content;
  text-decoration: none;
  color: #0f766e;
  font-weight: 700;
  font-size: 13px;
}

.topbar-side {
  justify-items: end;
  flex-shrink: 0;
  gap: 8px;
}

.topbar-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px 10px;
  color: #64748b;
  font-size: 12px;
}

.topbar-actions-menu {
  position: relative;
}

.topbar-actions-menu > summary {
  list-style: none;
}

.topbar-actions-menu > summary::-webkit-details-marker {
  display: none;
}

.topbar-actions-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 76px;
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(15, 118, 110, 0.18);
  background: rgba(15, 118, 110, 0.05);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  user-select: none;
}

.topbar-actions-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 10;
  display: grid;
  gap: 6px;
  min-width: 180px;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.12);
}

.topbar-actions-panel .btn {
  width: 100%;
  justify-content: flex-start;
  padding: 8px 10px;
  font-size: 12px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
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
  width: min(1040px, 100%);
  justify-self: center;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
  font-size: 13px;
}

.chat-stage {
  min-height: 0;
  width: min(1040px, 100%);
  justify-self: center;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background: #ffffff;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

.chat-thread {
  min-height: 0;
  overflow-y: auto;
  padding: 20px clamp(12px, 3vw, 36px) 14px;
  display: grid;
  align-content: start;
  gap: 14px;
}

.empty-chat-card {
  width: min(680px, 100%);
  justify-self: center;
  padding: 20px;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: none;
}

.empty-chat-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

.empty-chat-card h2 {
  margin-top: 8px;
  font-size: 24px;
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
  margin-top: 16px;
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
  width: min(760px, 100%);
  max-width: 100%;
  border-radius: 16px;
  padding: 13px 14px;
}

.user-card {
  width: fit-content;
  max-width: min(640px, 84%);
  background: #0f766e;
  color: white;
  box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
}

.assistant-card {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
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
  margin-bottom: 8px;
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
  padding: 0;
  border-radius: 0;
  background: transparent;
}

.uploaded-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.uploaded-file-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
}

.uploaded-file-name {
  max-width: min(460px, 64vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
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
  min-height: 76px;
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
  width: min(760px, 100%);
  max-width: 100%;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.8);
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

.composer-shell {
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  padding: 9px clamp(10px, 2.5vw, 22px) 12px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
  display: grid;
  gap: 8px;
  position: sticky;
  bottom: 0;
  z-index: 4;
}

.upload-input {
  display: none;
}

.workspace-bind-shell {
  display: grid;
  width: min(760px, 100%);
  justify-self: center;
  margin-bottom: 2px;
  padding: 0;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  background: rgba(248, 250, 252, 0.72);
  overflow: hidden;
}

.workspace-bind-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #0f172a;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
  list-style: none;
}

.workspace-bind-head::-webkit-details-marker {
  display: none;
}

.workspace-bind-body {
  display: grid;
  gap: 10px;
  padding: 9px 10px 10px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}

.workspace-refresh-btn {
  border: 1px solid rgba(15, 118, 110, 0.18);
  background: rgba(15, 118, 110, 0.06);
  color: #0f766e;
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.workspace-refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.workspace-bind-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.workspace-option {
  display: grid;
  gap: 8px;
}

.workspace-option span {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}

.workspace-option-wide {
  grid-column: 1 / -1;
}

.workspace-select {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: #fff;
  color: #0f172a;
  padding: 8px 10px;
  font-size: 13px;
}

.workspace-bind-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  font-size: 12px;
  color: #64748b;
}

.composer-form {
  display: block;
}

.composer-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-bottom: 4px;
}

.composer-tool-btn {
  width: 46px;
  height: 46px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  background: rgba(255, 255, 255, 0.92);
  color: #334155;
  border-radius: 16px;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.composer-tool-btn:hover:not(:disabled) {
  background: #ffffff;
  border-color: rgba(15, 118, 110, 0.34);
  transform: translateY(-1px);
}

.composer-tool-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  box-shadow: none;
}

.composer-tool-btn svg {
  width: 20px;
  height: 20px;
}

.composer-tool-meta {
  color: #64748b;
  font-size: 12px;
  padding-left: 58px;
}

.composer-upload-list {
  display: grid;
  gap: 10px;
}

.composer-upload-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
}

.composer-upload-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.composer-upload-main strong {
  color: #0f172a;
  font-size: 13px;
}

.composer-upload-main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.composer-upload-remove {
  border: none;
  background: transparent;
  color: #c2410c;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.upload-error {
  padding: 12px 14px;
  border-radius: 16px;
  font-size: 13px;
}

.input-container {
  width: min(760px, 100%);
  justify-self: center;
  display: grid;
  gap: 8px;
}

.input-inner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: end;
  gap: 12px;
}

.input-form {
  width: 100%;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  padding: 8px 8px 8px 12px;
  border-radius: 16px;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.1);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input-wrapper:focus-within {
  border-color: rgba(15, 118, 110, 0.42);
  box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.08);
}

.message-input {
  flex: 1;
  min-height: 40px;
  max-height: 180px;
  resize: none;
  border: none;
  background: transparent;
  font: inherit;
  line-height: 1.65;
  color: #0f172a;
  padding: 10px 0 8px;
}

.message-input:focus {
  outline: none;
}

.message-input:disabled {
  cursor: not-allowed;
  color: #94a3b8;
}

.btn-send {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 12px;
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
  max-height: min(72vh, 880px);
  overflow: hidden;
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
  width: min(1040px, 100%);
  justify-self: center;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
  padding: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.05);
}

.details-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.details-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(300px, 0.92fr);
  gap: 12px;
  margin-bottom: 12px;
}

.details-panel-head h2 {
  font-size: 18px;
  color: #0f172a;
}

.details-panel-head p {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
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
    padding: 8px;
    gap: 8px;
  }

  .chat-topbar,
  .details-panel {
    border-radius: 16px;
  }

  .chat-topbar,
  .details-panel-head {
    flex-direction: column;
  }

  .topbar-side {
    width: 100%;
    justify-items: start;
  }

  .topbar-actions-menu {
    width: 100%;
  }

  .topbar-actions-toggle {
    width: 100%;
  }

  .topbar-actions-panel {
    position: static;
    width: 100%;
    margin-top: 8px;
  }

  .details-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .chat-thread {
    padding: 18px 12px 14px;
  }

  .empty-chat-card,
  .message-card,
  .detail-toggle {
    width: 100%;
  }

  .input-wrapper {
    padding: 10px 10px 10px 14px;
  }

  .input-inner {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .composer-tools {
    padding-bottom: 0;
  }

  .composer-tool-meta {
    padding-left: 0;
  }

  .workspace-bind-grid {
    grid-template-columns: 1fr;
  }

  .workspace-bind-shell,
  .input-container,
  .chat-stage,
  .error-banner {
    width: 100%;
  }
}
</style>
