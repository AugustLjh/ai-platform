<template>
  <div class="chat-container">
    <div class="chat-main">
      <div class="chat-toolbar">
        <div class="chat-toolbar-inner">
          <div class="toolbar-left">
            <div class="model-select">
              <label>对话模型</label>
              <select
                v-model="selectedModelId"
                :disabled="modelsLoading || enabledModels.length === 0"
              >
                <option v-if="enabledModels.length === 0" value="">暂无可用模型</option>
                <option
                  v-for="model in enabledModels"
                  :key="model.id"
                  :value="model.id"
                >
                  {{ model.display_name }} ({{ model.model_id }})
                </option>
              </select>
            </div>
            <div class="model-select knowledge-select">
              <label>知识库</label>
              <select v-model="selectedKnowledgeBaseId" :disabled="knowledgeLoading">
                <option value="">不使用知识库</option>
                <option
                  v-for="kb in knowledgeBases"
                  :key="kb.id"
                  :value="kb.id"
                >
                  {{ kb.name }}
                </option>
              </select>
            </div>
            <div v-if="modelsError" class="model-error">
              {{ modelsError }}
            </div>
            <div v-if="knowledgeError" class="model-error">
              {{ knowledgeError }}
            </div>
          </div>
          <div class="toolbar-right">
            <router-link to="/models" class="btn-models">模型管理</router-link>
          </div>
        </div>
      </div>

      <div class="messages-container" ref="messagesContainer" @click="handleMessageClick">
        <div v-if="!canChat" class="model-alert">
          <div class="alert-icon">⚠️</div>
          <div class="alert-content">
            <div class="alert-title">未配置可用的聊天模型</div>
            <div class="alert-desc">请先添加并启用一个模型后再开始对话</div>
          </div>
          <router-link to="/models" class="alert-action">去配置</router-link>
        </div>

        <div v-if="messages.length === 0" class="empty-state">
          <div class="welcome-animation">
            <div class="welcome-icon">🤖</div>
            <div class="welcome-rings">
              <div class="ring ring-1"></div>
              <div class="ring ring-2"></div>
              <div class="ring ring-3"></div>
            </div>
          </div>
          <h2>你好！我是 AI 助手</h2>
          <p>我可以帮你解答问题、提供建议、进行创作等</p>

          <div class="quick-actions">
            <button class="quick-action" @click="openAgent('writing')">
              <span class="action-icon">✍️</span>
              <span class="action-text">写作助手</span>
            </button>
            <button class="quick-action" @click="openAgent('knowledge')">
              <span class="action-icon">🔬</span>
              <span class="action-text">知识问答</span>
            </button>
            <button class="quick-action" @click="openAgent('code')">
              <span class="action-icon">💻</span>
              <span class="action-text">代码分析</span>
            </button>
            <button class="quick-action" @click="openAgent('creative')">
              <span class="action-icon">💡</span>
              <span class="action-text">创意灵感</span>
            </button>
          </div>
        </div>

        <div
          v-for="(message, index) in messages"
          :key="index"
          :class="['thread-turn', `thread-turn-${message.role}`]"
        >
          <article class="thread-article" :data-turn-role="message.role">
            <div class="thread-shell">
              <div :class="['thread-message', `thread-message-${message.role}`]">
                <div v-if="message.role !== 'user'" class="message-avatar">
                  <span class="ai-avatar">AI</span>
                </div>
                <div class="message-content">
              <div
                v-if="message.streaming && !message.content"
                class="typing-indicator"
              >
                <span></span>
                <span></span>
                <span></span>
              </div>
                <div class="message-text">
                <template v-if="message.role === 'assistant' && message.renderMarkdown !== false">
                  <div
                    v-if="hasRenderedMarkdown(message)"
                    class="markdown prose markdown-new-styling wrap-break-word light"
                    :class="{ 'streaming-markdown': message.streaming }"
                  >
                    <MessageMarkdownBlocks
                      v-if="message.renderBlocks && message.renderBlocks.length > 0"
                      :blocks="message.renderBlocks"
                      block-key-prefix="stable-"
                    />
                    <MessageMarkdownBlocks
                      v-if="message.streamingRenderBlocks && message.streamingRenderBlocks.length > 0"
                      :blocks="message.streamingRenderBlocks"
                      block-key-prefix="preview-"
                    />
                  </div>
                </template>
                <template v-else-if="message.role === 'assistant' && message.renderMarkdown === false">
                  <pre class="plain-markdown">{{ message.content }}</pre>
                </template>
                <template v-else>
                  <div
                    class="user-bubble"
                    :data-multiline="message.content && message.content.includes('\n')"
                  >
                    <div class="user-content">{{ message.content }}</div>
                  </div>
                </template>
                <span v-if="message.streaming" class="stream-cursor">▍</span>
              </div>
                  <div
                    v-if="message.role === 'assistant' && message.retrievalStatus === 'no_hits'"
                    class="retrieval-banner"
                  >
                    <span class="retrieval-banner-label">知识库未命中</span>
                    <span v-if="message.knowledgeBaseName">{{ message.knowledgeBaseName }}</span>
                  </div>
                  <div
                    v-if="message.role === 'assistant' && message.citations && message.citations.length > 0"
                    class="citation-list"
                  >
                    <div class="citation-title">引用来源</div>
                    <div
                      v-for="(citation, citationIndex) in message.citations"
                      :key="`${message.id || index}-${citation.document_id || citationIndex}`"
                      class="citation-card"
                    >
                      <div class="citation-head">
                        <strong>{{ citation.title || '未命名文档' }}</strong>
                        <span v-if="Number.isFinite(citation.score)">相关度 {{ citation.score.toFixed(4) }}</span>
                      </div>
                      <div v-if="citation.source" class="citation-source">{{ citation.source }}</div>
                      <div
                        v-for="segment in citation.matched_segments || []"
                        :key="`${citation.document_id}-${segment.segment_index}`"
                        class="citation-segment"
                      >
                        <div class="citation-segment-meta">
                          <span>#{{ segment.segment_index }}</span>
                          <span>{{ segment.start_offset }} - {{ segment.end_offset }}</span>
                        </div>
                        <div class="citation-segment-content">{{ segment.content }}</div>
                      </div>
                    </div>
                  </div>
                  <div v-if="!message.streaming && message.role === 'assistant'" class="message-footer">
                    <div class="message-metrics">
                      <span v-if="message.routeScene" class="meta-chip">{{ message.routeScene }}</span>
                      <span v-if="message.resolvedModelName" class="meta-chip">{{ message.resolvedModelName }}</span>
                      <span v-if="message.fallbackUsed" class="meta-chip warning">已回退</span>
                      <span v-if="message.totalTokens" class="meta-chip">{{ formatTokenCount(message.totalTokens) }} tokens</span>
                      <span v-if="message.costUsd !== null && message.costUsd !== undefined" class="meta-chip">${{ formatCurrency(message.costUsd) }}</span>
                      <span v-if="message.timestamp" class="meta-chip subtle">{{ formatTime(message.timestamp) }}</span>
                    </div>
                    <div class="message-actions">
                      <button
                        class="action-btn"
                        :class="{ active: message.feedback?.label === 'like' }"
                        @click="submitMessageFeedback(message, 'like')"
                        title="有帮助"
                        aria-label="有帮助"
                      >
                        <span>👍</span>
                      </button>
                      <button
                        class="action-btn"
                        :class="{ active: message.feedback?.label === 'dislike' }"
                        @click="submitMessageFeedback(message, 'dislike')"
                        title="质量较差"
                        aria-label="质量较差"
                      >
                        <span>👎</span>
                      </button>
                      <button class="action-btn" @click="copyMessage(message.content)" title="复制" aria-label="复制">
                        <span>⧉</span>
                      </button>
                      <button class="action-btn" @click="regenerateMessage(index)" v-if="message.role === 'assistant'" title="重新生成" aria-label="重新生成">
                        <span>↻</span>
                      </button>
                    </div>
                  </div>
                  <div v-if="message.feedback?.comment" class="feedback-note">
                    反馈备注：{{ message.feedback.comment }}
                  </div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <div class="input-container">
        <div class="input-inner">
          <div v-if="error" class="error-message">
            <span class="error-icon">⚠️</span>
            <span>{{ error }}</span>
            <button @click="error = ''" class="error-close">×</button>
          </div>

          <form @submit.prevent="handleSendMessage" class="input-form">
            <div class="input-wrapper">
              <textarea
                v-model="inputMessage"
                @compositionstart="isComposing = true"
                @compositionend="isComposing = false"
                @keydown.enter.exact.prevent="handleEnterSend"
                @input="autoResize"
                :placeholder="canChat ? '输入消息... (Enter 发送，Shift+Enter 换行)' : '请先配置聊天模型'"
                rows="1"
                ref="textareaRef"
                :disabled="isLoading || !canChat"
                class="message-input"
              ></textarea>
              <button
                type="submit"
                :disabled="!inputMessage.trim() || isLoading || !canChat"
                class="btn-send"
              >
                <span v-if="!isLoading" class="send-icon">
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
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { chatAPI } from '@/api'
import { useChatStore } from '@/store/chat'
import { useModelsStore } from '@/store/models'
import { useKnowledgeStore } from '@/store/knowledge'
import MessageMarkdownBlocks from '@/components/MessageMarkdownBlocks.vue'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const modelsStore = useModelsStore()
const knowledgeStore = useKnowledgeStore()

