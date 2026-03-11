<template>
  <div class="history-page">
    <header class="history-header">
      <div>
        <p class="eyebrow">Conversation Archive</p>
        <h1>历史记录</h1>
        <p>历史消息保存在数据库中，助手回复按 Markdown 渲染展示。</p>
      </div>
      <div v-if="activeSession" class="header-actions">
        <button class="btn-danger" @click="handleDelete">删除对话</button>
        <button class="btn-continue" @click="continueChat">继续对话</button>
      </div>
    </header>

    <div v-if="!activeSession" class="placeholder">
      <div class="placeholder-icon">💬</div>
      <h3>暂无可查看的对话</h3>
      <p>请先选择一条对话，或直接回到聊天页继续创建。</p>
      <button class="btn-continue" @click="goToChat">去聊天</button>
    </div>

    <section v-else class="history-detail">
      <div class="detail-header">
        <div>
          <h3>{{ activeSession.title || '未命名对话' }}</h3>
          <p>创建于 {{ formatFullTime(activeSession.createdAt) }}</p>
        </div>
        <div class="session-badge">
          {{ (historyMessages || []).length }} 条消息
        </div>
      </div>

      <div v-if="historyMessages.length === 0" class="detail-empty">
        <div class="empty-icon">🫥</div>
        <h4>该对话暂无消息</h4>
        <p>点击继续对话开始聊天</p>
      </div>

      <div v-else class="message-list" @click="handleMessageClick">
        <article
          v-for="(message, index) in historyMessages"
          :key="message.id || index"
          :class="['message-card', message.role]"
        >
          <div class="message-head">
            <div class="message-role">{{ message.role === 'user' ? '用户' : '助手' }}</div>
            <div class="message-time">{{ formatFullTime(message.timestamp) }}</div>
          </div>

          <div v-if="message.role === 'assistant' && message.renderMarkdown !== false" class="message-body markdown wrap-break-word" v-html="message.historyHtml"></div>
          <pre v-else-if="message.role === 'assistant'" class="message-body plain-markdown">{{ message.content }}</pre>
          <div v-else class="message-body user-content">{{ message.content }}</div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/store/chat'
import { useToastStore } from '@/store/toast'
import { renderMarkdown } from '@/utils/markdown'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const toastStore = useToastStore()

const activeSession = computed(() => chatStore.currentSession)
const historyMessages = computed(() => {
  const list = activeSession.value?.messages || []
  return list.map((message) => ({
    ...message,
    historyHtml: message.htmlContent || renderMarkdown(message.content || '')
  }))
})

onMounted(() => {
  const bootstrap = async () => {
    if (chatStore.sessions.length === 0) {
      try {
        await chatStore.fetchSessions()
      } catch (error) {
        console.error('Failed to load chat sessions:', error)
      }
    }

    if (!chatStore.currentSessionId) {
      const firstSession = chatStore.sortedSessions[0]
      if (firstSession) {
        await chatStore.loadSession(firstSession.id)
      }
    }

    const requestedSession = route.query.session
    if (requestedSession && chatStore.sessions.some((session) => session.id === requestedSession)) {
      await chatStore.loadSession(requestedSession)
    }
  }

  bootstrap()
})

watch(
  () => route.query.session,
  async (sessionId) => {
    if (sessionId && chatStore.sessions.some((session) => session.id === sessionId)) {
      await chatStore.loadSession(sessionId)
    }
  }
)

const continueChat = () => {
  if (!chatStore.currentSessionId) return
  router.push({ path: '/chat', query: { session: chatStore.currentSessionId } })
}

const goToChat = () => {
  router.push({ path: '/chat' })
}

const handleDelete = async () => {
  if (!chatStore.currentSessionId) return
  if (!confirm('确定要删除此对话吗？此操作无法撤销。')) return
  try {
    await chatStore.deleteSession(chatStore.currentSessionId)
    toastStore.showToast({ type: 'success', message: '对话已删除' })
  } catch (error) {
    console.error('Failed to delete session:', error)
    toastStore.showToast({ type: 'error', message: '删除对话失败' })
  }
}

