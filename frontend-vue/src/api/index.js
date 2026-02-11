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

  // List chat sessions
  getSessions(limit = 50, offset = 0, query = '') {
    const params = { limit, offset }
    if (query) {
      params.q = query
    }
    return api.get('/api/v1/chat/sessions', { params })
  },

  // Create chat session
  createSession(data = {}) {
    return api.post('/api/v1/chat/sessions', {
      session_id: data.session_id,
      title: data.title
    })
  },

  // Get chat history
  getHistory(sessionId, limit = 200, offset = 0) {
    return api.get(`/api/v1/chat/history/${sessionId}`, {
      params: { limit, offset }
    })
  },

  // Delete chat session
  deleteSession(sessionId) {
    return api.delete(`/api/v1/chat/session/${sessionId}`)
  },

  // Send message with SSE (streaming)
  async sendMessageSSE(sessionId, message, config = {}, onChunk) {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/v1/chat/sse`, {
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
    let buffer = ''
    let dataLines = []

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        let newlineIndex = buffer.indexOf('\n')
        while (newlineIndex !== -1) {
          let line = buffer.slice(0, newlineIndex)
          buffer = buffer.slice(newlineIndex + 1)
          newlineIndex = buffer.indexOf('\n')

          if (line.endsWith('\r')) {
            line = line.slice(0, -1)
          }

          if (line === '') {
            if (dataLines.length > 0) {
              const data = dataLines.join('\n')
              dataLines = []
              if (data === '[DONE]') {
                return
              }
              try {
                const json = JSON.parse(data)
                const content = json.content ?? json.Content
                if (content) {
                  onChunk(content)
                }
                const errMsg = json.error ?? json.Error
                if (errMsg) {
                  console.error('SSE error payload:', errMsg)
                }
              } catch (e) {
                console.error('Parse SSE error:', e, data)
              }
            }
            continue
          }

          if (line.startsWith('data:')) {
            let dataPart = line.slice(5)
            if (dataPart.startsWith(' ')) {
              dataPart = dataPart.slice(1)
            }
            dataLines.push(dataPart)
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }
}

export const knowledgeBaseAPI = {
  // Get all knowledge bases
  getKnowledgeBases(page = 1, pageSize = 20) {
    return api.get('/api/v1/knowledge-bases', {
      params: { page, page_size: pageSize }
    })
  },

  // Get knowledge base by ID (with stats)
  getKnowledgeBase(id) {
    return api.get(`/api/v1/knowledge-bases/${id}`)
  },

  // Create knowledge base
  createKnowledgeBase(data) {
    return api.post('/api/v1/knowledge-bases', {
      name: data.name,
      description: data.description || '',
      access_level: data.access_level || 'tenant',
      metadata: data.metadata || {}
    })
  },

  // Update knowledge base
  updateKnowledgeBase(id, data) {
    return api.put(`/api/v1/knowledge-bases/${id}`, {
      name: data.name,
      description: data.description,
      metadata: data.metadata
    })
  },

  // Delete knowledge base
  deleteKnowledgeBase(id) {
    return api.delete(`/api/v1/knowledge-bases/${id}`)
  },

  // Get documents in knowledge base
  getKnowledgeBaseDocuments(id, page = 1, pageSize = 20) {
    return api.get(`/api/v1/knowledge-bases/${id}/documents`, {
      params: { page, page_size: pageSize }
    })
  },

  // Get knowledge base stats
  getKnowledgeBaseStats(id) {
    return api.get(`/api/v1/knowledge-bases/${id}/stats`)
  }
}

export const documentAPI = {
  // Get all documents
  getDocuments(params = {}) {
    return api.get('/api/v1/knowledge/documents', { params })
  },

  // Get document by ID
  getDocument(id) {
    return api.get(`/api/v1/knowledge/documents/${id}`)
  },

  // Create document
  createDocument(data) {
    return api.post('/api/v1/knowledge/documents', {
      knowledge_base_id: data.knowledge_base_id,
      title: data.title,
      content: data.content,
      source: data.source || 'manual',
      source_type: data.source_type || 'manual',
      access_level: data.access_level || 'tenant',
      metadata: data.metadata || {},
      auto_index: data.auto_index !== false
    })
  },

  // Update document
  updateDocument(id, data) {
    return api.put(`/api/v1/knowledge/documents/${id}`, {
      title: data.title,
      content: data.content,
      source: data.source,
      metadata: data.metadata,
      re_index: data.re_index || false
    })
  },

  // Delete document
  deleteDocument(id) {
    return api.delete(`/api/v1/knowledge/documents/${id}`)
  },

  // Upload file as document
  uploadDocument(knowledgeBaseId, file, accessLevel = 'tenant') {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('knowledge_base_id', knowledgeBaseId)
    formData.append('access_level', accessLevel)
    formData.append('auto_index', 'true')
    return api.post('/api/v1/knowledge/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // Create document from URL
  createFromUrl(knowledgeBaseId, url, accessLevel = 'tenant') {
    const formData = new FormData()
    formData.append('url', url)
    formData.append('knowledge_base_id', knowledgeBaseId)
    formData.append('access_level', accessLevel)
    formData.append('auto_index', 'true')
    return api.post('/api/v1/knowledge/documents/from-url', formData)
  },

  // Search documents
  searchDocuments(query, topK = 10) {
    return api.post('/api/v1/knowledge/documents/search', {
      query,
      top_k: topK
    })
  },

  // Batch create documents
  batchCreateDocuments(documents) {
    return api.post('/api/v1/knowledge/documents/batch', {
      documents
    })
  }
}

// Legacy API for backward compatibility
export const knowledgeAPI = {
  // Map to knowledge bases
  getKnowledgeBases(page = 1, pageSize = 100) {
    return knowledgeBaseAPI.getKnowledgeBases(page, pageSize)
  },

  getKnowledgeBase(id) {
    return knowledgeBaseAPI.getKnowledgeBase(id)
  },

  createKnowledgeBase(data) {
    return knowledgeBaseAPI.createKnowledgeBase(data)
  },

  updateKnowledgeBase(id, data) {
    return knowledgeBaseAPI.updateKnowledgeBase(id, data)
  },

  deleteKnowledgeBase(id) {
    return knowledgeBaseAPI.deleteKnowledgeBase(id)
  },

  // Map to documents
  getDocuments(knowledgeBaseId) {
    if (knowledgeBaseId) {
      return knowledgeBaseAPI.getKnowledgeBaseDocuments(knowledgeBaseId)
    }
    return documentAPI.getDocuments()
  },

  deleteDocument(knowledgeBaseId, documentId) {
    return documentAPI.deleteDocument(documentId)
  },

  uploadDocument(knowledgeBaseId, file) {
    return documentAPI.uploadDocument(knowledgeBaseId, file)
  },

  searchDocuments(query, topK = 10) {
    return documentAPI.searchDocuments(query, topK)
  },

  getStats() {
    return api.get('/api/v1/knowledge/stats')
  }
}