const inputMessage = ref('')
const isLoading = ref(false)
const isComposing = ref(false)
const error = ref('')
const messagesContainer = ref(null)
const textareaRef = ref(null)

const messages = computed(() => chatStore.currentSession?.messages || [])
const latestMessageSignature = computed(() => {
  const lastMessage = messages.value[messages.value.length - 1]
  if (!lastMessage) return ''
  return `${messages.value.length}:${lastMessage.role}:${lastMessage.streaming ? 1 : 0}:${lastMessage.content?.length || 0}:${lastMessage.rawContent?.length || 0}:${lastMessage.renderBlocks?.length || 0}`
})

const enabledModels = computed(() => modelsStore.enabledModels)
const selectedModelId = computed({
  get: () => modelsStore.selectedModelId,
  set: (value) => modelsStore.selectModel(value)
})
const selectedModel = computed(() => modelsStore.selectedModel)
const modelsLoading = computed(() => modelsStore.loading)
const modelsError = computed(() => modelsStore.error)
const canChat = computed(() => enabledModels.value.length > 0 && !!selectedModel.value)

const knowledgeBases = computed(() => knowledgeStore.knowledgeBases)
const knowledgeLoading = computed(() => knowledgeStore.loading)
const knowledgeError = computed(() => knowledgeStore.error)
const selectedKnowledgeBaseId = computed({
  get: () => chatStore.config.knowledgeBaseId,
  set: (value) => {
    chatStore.updateConfig({
      knowledgeBaseId: value || '',
      useRAG: value ? true : chatStore.config.useRAG
    })
  }
})

