<template>
  <div class="chat-container">
    <Navbar />

    <div class="chat-layout">
      <!-- 侧边栏 -->
      <div class="chat-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-header">
          <button @click="handleNewChat" class="btn-new-chat">
            <span class="icon">✨</span>
            <span class="text">新对话</span>
          </button>
          <button @click="toggleSidebar" class="btn-toggle">
            <span>{{ sidebarCollapsed ? '→' : '←' }}</span>
          </button>
        </div>

        <div class="sidebar-content">
          <div class="sessions-list">
            <div class="sessions-header">
              <h3>最近对话</h3>
            </div>
            <div
              v-for="session in sessions"
              :key="session.id"
              :class="['session-item', { active: session.id === currentSessionId }]"
              @click="switchSession(session.id)"
            >
              <div class="session-icon">💬</div>
              <div class="session-info">
                <div class="session-title">{{ session.title }}</div>
                <div class="session-time">{{ formatSessionTime(session.timestamp) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 主聊天区域 -->
      <div class="chat-main">
        <div class="messages-container" ref="messagesContainer">
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
              <button class="quick-action" @click="sendQuickMessage('帮我写一篇关于人工智能的文章')">
                <span class="action-icon">✍️</span>
                <span class="action-text">写作助手</span>
              </button>
              <button class="quick-action" @click="sendQuickMessage('解释一下量子计算的原理')">
                <span class="action-icon">🔬</span>
                <span class="action-text">知识问答</span>
              </button>
              <button class="quick-action" @click="sendQuickMessage('帮我分析这段代码')">
                <span class="action-icon">💻</span>
                <span class="action-text">代码分析</span>
              </button>
              <button class="quick-action" @click="sendQuickMessage('给我一些创意灵感')">
                <span class="action-icon">💡</span>
                <span class="action-text">创意灵感</span>
              </button>
            </div>
          </div>

          <div
            v-for="(message, index) in messages"
            :key="index"
            :class="['message', message.role]"
          >
            <div class="message-avatar">
              <span v-if="message.role === 'user'">👤</span>
              <span v-else class="ai-avatar">🤖</span>
            </div>
            <div class="message-content">
              <div class="message-text">{{ message.content }}</div>
              <div class="message-footer">
                <div class="message-time">{{ formatTime(message.timestamp) }}</div>
                <div class="message-actions">
                  <button class="action-btn" @click="copyMessage(message.content)" title="复制">
                    <span>📋</span>
                  </button>
                  <button class="action-btn" @click="regenerateMessage(index)" v-if="message.role === 'assistant'" title="重新生成">
                    <span>🔄</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-if="isLoading" class="message assistant">
            <div class="message-avatar">
              <span class="ai-avatar pulse">🤖</span>
            </div>
            <div class="message-content">
              <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        </div>

        <div class="input-container">
          <div v-if="error" class="error-message">
            <span class="error-icon">⚠️</span>
            <span>{{ error }}</span>
            <button @click="error = ''" class="error-close">×</button>
          </div>

          <form @submit.prevent="handleSendMessage" class="input-form">
            <div class="input-wrapper">
              <textarea
                v-model="inputMessage"
                @keydown.enter.exact.prevent="handleSendMessage"
                @input="autoResize"
                placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
                rows="1"
                ref="textareaRef"
                :disabled="isLoading"
                class="message-input"
              ></textarea>
              <button
                type="submit"
                :disabled="!inputMessage.trim() || isLoading"
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
import { ref, nextTick, onMounted } from 'vue'
import { useChatStore } from '@/store/chat'
import Navbar from '@/components/Navbar.vue'

const chatStore = useChatStore()

const messages = ref([])
const inputMessage = ref('')
const isLoading = ref(false)
const error = ref('')
const messagesContainer = ref(null)
const textareaRef = ref(null)
const currentSessionId = ref(null)
const sidebarCollapsed = ref(false)
const sessions = ref([])

onMounted(() => {
  // 创建新会话
  currentSessionId.value = `session_${Date.now()}`
  loadSessions()
})

const loadSessions = () => {
  // 从 localStorage 加载会话历史
  const savedSessions = localStorage.getItem('chat_sessions')
  if (savedSessions) {
    sessions.value = JSON.parse(savedSessions)
  }
}

const saveSessions = () => {
  localStorage.setItem('chat_sessions', JSON.stringify(sessions.value))
}

const handleSendMessage = async () => {
  if (!inputMessage.value.trim() || isLoading.value) return

  const userMessage = inputMessage.value.trim()
  inputMessage.value = ''
  error.value = ''

  // 重置 textarea 高度
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userMessage,
    timestamp: new Date()
  })

  // 更新会话
  updateSession(userMessage)

  scrollToBottom()

  isLoading.value = true

  try {
    // 调用聊天 API
    const response = await chatStore.sendMessage(currentSessionId.value, userMessage)

    // 添加助手回复
    messages.value.push({
      role: 'assistant',
      content: response.response || response.message || '抱歉，我没有理解你的问题。',
      timestamp: new Date()
    })

    scrollToBottom()
  } catch (err) {
    error.value = err.response?.data?.error || '发送消息失败，请重试'
    console.error('Chat error:', err)
  } finally {
    isLoading.value = false
  }
}

