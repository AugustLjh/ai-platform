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
  // Get all documents (knowledge base items)
  getKnowledgeBases(page = 1, pageSize = 100) {
    return api.get('/api/v1/knowledge/documents', {
      params: { page, page_size: pageSize }
    })
  },

  // Get document by ID
  getKnowledgeBase(id) {
    return api.get(`/api/v1/knowledge/documents/${id}`)
  },

  // Create document
  createKnowledgeBase(data) {
    return api.post('/api/v1/knowledge/documents', {
      title: data.name || data.title,
      content: data.description || data.content || '',
      source: data.source || 'manual',
      source_type: 'manual',
      access_level: 'tenant',
      auto_index: true
    })
  },

  // Update document
  updateKnowledgeBase(id, data) {
    return api.put(`/api/v1/knowledge/documents/${id}`, {
      title: data.name || data.title,
      content: data.description || data.content,
      re_index: true
    })
  },

  // Delete document
  deleteKnowledgeBase(id) {
    return api.delete(`/api/v1/knowledge/documents/${id}`)
  },

  // Upload file as document
  uploadDocument(knowledgeBaseId, file) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('access_level', 'tenant')
    formData.append('auto_index', 'true')
    return api.post('/api/v1/knowledge/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // Get documents (same as getKnowledgeBases for compatibility)
  getDocuments(knowledgeBaseId) {
    return api.get('/api/v1/knowledge/documents')
  },

  // Delete document (same as deleteKnowledgeBase)
  deleteDocument(knowledgeBaseId, documentId) {
    return api.delete(`/api/v1/knowledge/documents/${documentId}`)
  },

  // Search documents
  searchDocuments(query, topK = 10) {
    return api.post('/api/v1/knowledge/documents/search', {
      query,
      top_k: topK
    })
  },

  // Get knowledge base stats
  getStats() {
    return api.get('/api/v1/knowledge/stats')
  }
}