onMounted(async () => {
  try {
    await modelsStore.fetchModels()
  } catch (err) {
    console.error('Failed to load models:', err)
  }

  try {
    await knowledgeStore.fetchKnowledgeBases(1, 100)
  } catch (err) {
    console.error('Failed to load knowledge bases:', err)
  }

  if (chatStore.sessions.length === 0) {
    try {
      await chatStore.fetchSessions()
    } catch (err) {
      console.error('Failed to load chat sessions:', err)
    }
  }

  if (!chatStore.currentSessionId) {
    const firstSession = chatStore.sortedSessions[0]
    if (firstSession) {
      chatStore.loadSession(firstSession.id)
    }
  }

  const requestedSession = route.query.session
  if (requestedSession && chatStore.sessions.some((session) => session.id === requestedSession)) {
    chatStore.loadSession(requestedSession)
  }

})

watch(
  () => messages.value.length,
  () => scrollToBottom()
)

watch(
  () => latestMessageSignature.value,
  () => scrollToBottom()
)

watch(
  () => route.query.session,
  (sessionId) => {
    if (sessionId && chatStore.sessions.some((session) => session.id === sessionId)) {
      chatStore.loadSession(sessionId)
    }
  }
)

const handleSendMessage = async () => {
  if (!inputMessage.value.trim() || isLoading.value) return
  if (!canChat.value) {
    error.value = '请先配置聊天模型'
    return
  }

  const userMessage = inputMessage.value.trim()
  inputMessage.value = ''
  error.value = ''

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  scrollToBottom()
  isLoading.value = true

  try {
    await chatStore.sendMessage(userMessage, {
      model: selectedModel.value?.id
    })
    scrollToBottom()
  } catch (err) {
    error.value = err.response?.data?.error || '发送消息失败，请重试'
    console.error('Chat error:', err)
  } finally {
    isLoading.value = false
  }
}

