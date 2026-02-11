<template>
  <div class="history-container">
    <div class="history-header">
      <h1>历史记录</h1>
      <p>历史记录保存在数据库中。</p>
    </div>

    <div v-if="!activeSession" class="placeholder">
      <div class="placeholder-icon">💬</div>
      <h3>暂无可查看的对话</h3>
      <p>请在左侧栏选择一条对话查看详情。</p>
      <button class="btn-continue" @click="goToChat">去聊天</button>
    </div>

    <div v-else class="history-detail">
      <div class="detail-header">
        <div>
          <h3>{{ activeSession.title || '未命名对话' }}</h3>
          <p>创建于 {{ formatFullTime(activeSession.createdAt) }}</p>
        </div>
        <div class="detail-actions">
          <button class="btn-danger" @click="handleDelete">删除对话</button>
          <button class="btn-continue" @click="continueChat">继续对话</button>
        </div>
      </div>

      <div v-if="(activeSession.messages || []).length === 0" class="detail-empty">
        <div class="empty-icon">🫥</div>
        <h4>该对话暂无消息</h4>
        <p>点击继续对话开始聊天</p>
      </div>

      <div v-else class="message-list">
        <div
          v-for="(message, index) in activeSession.messages || []"
          :key="index"
          :class="['message-item', message.role]"
        >
          <div class="message-role">{{ message.role === 'user' ? '用户' : '助手' }}</div>
          <div class="message-content">{{ message.content }}</div>
          <div class="message-time">{{ formatFullTime(message.timestamp) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/store/chat'
import { useToastStore } from '@/store/toast'

const router = useRouter()
const chatStore = useChatStore()
const toastStore = useToastStore()

const activeSession = computed(() => chatStore.currentSession)

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
  }

  bootstrap()
})

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

const formatFullTime = (date) => {
  if (!date) return ''
  const d = new Date(date)
  return d.toLocaleString('zh-CN')
}
</script>

<style scoped>
.history-container {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gray-50);
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 32px;
  gap: 24px;
}

.history-header h1 {
  margin: 0 0 6px 0;
  font-size: 28px;
}

.history-header p {
  margin: 0;
  color: var(--gray-500);
  font-size: 14px;
}

.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--gray-500);
  text-align: center;
  gap: 12px;
}

.placeholder-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-header h3 {
  margin: 0 0 6px 0;
}

.detail-header p {
  margin: 0;
  color: var(--gray-500);
  font-size: 12px;
}

.btn-continue {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--gradient-primary);
  color: white;
  font-weight: 600;
  cursor: pointer;
}

.btn-danger {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: #ef4444;
  color: white;
  font-weight: 600;
  cursor: pointer;
}

.btn-danger:hover {
  background: #dc2626;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 32px;
  border-radius: var(--radius-lg);
  background: #f9fafb;
  border: 1px dashed #e5e7eb;
  color: var(--gray-500);
  gap: 6px;
}

.detail-empty .empty-icon {
  font-size: 32px;
}

.message-item {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: white;
  box-shadow: var(--shadow-sm);
}

.message-item.user {
  border-left: 4px solid var(--primary-400);
}

.message-item.assistant {
  border-left: 4px solid var(--gray-300);
}

.message-role {
  font-size: 12px;
  color: var(--gray-500);
  margin-bottom: 6px;
}

.message-content {
  font-size: 14px;
  color: var(--gray-800);
  line-height: 1.6;
}

.message-time {
  font-size: 11px;
  color: var(--gray-400);
  margin-top: 8px;
}

</style>
