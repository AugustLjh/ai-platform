import api from './axios'

export const authAPI = {
  // Register
  register(email, password) {
    return api.post('/api/v1/auth/register', { email, password })
  },

  // Login
  login(email, password) {
    return api.post('/api/v1/auth/login', { email, password })
  },

  // Logout
  logout() {
    return api.post('/api/v1/auth/logout')
  },

  // Get current user
  getCurrentUser() {
    return api.get('/api/v1/auth/me')
  },

  // Refresh token
  refreshToken(refreshToken) {
    return api.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
  }
}

export const chatAPI = {
  // Send message (sync)
  sendMessage(sessionId, message, config = {}) {
    return api.post('/api/v1/chat', {
      session_id: sessionId,
      message,
      config
    })
  },

  // Send message with SSE (streaming)
  async sendMessageSSE(sessionId, message, config = {}, onChunk) {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`${api.defaults.baseURL}/api/v1/chat/sse`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        config
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.substring(6)
            if (data === '[DONE]') {
              return
            }
            try {
              const json = JSON.parse(data)
              if (json.content) {
                onChunk(json.content)
              }
            } catch (e) {
              console.error('Parse SSE error:', e)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }
}

export const knowledgeAPI = {
  // Get all knowledge bases
  getKnowledgeBases() {
    return api.get('/api/v1/knowledge')
  },

  // Get knowledge base by ID
  getKnowledgeBase(id) {
    return api.get(`/api/v1/knowledge/${id}`)
  },

  // Create knowledge base
  createKnowledgeBase(data) {
    return api.post('/api/v1/knowledge', data)
  },

  // Update knowledge base
  updateKnowledgeBase(id, data) {
    return api.put(`/api/v1/knowledge/${id}`, data)
  },

  // Delete knowledge base
  deleteKnowledgeBase(id) {
    return api.delete(`/api/v1/knowledge/${id}`)
  },

  // Upload document to knowledge base
  uploadDocument(knowledgeBaseId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/api/v1/knowledge/${knowledgeBaseId}/documents`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // Get documents in knowledge base
  getDocuments(knowledgeBaseId) {
    return api.get(`/api/v1/knowledge/${knowledgeBaseId}/documents`)
  },

  // Delete document
  deleteDocument(knowledgeBaseId, documentId) {
    return api.delete(`/api/v1/knowledge/${knowledgeBaseId}/documents/${documentId}`)
  }
}