const handleEnterSend = (event) => {
  if (isComposing.value || event?.isComposing || event?.keyCode === 229) {
    return
  }
  handleSendMessage()
}

const openAgent = (agent) => {
  router.push(`/agents/${agent}`)
}

const copyMessage = async (content) => {
  try {
    await navigator.clipboard.writeText(content)
    console.log('Copied to clipboard')
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

const handleMessageClick = async (event) => {
  const target = event.target
  const button = target?.closest?.('.code-copy-btn')
  if (!button) return
  const wrapper = button.closest('.code-block')
  if (!wrapper) return
  const codeEl = wrapper.querySelector('code')
  if (!codeEl) return
  try {
    await navigator.clipboard.writeText(codeEl.innerText)
    const original = button.textContent
    button.textContent = '已复制'
    setTimeout(() => {
      button.textContent = original || '复制'
    }, 1500)
  } catch (err) {
    console.error('Failed to copy code:', err)
  }
}

const regenerateMessage = (index) => {
  console.log('Regenerate message at index:', index)
}

const submitMessageFeedback = async (message, label) => {
  if (!message?.id) {
    return
  }

  try {
    const comment = label === 'dislike'
      ? (window.prompt('记录本次回答的问题（可选）：', message.feedback?.comment || '') || '')
      : ''
    await chatAPI.saveMessageFeedback(message.id, {
      label,
      rating: label === 'like' ? 5 : 1,
      comment
    })
    await chatStore.fetchHistory(chatStore.currentSessionId)
  } catch (err) {
    error.value = err.response?.data?.error || err.response?.data?.detail || '保存反馈失败'
  }
}

const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = textareaRef.value.scrollHeight + 'px'
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const formatTime = (date) => {
  if (!date) return ''
  const d = new Date(date)
  const hours = d.getHours().toString().padStart(2, '0')
  const minutes = d.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
}

const formatCurrency = (value) => {
  const parsed = Number(value || 0)
  return parsed.toFixed(4)
}

const formatTokenCount = (value) => {
  const parsed = Number(value || 0)
  if (parsed >= 1000) {
    return `${(parsed / 1000).toFixed(1)}k`
  }
  return `${parsed}`
}

const hasRenderedMarkdown = (message) => {
  return Boolean(
    (message.renderBlocks && message.renderBlocks.length > 0) ||
    (message.streamingRenderBlocks && message.streamingRenderBlocks.length > 0)
  )
}

</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gpt-bg);
  overflow: hidden;
}

.message-text {
  display: flex;
  flex-direction: column;
  white-space: normal;
  word-break: break-word;
}

.streaming-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  color: #1e293b;
}

.streaming-markdown {
  color: #1e293b;
}

.retrieval-banner {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: #fff7ed;
  border: 1px solid #fdba74;
  color: #9a3412;
  font-size: 12px;
  width: fit-content;
}

.retrieval-banner-label {
  font-weight: 700;
}

