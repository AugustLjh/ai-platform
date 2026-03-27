<template>
  <aside class="app-sidebar">
    <div class="sidebar-header">
      <router-link to="/chat" class="sidebar-brand" aria-label="回到聊天">
        <span class="brand-icon">🤖</span>
        <span class="brand-text">AI Platform</span>
      </router-link>
    </div>

    <div class="sidebar-scroll">
      <button class="btn-new-chat" @click="handleNewChat">
        <span class="icon">✨</span>
        <span class="text">新对话</span>
      </button>

      <nav class="sidebar-nav">
        <router-link to="/chat" class="sidebar-nav-item">
          <span class="nav-icon">💬</span>
          <span>聊天</span>
        </router-link>
        <router-link to="/history" class="sidebar-nav-item">
          <span class="nav-icon">🕘</span>
          <span>历史记录</span>
        </router-link>
        <router-link to="/agents" class="sidebar-nav-item">
          <span class="nav-icon">🧭</span>
          <span>智能体</span>
        </router-link>
        <router-link to="/costs" class="sidebar-nav-item">
          <span class="nav-icon">💵</span>
          <span>成本统计</span>
        </router-link>
        <router-link to="/knowledge" class="sidebar-nav-item">
          <span class="nav-icon">📚</span>
          <span>知识库</span>
        </router-link>
        <router-link to="/models" class="sidebar-nav-item">
          <span class="nav-icon">🤖</span>
          <span>模型管理</span>
        </router-link>
        <router-link to="/mcp" class="sidebar-nav-item">
          <span class="nav-icon">🔌</span>
          <span>MCP</span>
        </router-link>
        <router-link to="/settings" class="sidebar-nav-item">
          <span class="nav-icon">⚙️</span>
          <span>设置</span>
        </router-link>
        <router-link to="/profile" class="sidebar-nav-item">
          <span class="nav-icon">👤</span>
          <span>个人中心</span>
        </router-link>
      </nav>

      <div class="sessions-header">
        <h3>最近对话</h3>
      </div>

      <div class="sessions-search">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索对话..."
          class="search-input"
          @input="handleSearch"
        />
        <button
          v-if="searchQuery"
          type="button"
          class="search-clear"
          @click="clearSearch"
          aria-label="清除搜索"
        >
          ×
        </button>
      </div>

      <div class="sessions-list">
        <div v-if="sessions.length === 0" class="sessions-empty">暂无对话，点击新对话开始</div>
        <div v-for="session in sessions" :key="session.id" class="session-row">
          <button
            type="button"
            :class="['session-item', { active: session.id === currentSessionId }]"
            @click="switchSession(session.id)"
          >
            <div class="session-icon">💬</div>
            <div class="session-info">
              <div class="session-title">{{ session.title || '未命名对话' }}</div>
              <div class="session-time">{{ formatSessionTime(session.updatedAt || session.createdAt) }}</div>
            </div>
          </button>
          <button
            type="button"
            class="session-delete"
            title="删除对话"
            aria-label="删除对话"
            @click.stop="handleDeleteSession(session.id)"
          >
            🗑️
          </button>
        </div>
      </div>

      <div class="sessions-footer">
        <button
          v-if="hasMore"
          type="button"
          class="btn-load-more"
          :disabled="loadingMore"
          @click="loadMoreSessions"
        >
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
        <div v-else-if="sessions.length > 0" class="sessions-end">没有更多对话了</div>
      </div>
    </div>

    <div class="sidebar-footer" v-if="user">
      <div class="user-info">
        <div class="user-avatar">{{ userInitial }}</div>
        <div class="user-meta">
          <div class="user-name">{{ user.email || '用户' }}</div>
          <div class="user-subtitle">已登录</div>
        </div>
      </div>
      <button class="btn-logout" type="button" @click="handleLogout">退出登录</button>
    </div>
  </aside>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useChatStore } from '@/store/chat'
import { useAuthStore } from '@/store/auth'
import { useToastStore } from '@/store/toast'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const authStore = useAuthStore()
const toastStore = useToastStore()

const sessions = computed(() => chatStore.sortedSessions)
const currentSessionId = computed(() => chatStore.currentSessionId)
const user = computed(() => authStore.user)

const searchQuery = ref('')
const pageSize = 50
const offset = ref(0)
const hasMore = ref(true)
const loadingMore = ref(false)
let searchTimer = null

const userInitial = computed(() => {
  if (!user.value || !user.value.email) return '?'
  return user.value.email.charAt(0).toUpperCase()
})

const handleNewChat = async () => {
  try {
    const session = await chatStore.createSession()
    if (session?.id) {
      router.push({ path: '/chat', query: { session: session.id } })
      toastStore.showToast({ type: 'success', message: '已创建新对话' })
    } else {
      router.push({ path: '/chat' })
    }
  } catch (error) {
    console.error('Failed to create session:', error)
    toastStore.showToast({ type: 'error', message: '创建对话失败' })
    router.push({ path: '/chat' })
  }
}

const switchSession = (sessionId) => {
  chatStore.loadSession(sessionId)
  const targetPath = route.path === '/history' ? '/history' : '/chat'
  router.push({ path: targetPath, query: { session: sessionId } })
}

