import { defineStore } from 'pinia'
import { chatAPI } from '@/api'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: JSON.parse(localStorage.getItem('chat_sessions') || '{}'),
    currentSessionId: localStorage.getItem('current_session_id') || null,
    config: {
      useRAG: false,
      useAgent: false,
      temperature: 0.7
    }
  }),

  getters: {
    currentSession(state) {
      return state.currentSessionId ? state.sessions[state.currentSessionId] : null
    },

    sortedSessions(state) {
      return Object.values(state.sessions).sort(
        (a, b) => new Date(b.createdAt) - new Date(a.createdAt)
      )
    }
  },

  actions: {
    createSession() {
      const sessionId = this.generateUUID()
      const session = {
        id: sessionId,
        title: `Session ${Object.keys(this.sessions).length + 1}`,
        messages: [],
        createdAt: new Date().toISOString()
      }

      this.sessions[sessionId] = session
      this.currentSessionId = sessionId
      this.saveSessions()
      return session
    },

    loadSession(sessionId) {
      if (this.sessions[sessionId]) {
        this.currentSessionId = sessionId
        localStorage.setItem('current_session_id', sessionId)
      }
    },

    addMessage(message) {
      if (this.currentSession) {
        this.currentSession.messages.push({
          ...message,
          timestamp: new Date().toISOString()
        })
        this.saveSessions()
      }
    },

    updateLastMessage(content) {
      if (this.currentSession && this.currentSession.messages.length > 0) {
        const lastMessage = this.currentSession.messages[this.currentSession.messages.length - 1]
        lastMessage.content = content
        this.saveSessions()
      }
    },

    async sendMessage(message) {
      if (!this.currentSessionId) {
        this.createSession()
      }

      // Add user message
      this.addMessage({
        role: 'user',
        content: message
      })

      // Add assistant placeholder
      this.addMessage({
        role: 'assistant',
        content: '',
        streaming: true
      })

      try {
        await chatAPI.sendMessageSSE(
          this.currentSessionId,
          message,
          {
            use_rag: this.config.useRAG,
            use_agent: this.config.useAgent,
            temperature: this.config.temperature
          },
          (chunk) => {
            const lastMessage = this.currentSession.messages[this.currentSession.messages.length - 1]
            lastMessage.content += chunk
            this.saveSessions()
          }
        )

        // Mark streaming complete
        const lastMessage = this.currentSession.messages[this.currentSession.messages.length - 1]
        lastMessage.streaming = false
        this.saveSessions()
      } catch (error) {
        // Update last message with error
        const lastMessage = this.currentSession.messages[this.currentSession.messages.length - 1]
        lastMessage.content = `Error: ${error.message}`
        lastMessage.streaming = false
        lastMessage.error = true
        this.saveSessions()
        throw error
      }
    },

    saveSessions() {
      localStorage.setItem('chat_sessions', JSON.stringify(this.sessions))
    },

    generateUUID() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0
        const v = c === 'x' ? r : (r & 0x3 | 0x8)
        return v.toString(16)
      })
    }
  }
})