.citation-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.citation-title {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.citation-card {
  background: #f8fafc;
  border: 1px solid #dbe4ee;
  border-radius: 14px;
  padding: 12px 14px;
}

.citation-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: #0f172a;
  font-size: 13px;
}

.citation-source {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  word-break: break-all;
}

.citation-segment {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #cbd5e1;
}

.citation-segment-meta {
  display: flex;
  gap: 10px;
  color: #64748b;
  font-size: 11px;
  margin-bottom: 6px;
}

.citation-segment-content {
  color: #1e293b;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.plain-text {
  white-space: pre-wrap;
}

.plain-markdown {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  background: #f7f7f8;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  margin: 0;
}

.message-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.meta-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 600;
}

.meta-chip.warning {
  background: #fff7ed;
  color: #c2410c;
}

.feedback-note {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.markdown {
  line-height: 1.7;
  width: 100%;
  font-size: 15px;
  color: #111827;
  white-space: normal;
}

:deep(.wrap-break-word) {
  word-break: break-word;
}

:deep(.markdown-new-styling > :first-child) {
  margin-top: 0;
}

:deep(.markdown-new-styling > :last-child) {
  margin-bottom: 0;
}

:deep(.markdown > * + *) {
  margin-top: 8px;
}

:deep(.markdown p) {
  margin: 0;
}

:deep(.markdown h1),
:deep(.markdown h2),
:deep(.markdown h3),
:deep(.markdown h4) {
  margin: 0;
  font-weight: 600;
}

:deep(.markdown ul),
:deep(.markdown ol) {
  padding-left: 22px;
  margin: 0;
}

:deep(.markdown li) {
  margin: 0;
}

:deep(.markdown a) {
  color: var(--primary-600);
  text-decoration: underline;
}

:deep(.markdown .streaming-link-pending) {
  color: var(--primary-600);
  text-decoration: underline;
}

:deep(.markdown blockquote) {
  border-left: 3px solid #e5e7eb;
  padding-left: 12px;
  color: var(--gray-600);
  margin: 0;
}

:deep(.markdown hr) {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 0;
}

:deep(.code-block) {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  background: #f7f7f8;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  overflow: hidden;
  margin: 0;
}

:deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 2px 8px;
  min-height: 30px;
  background: #f7f7f8;
  color: #6b7280;
  font-size: 12px;
  border-bottom: 1px solid #e5e7eb;
}

:deep(.code-copy-btn) {
  border: 1px solid #d1d5db;
  background: #fff;
  color: #6b7280;
  padding: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}

:deep(.code-copy-btn:hover) {
  background: #e5e7eb;
}

:deep(.code-block pre) {
  margin: 0;
  flex: 1 1 auto;
  padding: 8px 12px;
  overflow-x: auto;
}

:deep(.markdown pre) {
  margin: 0;
}

:deep(.code-block code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  line-height: 1.5;
  display: block;
}

:deep(.hljs) {
  background: transparent;
  color: #111827;
  padding: 0;
}

:deep(.hljs-comment),
:deep(.hljs-quote) {
  color: #6b7280;
  font-style: italic;
}

:deep(.hljs-keyword),
:deep(.hljs-selector-tag),
:deep(.hljs-literal) {
  color: #7c3aed;
}

:deep(.hljs-string),
:deep(.hljs-doctag) {
  color: #059669;
}

:deep(.hljs-number),
:deep(.hljs-regexp) {
  color: #b45309;
}

:deep(.hljs-title),
:deep(.hljs-section),
:deep(.hljs-function) {
  color: #2563eb;
}

:deep(.hljs-attr),
:deep(.hljs-attribute),
:deep(.hljs-variable) {
  color: #b91c1c;
}

:deep(.hljs-built_in),
:deep(.hljs-type),
:deep(.hljs-symbol),
:deep(.hljs-meta) {
  color: #0f766e;
}

:deep(.markdown code) {
  background: #f1f1f1;
  padding: 1px 3px;
  border-radius: 4px;
}

.stream-cursor {
  display: inline-block;
  margin-left: 2px;
  color: var(--primary-600);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  to {
    visibility: hidden;
  }
}

