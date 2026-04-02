import api from './axios'
import { buildApiUrl } from './base'
export { agentsAPI } from './agents'
export { skillsAPI } from './skills'
export { mcpAPI } from './mcp'
export { subagentsAPI } from './subagents'

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
  logout(refreshToken = '') {
    return api.post('/api/v1/auth/logout', refreshToken ? { refresh_token: refreshToken } : {})
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

  getUsageStats(knowledgeBaseId = '') {
    const params = {}
    if (knowledgeBaseId) {
      params.knowledge_base_id = knowledgeBaseId
    }
    return api.get('/api/v1/chat/usage/stats', { params })
  },

  getLowQualitySamples({ knowledgeBaseId = '', limit = 20 } = {}) {
    const params = { limit }
    if (knowledgeBaseId) {
      params.knowledge_base_id = knowledgeBaseId
    }
    return api.get('/api/v1/chat/feedback/low-quality', { params })
  },

  saveMessageFeedback(messageId, payload) {
    return api.post(`/api/v1/chat/messages/${messageId}/feedback`, payload)
  },

  // Send message with SSE (streaming)
  async sendMessageSSE(sessionId, message, config = {}, onChunk) {
    const token = localStorage.getItem('access_token')
    const response = await fetch(buildApiUrl('/api/v1/chat/sse'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        metadata: config.metadata || {},
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
                onChunk({
                  messageId: json.message_id ?? json.MessageID ?? '',
                  type: json.type ?? json.Type,
                  content: json.content ?? json.Content ?? '',
                  metadata: json.metadata ?? json.Metadata ?? {},
                  error: json.error ?? json.Error ?? ''
                })
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

export const uploadAPI = {
  createBundle(files = [], paths = []) {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })
    paths.forEach((path) => {
      formData.append('paths', path)
    })
    return api.post('/api/v1/uploads/bundles', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 120000
    })
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
  },

  // Get indexing settings
  getIndexingSettings(id) {
    return api.get(`/api/v1/knowledge-bases/${id}/indexing-settings`)
  },

  // Update indexing settings
  updateIndexingSettings(id, data) {
    return api.put(`/api/v1/knowledge-bases/${id}/indexing-settings`, {
      indexing_method: data.indexing_method,
      chunk_size: data.chunk_size,
      chunk_overlap: data.chunk_overlap,
      embedding_model_id: data.embedding_model_id || null,
      tokenizer_mode: data.tokenizer_mode,
      custom_terms: Array.isArray(data.custom_terms) ? data.custom_terms : [],
      synonym_map: data.synonym_map && typeof data.synonym_map === 'object' ? data.synonym_map : {}
    })
  },

  // Get retrieval settings
  getRetrievalSettings(id) {
    return api.get(`/api/v1/knowledge-bases/${id}/retrieval-settings`)
  },

  // Update retrieval settings
  updateRetrievalSettings(id, data) {
    return api.put(`/api/v1/knowledge-bases/${id}/retrieval-settings`, {
      retrieval_method: data.retrieval_method,
      top_k: data.top_k,
      score_threshold: data.score_threshold,
      vector_top_k: data.vector_top_k,
      keyword_top_k: data.keyword_top_k,
      fusion_algorithm: data.fusion_algorithm,
      rrf_k: data.rrf_k,
      vector_weight: data.vector_weight,
      keyword_weight: data.keyword_weight,
      max_candidates: data.max_candidates,
      enable_rerank: data.enable_rerank,
      rerank_model_id: data.rerank_model_id || null,
      query_rewrite: data.query_rewrite
    })
  },

  getGovernanceSettings(id) {
    return api.get(`/api/v1/knowledge-bases/${id}/governance-settings`)
  },

  updateGovernanceSettings(id, data) {
    return api.put(`/api/v1/knowledge-bases/${id}/governance-settings`, data)
  },

  // Retrieval test
  testRetrieval(id, data) {
    return api.post(`/api/v1/knowledge-bases/${id}/retrieval-test`, {
      query: data.query,
      top_k: data.top_k ?? null,
      score_threshold: data.score_threshold ?? null
    })
  },

  listEvaluationDatasets(id) {
    return api.get(`/api/v1/knowledge-bases/${id}/evaluation-datasets`)
  },

  createEvaluationDataset(id, data) {
    return api.post(`/api/v1/knowledge-bases/${id}/evaluation-datasets`, data)
  },

  updateEvaluationDataset(id, datasetId, data) {
    return api.put(`/api/v1/knowledge-bases/${id}/evaluation-datasets/${datasetId}`, data)
  },

  deleteEvaluationDataset(id, datasetId) {
    return api.delete(`/api/v1/knowledge-bases/${id}/evaluation-datasets/${datasetId}`)
  },

  listEvaluationRuns(id, limit = 20) {
    return api.get(`/api/v1/knowledge-bases/${id}/evaluation-runs`, {
      params: { limit }
    })
  },

  runEvaluation(id, data) {
    return api.post(`/api/v1/knowledge-bases/${id}/evaluation-runs`, data)
  },

  getEvaluationRun(id, runId) {
    return api.get(`/api/v1/knowledge-bases/${id}/evaluation-runs/${runId}`)
  },

  updateEvaluationFeedback(id, runId, data) {
    return api.post(`/api/v1/knowledge-bases/${id}/evaluation-runs/${runId}/feedback`, data)
  },

  applyEvaluationRunConfig(id, runId) {
    return api.post(`/api/v1/knowledge-bases/${id}/evaluation-runs/${runId}/apply-config`)
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

  // Get document preview
  getDocumentPreview(id, maxChars = 4000) {
    return api.get(`/api/v1/knowledge/documents/${id}/preview`, {
      params: { max_chars: maxChars }
    })
  },

  // Get document segments
  getDocumentSegments(id, params = {}) {
    return api.get(`/api/v1/knowledge/documents/${id}/segments`, { params })
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
      auto_index: data.auto_index !== false,
      skip_duplicate_check: data.skip_duplicate_check === true
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
  uploadDocument(knowledgeBaseId, file, options = {}) {
    const accessLevel = options.accessLevel || 'tenant'
    const skipDuplicateCheck = options.skipDuplicateCheck === true
    const formData = new FormData()
    formData.append('file', file)
    formData.append('knowledge_base_id', knowledgeBaseId)
    formData.append('access_level', accessLevel)
    formData.append('auto_index', 'true')
    formData.append('skip_duplicate_check', skipDuplicateCheck ? 'true' : 'false')
    return api.post('/api/v1/knowledge/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // Create document from URL
  createFromUrl(knowledgeBaseId, url, options = {}) {
    const accessLevel = options.accessLevel || 'tenant'
    const skipDuplicateCheck = options.skipDuplicateCheck === true
    const formData = new FormData()
    formData.append('url', url)
    formData.append('knowledge_base_id', knowledgeBaseId)
    formData.append('access_level', accessLevel)
    formData.append('auto_index', 'true')
    formData.append('skip_duplicate_check', skipDuplicateCheck ? 'true' : 'false')
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
