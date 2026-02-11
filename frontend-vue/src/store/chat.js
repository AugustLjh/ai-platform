import { defineStore } from 'pinia'
import { chatAPI } from '@/api'
import { isPlainMarkdownRequest } from '@/utils/markdown'

try {
  localStorage.removeItem('chat_sessions')
  localStorage.removeItem('current_session_id')
} catch (error) {
  // Ignore storage cleanup errors
}

const normalizeSession = (raw) => ({
  id: raw.id,
  title: raw.title || '',
  createdAt: raw.created_at || raw.createdAt || raw.created_at,
  updatedAt: raw.updated_at || raw.updatedAt || raw.updated_at,
  lastMessageAt: raw.last_message_at || raw.lastMessageAt || null
})

const normalizeMessage = (raw) => ({
  id: raw.id,
  role: raw.role,
  content: raw.content,
  timestamp: raw.created_at || raw.createdAt || raw.timestamp || new Date().toISOString()
})

const buildTitle = (message) => {
  const text = (message || '').trim()
  if (!text) return ''
  const chars = Array.from(text)
  if (chars.length > 30) {
    return chars.slice(0, 30).join('') + '...'
  }
  return text
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [],
    currentSessionId: null,
    messagesBySession: {},
    loading: false,
    error: null,
    config: {
      useRAG: localStorage.getItem('chat_use_rag') === 'true',
      useAgent: localStorage.getItem('chat_use_agent') === 'true',
      temperature: Number(localStorage.getItem('chat_temperature') || 0.7),
      maxTokens: Number(localStorage.getItem('chat_max_tokens') || 2000),
      knowledgeBaseId: localStorage.getItem('chat_knowledge_base_id') || ''
    }
  }),

  getters: {
    currentSession(state) {
      if (!state.currentSessionId) return null
      const session = state.sessions.find((item) => item.id === state.currentSessionId)
      if (!session) return null
      return {
        ...session,
        messages: state.messagesBySession[state.currentSessionId] || []
      }
    },

    sortedSessions(state) {
      return [...state.sessions].sort((a, b) => {
        const aTime = new Date(a.lastMessageAt || a.updatedAt || a.createdAt).getTime()
        const bTime = new Date(b.lastMessageAt || b.updatedAt || b.createdAt).getTime()
        return bTime - aTime
      })
    }
  },

  actions: {
    async fetchSessionsPage({ limit = 50, offset = 0, query = '', append = false } = {}) {
      this.loading = true
      this.error = null
      try {
        const { data } = await chatAPI.getSessions(limit, offset, query)
        const pageSessions = (data.sessions || []).map(normalizeSession)
        if (append) {
          const merged = [...this.sessions]
          const indexById = new Map(merged.map((session, index) => [session.id, index]))
          for (const session of pageSessions) {
            if (indexById.has(session.id)) {
              merged[indexById.get(session.id)] = session
            } else {
              merged.push(session)
            }
          }
          this.sessions = merged
        } else {
          this.sessions = pageSessions
        }
        return pageSessions
      } catch (error) {
        this.error = error.response?.data?.detail || error.response?.data?.error || 'Failed to fetch sessions'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchSessions(limit = 50, offset = 0) {
      return this.fetchSessionsPage({ limit, offset })
    },

    async createSession() {
      this.loading = true
      this.error = null
      try {
        const { data } = await chatAPI.createSession()
        const session = normalizeSession(data)
        this.sessions = [session, ...this.sessions.filter((item) => item.id !== session.id)]
        this.currentSessionId = session.id
        this.messagesBySession[session.id] = []
        return session
      } catch (error) {
        this.error = error.response?.data?.detail || error.response?.data?.error || 'Failed to create session'
        throw error
      } finally {
        this.loading = false
      }
    },

    async loadSession(sessionId, options = {}) {
      if (!sessionId) return
      this.currentSessionId = sessionId
      const shouldRefresh = options.refresh || !this.messagesBySession[sessionId]
      if (shouldRefresh) {
        await this.fetchHistory(sessionId)
      }
    },

    async fetchHistory(sessionId, limit = 200, offset = 0) {
      this.loading = true
      this.error = null
      try {
        const { data } = await chatAPI.getHistory(sessionId, limit, offset)
        const messages = (data.messages || []).map(normalizeMessage)
        this.messagesBySession[sessionId] = messages
        return messages
      } catch (error) {
        this.error = error.response?.data?.detail || error.response?.data?.error || 'Failed to fetch history'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteSession(sessionId) {
      this.loading = true
      this.error = null
      try {
        await chatAPI.deleteSession(sessionId)
        this.sessions = this.sessions.filter((item) => item.id !== sessionId)
        delete this.messagesBySession[sessionId]
        if (this.currentSessionId === sessionId) {
          this.currentSessionId = this.sessions[0]?.id || null
          if (this.currentSessionId) {
            await this.loadSession(this.currentSessionId, { refresh: true })
          }
        }
      } catch (error) {
        this.error = error.response?.data?.detail || error.response?.data?.error || 'Failed to delete session'
        throw error
      } finally {
        this.loading = false
      }
    },

    addMessage(message) {
      if (!this.currentSessionId) return
      const list = this.messagesBySession[this.currentSessionId] || []
      list.push({
        ...message,
        timestamp: message.timestamp || new Date().toISOString()
      })
      this.messagesBySession[this.currentSessionId] = list
    },

    updateLastMessage(content) {
      if (!this.currentSessionId) return
      const list = this.messagesBySession[this.currentSessionId] || []
      if (list.length === 0) return
      list[list.length - 1].content = content
      this.messagesBySession[this.currentSessionId] = list
    },

    touchSession(sessionId, userMessage) {
      const session = this.sessions.find((item) => item.id === sessionId)
      if (!session) return
      const now = new Date().toISOString()
      session.updatedAt = now
      session.lastMessageAt = now
      if (!session.title || session.title === '新对话') {
        const title = buildTitle(userMessage)
        if (title) {
          session.title = title
        }
      }
    },

    async sendMessage(message, configOverride = {}) {
      if (!this.currentSessionId) {
        await this.createSession()
      }

      const sessionId = this.currentSessionId
      const renderMarkdown = !isPlainMarkdownRequest(message)

      // Add user message
      this.addMessage({
        role: 'user',
        content: message
      })

      // Add assistant placeholder
      this.addMessage({
        role: 'assistant',
        content: '',
        streaming: true,
        renderMarkdown
      })

      this.touchSession(sessionId, message)

      try {
        const effectiveKnowledgeBaseId = configOverride.knowledge_base_id ?? this.config.knowledgeBaseId
        await chatAPI.sendMessageSSE(
          sessionId,
          message,
          {
            model: configOverride.model,
            use_rag: configOverride.use_rag ?? (effectiveKnowledgeBaseId ? true : this.config.useRAG),
            use_agent: configOverride.use_agent ?? this.config.useAgent,
            temperature: configOverride.temperature ?? this.config.temperature,
            max_tokens: configOverride.max_tokens ?? this.config.maxTokens,
            knowledge_base_id: effectiveKnowledgeBaseId || undefined
          },
          (chunk) => {
            const list = this.messagesBySession[sessionId] || []
            if (list.length === 0) return
            const lastMessage = list[list.length - 1]
            lastMessage.content += chunk
            this.messagesBySession[sessionId] = list
          }
        )

        const list = this.messagesBySession[sessionId] || []
        if (list.length > 0) {
          list[list.length - 1].streaming = false
          this.messagesBySession[sessionId] = list
        }

        await this.fetchSessions()
      } catch (error) {
        const list = this.messagesBySession[sessionId] || []
        if (list.length > 0) {
          list[list.length - 1].content = 'Error: ' + error.message
          list[list.length - 1].streaming = false
          list[list.length - 1].error = true
          this.messagesBySession[sessionId] = list
        }
        throw error
      }
    },

    updateConfig(partial) {
      this.config = {
        ...this.config,
        ...partial
      }
      localStorage.setItem('chat_use_rag', String(this.config.useRAG))
      localStorage.setItem('chat_use_agent', String(this.config.useAgent))
      localStorage.setItem('chat_temperature', String(this.config.temperature))
      localStorage.setItem('chat_max_tokens', String(this.config.maxTokens))
      localStorage.setItem('chat_knowledge_base_id', String(this.config.knowledgeBaseId || ''))
    }
  }
})