/* 主聊天区域 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--gpt-bg);
  min-width: 0;
  position: relative;
  --thread-content-margin: 16px;
  --thread-content-max-width: 40rem;
  width: 100%;
  max-width: 100%;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-bottom: 1px solid var(--gpt-border);
  background: var(--gpt-panel);
}

.chat-toolbar-inner {
  width: 100%;
  max-width: var(--thread-content-max-width);
  padding: 10px var(--thread-content-margin);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}

.model-select {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-select label {
  font-size: 13px;
  color: var(--gray-600);
}

.model-select select {
  padding: 6px 10px;
  border: 1px solid var(--gray-300);
  border-radius: var(--radius-md);
  font-size: 13px;
  background: white;
  color: var(--gray-800);
}

.knowledge-select select {
  min-width: 180px;
}

.model-error {
  font-size: 12px;
  color: var(--error);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-models {
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--gray-100);
  color: var(--gray-700);
  text-decoration: none;
  font-size: 12px;
  font-weight: 600;
  transition: all var(--transition-base);
}

.btn-models:hover {
  background: var(--gray-200);
  color: var(--gray-900);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  width: 100%;
  max-width: 100%;
  padding: 12px var(--thread-content-margin) 40px;
  display: flex;
  flex-direction: column;
  gap: 0;
  align-items: stretch;
  font-size: 15px;
}

@media (min-width: 640px) {
  .chat-main {
    --thread-content-margin: 24px;
  }
}

@media (min-width: 1024px) {
  .chat-main {
    --thread-content-margin: 32px;
    --thread-content-max-width: 48rem;
  }
}

.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 999px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 40px 20px;
}

.model-alert {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  border-radius: 12px;
  margin: 0 auto 16px;
  max-width: 760px;
}

.alert-icon {
  font-size: 20px;
}

.alert-content {
  flex: 1;
}

.alert-title {
  font-weight: 600;
  color: var(--gray-800);
  margin-bottom: 4px;
}

.alert-desc {
  font-size: 12px;
  color: var(--gray-600);
}

.alert-action {
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--primary-500);
  color: white;
  text-decoration: none;
  font-size: 12px;
  font-weight: 600;
}

.welcome-animation {
  position: relative;
  margin-bottom: 16px;
}

.welcome-icon {
  position: relative;
  z-index: 2;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  background: var(--gpt-panel);
  border-radius: 20px;
  border: 1px solid var(--gpt-border);
}

.welcome-rings {
  display: none;
}

.ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 2px solid var(--primary-300);
  border-radius: 50%;
  opacity: 0;
  animation: ripple 3s infinite;
}

.ring-1 {
  width: 120px;
  height: 120px;
  animation-delay: 0s;
}

.ring-2 {
  width: 150px;
  height: 150px;
  animation-delay: 1s;
}

.ring-3 {
  width: 180px;
  height: 180px;
  animation-delay: 2s;
}

@keyframes ripple {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.5);
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(1.5);
  }
}

.empty-state h2 {
  font-size: 24px;
  color: var(--gray-900);
  margin: 8px 0 8px 0;
  font-weight: 600;
}

.empty-state p {
  font-size: 14px;
  color: var(--gray-600);
  margin: 0 0 20px 0;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  max-width: 520px;
  width: 100%;
}

.quick-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px;
  background: var(--gpt-panel);
  border: 1px solid var(--gpt-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all var(--transition-base);
}

.quick-action:hover {
  border-color: var(--primary-500);
  background: #f0fdf8;
}

.action-icon {
  font-size: 32px;
}

.action-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-700);
}

/* 消息样式 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-row {
  width: 100%;
  padding: 6px 0;
  display: flex;
  justify-content: center;
}

.message-row.assistant {
  background: var(--gpt-bg);
}

.message-row.user {
  background: var(--gpt-bg);
}

.message {
  max-width: var(--thread-content-max-width);
  width: 100%;
  margin: 0 auto;
  padding: 0;
  display: flex;
  gap: 12px;
  align-items: flex-start;
  animation: fadeIn 0.2s ease-in;
}

.message.user {
  flex-direction: row-reverse;
  gap: 0;
  justify-content: flex-end;
}

.message-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  background: var(--primary-500);
  color: white;
  flex-shrink: 0;
}

.message.user .message-avatar {
  display: none;
}

.ai-avatar {
  color: white;
}

.message-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.message-row.assistant .message-content {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
}

.message.user .message-content {
  align-items: flex-end;
}

.message-text {
  display: flex;
  flex-direction: column;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--gray-900);
  line-height: 1.6;
  word-wrap: break-word;
  white-space: normal;
  box-shadow: none;
  border: none;
}

.message.user .message-text {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  color: var(--gray-900);
  max-width: 100%;
  text-align: left;
}

.user-bubble {
  background: #f3f4f6;
  color: #111827;
  border-radius: 18px;
  padding: 8px 14px;
  max-width: 100%;
  border: none;
}

.user-bubble[data-multiline="true"] {
  padding-top: 10px;
  padding-bottom: 10px;
}

.user-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 15px;
  line-height: 1.6;
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-top: 8px;
  padding: 0;
  gap: 8px;
}

.message.user .message-footer {
  justify-content: flex-end;
  gap: 8px;
}

.message-time {
  display: none;
}

.message-time {
  font-size: 12px;
  color: var(--gray-500);
}

.message-actions {
  display: flex;
  gap: 6px;
  opacity: 1;
}

.action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 14px;
  color: #6b7280;
}

.action-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

.action-btn.active {
  background: #e0f2fe;
  color: #0369a1;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 6px;
  padding: 10px 0;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  border: none;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--gray-400);
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.7;
  }
  30% {
    transform: translateY(-10px);
    opacity: 1;
  }
}

/* 输入区域 */
.input-container {
  padding: 12px 0 18px;
  background: var(--gpt-bg);
  border-top: 1px solid var(--gpt-border);
  box-shadow: 0 -6px 16px rgba(0, 0, 0, 0.04);
}