const sendQuickMessage = (message) => {
  inputMessage.value = message
  handleSendMessage()
}

const handleNewChat = () => {
  messages.value = []
  currentSessionId.value = `session_${Date.now()}`
  error.value = ''
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const switchSession = (sessionId) => {
  // TODO: 加载会话消息
  currentSessionId.value = sessionId
  console.log('Switch to session:', sessionId)
}

const updateSession = (lastMessage) => {
  const existingIndex = sessions.value.findIndex(s => s.id === currentSessionId.value)

  const sessionData = {
    id: currentSessionId.value,
    title: lastMessage.substring(0, 30) + (lastMessage.length > 30 ? '...' : ''),
    timestamp: new Date(),
    messageCount: messages.value.length
  }

  if (existingIndex >= 0) {
    sessions.value[existingIndex] = sessionData
  } else {
    sessions.value.unshift(sessionData)
  }

  // 只保留最近 20 个会话
  if (sessions.value.length > 20) {
    sessions.value = sessions.value.slice(0, 20)
  }

  saveSessions()
}

const copyMessage = async (content) => {
  try {
    await navigator.clipboard.writeText(content)
    // TODO: 显示复制成功提示
    console.log('Copied to clipboard')
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

const regenerateMessage = (index) => {
  // TODO: 实现重新生成功能
  console.log('Regenerate message at index:', index)
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

const formatSessionTime = (date) => {
  if (!date) return ''
  const d = new Date(date)
  const now = new Date()
  const diff = now - d

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return d.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--gray-50);
}

.chat-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 侧边栏样式 */
.chat-sidebar {
  width: 280px;
  background: white;
  border-right: 1px solid var(--gray-200);
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
}

.chat-sidebar.collapsed {
  width: 0;
  border-right: none;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--gray-200);
  display: flex;
  gap: 8px;
}

.btn-new-chat {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-sm);
}

.btn-new-chat:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.btn-new-chat .icon {
  font-size: 18px;
}

.btn-toggle {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-100);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
}

.btn-toggle:hover {
  background: var(--gray-200);
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.sessions-header {
  padding: 12px 8px;
}

.sessions-header h3 {
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
}

.session-item:hover {
  background: var(--gray-100);
}

.session-item.active {
  background: var(--primary-50);
  color: var(--primary-700);
}

.session-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 12px;
  color: var(--gray-500);
  margin-top: 2px;
}

/* 主聊天区域 */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(180deg, #f8f9ff 0%, #ffffff 100%);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 40px;
}

.welcome-animation {
  position: relative;
  margin-bottom: 32px;
}

.welcome-icon {
  position: relative;
  z-index: 2;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 50px;
  background: white;
  border-radius: 50%;
  box-shadow: var(--shadow-xl);
  animation: bounce 2s infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
}

.welcome-rings {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
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
  font-size: 28px;
  color: var(--gray-900);
  margin: 0 0 12px 0;
  font-weight: 700;
}

.empty-state p {
  font-size: 16px;
  color: var(--gray-600);
  margin: 0 0 32px 0;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-width: 500px;
  width: 100%;
}

.quick-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px;
  background: white;
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-base);
}

.quick-action:hover {
  border-color: var(--primary-500);
  background: var(--primary-50);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
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
.message {
  display: flex;
  gap: 16px;
  animation: fadeIn 0.3s ease-in;
  max-width: 800px;
}

.message.user {
  flex-direction: row-reverse;
  margin-left: auto;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  background: var(--gray-100);
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.message.user .message-avatar {
  background: var(--gradient-primary);
}

.ai-avatar {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.message-content {
  flex: 1;
  min-width: 0;
}

.message-text {
  padding: 16px 20px;
  border-radius: var(--radius-lg);
  background: white;
  color: var(--gray-900);
  line-height: 1.6;
  word-wrap: break-word;
  white-space: pre-wrap;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--gray-200);
}

.message.user .message-text {
  background: var(--gradient-primary);
  color: white;
  border: none;
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 4px;
}

.message-time {
  font-size: 12px;
  color: var(--gray-400);
}

.message-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-base);
}

.message:hover .message-actions {
  opacity: 1;
}

.action-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-100);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 14px;
}

.action-btn:hover {
  background: var(--gray-200);
  transform: scale(1.1);
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 6px;
  padding: 16px 20px;
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--gray-200);
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
  padding: 20px 24px;
  background: white;
  border-top: 1px solid var(--gray-200);
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
  max-width: 800px;
  margin: 0 auto;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 12px;
  background: var(--gray-50);
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-xl);
  transition: all var(--transition-base);
}

.input-wrapper:focus-within {
  border-color: var(--primary-500);
  background: white;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.message-input {
  flex: 1;
  padding: 8px 12px;
  border: none;
  background: transparent;
  font-size: 15px;
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
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-base);
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}

.btn-send:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
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
  .chat-sidebar {
    position: absolute;
    left: 0;
    top: 64px;
    height: calc(100vh - 64px);
    z-index: 100;
    box-shadow: var(--shadow-xl);
  }

  .chat-sidebar.collapsed {
    transform: translateX(-100%);
  }

  .quick-actions {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .messages-container {
    padding: 16px;
  }

  .input-container {
    padding: 16px;
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
</style>