const handleMessageClick = async (event) => {
  const button = event.target?.closest?.('.code-copy-btn')
  if (!button) return
  const wrapper = button.closest('.code-block')
  const codeEl = wrapper?.querySelector('code')
  if (!codeEl) return

  try {
    await navigator.clipboard.writeText(codeEl.innerText)
    const original = button.textContent
    button.textContent = '已复制'
    setTimeout(() => {
      button.textContent = original || '复制'
    }, 1500)
  } catch (error) {
    console.error('Failed to copy code block:', error)
  }
}

const formatFullTime = (date) => {
  if (!date) return ''
  const d = new Date(date)
  return d.toLocaleString('zh-CN')
}
</script>

<style scoped>
.history-page {
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow: auto;
  padding: 32px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 24rem),
    linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.history-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #2563eb;
}

.history-header h1 {
  margin: 0;
  font-size: 30px;
  color: #0f172a;
}

.history-header p {
  margin: 10px 0 0;
  color: #64748b;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.placeholder {
  min-height: calc(100vh - 220px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #64748b;
  gap: 12px;
}

.placeholder-icon {
  font-size: 42px;
}

.history-detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(203, 213, 225, 0.9);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
}

.detail-header h3 {
  margin: 0;
  font-size: 24px;
  color: #0f172a;
}

.detail-header p {
  margin: 8px 0 0;
  font-size: 13px;
  color: #64748b;
}

.session-badge {
  padding: 8px 12px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

.btn-continue,
.btn-danger {
  min-height: 40px;
  padding: 0 16px;
  border: none;
  border-radius: 12px;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

.btn-continue {
  background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
}

.btn-danger {
  background: linear-gradient(135deg, #e11d48 0%, #fb7185 100%);
}

.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 32px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.84);
  border: 1px dashed #cbd5e1;
  color: #64748b;
  gap: 8px;
}

.empty-icon {
  font-size: 34px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-card {
  padding: 18px 20px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.06);
}

.message-card.user {
  border-left: 4px solid #14b8a6;
}

.message-card.assistant {
  border-left: 4px solid #3b82f6;
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
  color: #0f172a;
}

.message-time {
  font-size: 12px;
  color: #64748b;
}

.message-body {
  color: #1e293b;
  line-height: 1.75;
  white-space: normal;
}

.user-content,
.plain-markdown {
  white-space: pre-wrap;
  word-break: break-word;
}

.plain-markdown {
  margin: 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

:deep(.wrap-break-word) {
  word-break: break-word;
}

:deep(.markdown > :first-child) {
  margin-top: 0;
}

:deep(.markdown > :last-child) {
  margin-bottom: 0;
}

:deep(.markdown p) {
  margin: 0;
}

:deep(.markdown > * + *) {
  margin-top: 10px;
}

:deep(.markdown ul),
:deep(.markdown ol) {
  margin: 0;
  padding-left: 22px;
}

:deep(.markdown blockquote) {
  margin: 0;
  padding-left: 12px;
  border-left: 3px solid #cbd5e1;
  color: #475569;
}

:deep(.markdown a) {
  color: #2563eb;
}

:deep(.markdown code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f1f5f9;
}

:deep(.code-block) {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #f8fafc;
}

:deep(.code-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 12px;
}

:deep(.code-copy-btn) {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  border-radius: 8px;
  padding: 4px 8px;
  cursor: pointer;
}

:deep(.code-block pre) {
  margin: 0;
  padding: 12px 14px;
  overflow-x: auto;
}

:deep(.hljs) {
  background: transparent;
  padding: 0;
}

@media (max-width: 960px) {
  .history-page {
    padding: 24px 16px;
  }

  .history-header,
  .detail-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    justify-content: flex-start;
  }

  .message-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