const handleDeleteSession = async (sessionId) => {
  if (!confirm('确定要删除这条对话吗？此操作无法撤销。')) return
  try {
    await chatStore.deleteSession(sessionId)
    toastStore.showToast({ type: 'success', message: '对话已删除' })
    await reloadSessions(true)
    if (route.path === '/chat') {
      const nextSessionId = chatStore.currentSessionId
      if (route.query.session !== nextSessionId) {
        router.replace({
          path: '/chat',
          query: nextSessionId ? { session: nextSessionId } : {}
        })
      }
    }
  } catch (error) {
    console.error('Failed to delete session:', error)
    toastStore.showToast({ type: 'error', message: '删除对话失败' })
  }
}

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
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

const reloadSessions = async (silent = false) => {
  if (loadingMore.value) return
  loadingMore.value = true
  try {
    offset.value = 0
    const page = await chatStore.fetchSessionsPage({
      limit: pageSize,
      offset: 0,
      query: searchQuery.value,
      append: false
    })
    offset.value = page.length
    hasMore.value = page.length === pageSize
  } catch (error) {
    if (!silent) {
      console.error('Failed to load chat sessions:', error)
    }
  } finally {
    loadingMore.value = false
  }
}

const loadMoreSessions = async () => {
  if (!hasMore.value || loadingMore.value) return
  loadingMore.value = true
  try {
    const page = await chatStore.fetchSessionsPage({
      limit: pageSize,
      offset: offset.value,
      query: searchQuery.value,
      append: true
    })
    offset.value += page.length
    if (page.length < pageSize) {
      hasMore.value = false
    }
  } catch (error) {
    console.error('Failed to load more sessions:', error)
  } finally {
    loadingMore.value = false
  }
}

const handleSearch = () => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    reloadSessions(true)
  }, 300)
}

const clearSearch = () => {
  searchQuery.value = ''
  reloadSessions(true)
}

onMounted(async () => {
  await reloadSessions()
})
</script>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  flex: 0 0 var(--sidebar-width);
  height: 100%;
  background: var(--gpt-sidebar);
  border-right: 1px solid #2a2b2e;
  color: #cbd5e1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #2a2b2e;
  display: flex;
  align-items: center;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: #f8fafc;
  font-weight: 600;
  font-size: 14px;
}

.brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: #343541;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.sidebar-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.btn-new-chat {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 12px;
  background: transparent;
  color: #f8fafc;
  border: 1px solid #3f4047;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: none;
}

.btn-new-chat:hover {
  background: var(--gpt-sidebar-hover);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  text-decoration: none;
  color: #e2e8f0;
  font-size: 13px;
  transition: all var(--transition-base);
}

.sidebar-nav-item:hover,
.sidebar-nav-item.router-link-active {
  background: var(--gpt-sidebar-hover);
  color: #ffffff;
}

.sessions-header {
  padding: 6px 4px 0;
}

.sessions-header h3 {
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0;
}

.sessions-search {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(52, 53, 65, 0.4);
  border: 1px solid #2a2b2e;
  border-radius: 8px;
  padding: 6px 8px;
}

.search-icon {
  font-size: 12px;
  color: #9ca3af;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: #e2e8f0;
  font-size: 12px;
  outline: none;
}

.search-input::placeholder {
  color: #6b7280;
}

.search-clear {
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sessions-empty {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  color: #9ca3af;
  background: rgba(52, 53, 65, 0.4);
}

.session-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--transition-base);
  color: #e2e8f0;
  background: transparent;
  border: none;
  text-align: left;
  font: inherit;
  flex: 1;
}

.session-item:hover {
  background: var(--gpt-sidebar-hover);
}

.session-item.active {
  background: #343541;
  color: #ffffff;
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
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: inherit;
}

.session-time {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}

.session-delete {
  border: none;
  background: transparent;
  color: #9ca3af;
  padding: 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 14px;
}

.session-delete:hover {
  color: #f87171;
  background: rgba(248, 113, 113, 0.15);
}

.sessions-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
}

.btn-load-more {
  border: 1px solid #3f4047;
  background: transparent;
  color: #cbd5e1;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: all var(--transition-base);
}

.btn-load-more:hover {
  background: var(--gpt-sidebar-hover);
}

.btn-load-more:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sessions-end {
  font-size: 11px;
  color: #6b7280;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid #2a2b2e;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #343541;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13px;
}

.user-meta {
  min-width: 0;
}

.user-name {
  font-size: 13px;
  color: #f8fafc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-subtitle {
  font-size: 11px;
  color: #9ca3af;
}

.btn-logout {
  width: 100%;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #3f4047;
  background: transparent;
  color: #e2e8f0;
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-base);
}

.btn-logout:hover {
  background: var(--gpt-sidebar-hover);
}

::deep(.app-sidebar ::-webkit-scrollbar) {
  width: 6px;
}

::deep(.app-sidebar ::-webkit-scrollbar-track) {
  background: transparent;
}

::deep(.app-sidebar ::-webkit-scrollbar-thumb) {
  background: #3b3c40;
  border-radius: 999px;
}

@media (max-width: 1024px) {
  .app-sidebar {
    width: 100%;
    flex-basis: 100%;
    border-right: 1px solid #2a2b2e;
    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.25);
  }
}
</style>