.input-inner {
  width: 100%;
  max-width: var(--thread-content-max-width);
  margin: 0 auto;
  padding: 0 var(--thread-content-margin);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: var(--radius-lg);
  margin-bottom: 12px;
  font-size: 14px;
  animation: shake 0.5s ease;
}

.error-icon {
  font-size: 16px;
}

.error-close {
  margin-left: auto;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 20px;
  color: #991B1B;
  border-radius: var(--radius-md);
  transition: background var(--transition-base);
}

.error-close:hover {
  background: rgba(0, 0, 0, 0.1);
}

.input-form {
  width: 100%;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 8px 10px;
  background: var(--gpt-input-bg);
  border: 1px solid var(--gray-300);
  border-radius: 12px;
  transition: all var(--transition-base);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.input-wrapper:focus-within {
  border-color: var(--primary-500);
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.15);
}

.message-input {
  flex: 1;
  padding: 6px 2px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  max-height: 200px;
  line-height: 1.5;
  color: var(--gray-900);
}

.message-input:focus {
  outline: none;
}

.message-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-send {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-500);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--transition-base);
  flex-shrink: 0;
  box-shadow: none;
}

.btn-send:hover:not(:disabled) {
  background: var(--primary-600);
}

.btn-send:active:not(:disabled) {
  transform: translateY(0);
}

.btn-send:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.send-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .quick-actions {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .messages-container {
    padding: 16px var(--thread-content-margin) 32px;
  }

  .input-container {
    padding: 12px 0 18px;
  }

  .message {
    max-width: 100%;
  }

  .empty-state h2 {
    font-size: 24px;
  }

  .empty-state p {
    font-size: 14px;
  }

  .quick-action {
    padding: 16px;
  }

  .action-icon {
    font-size: 28px;
  }
}

.message-row.assistant .message {
  max-width: 100%;
}

.message-row.assistant .message-content,
.message-row.assistant .message-text {
  width: 100%;
}
</style>
