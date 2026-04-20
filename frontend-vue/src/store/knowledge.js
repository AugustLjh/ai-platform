import { defineStore } from 'pinia'
import { knowledgeBaseAPI, documentAPI } from '@/api'

export const useKnowledgeStore = defineStore('knowledge', {
  state: () => ({
    knowledgeBases: [],
    currentKnowledgeBase: null,
    knowledgeBaseStats: null,
    indexingSettings: null,
    retrievalSettings: null,
    governanceSettings: null,
    evaluationDatasets: [],
    evaluationRuns: [],
    currentEvaluationRun: null,
    documents: [],
    currentDocument: null,
    loading: false,
    error: null,
    pagination: {
      page: 1,
      pageSize: 20,
      total: 0
    }
  }),

  actions: {
    // Knowledge Base Actions
    async fetchKnowledgeBases(page = 1, pageSize = 20) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getKnowledgeBases(page, pageSize)
        this.knowledgeBases = data.knowledge_bases || []
        this.pagination = {
          page: data.page,
          pageSize: data.page_size,
          total: data.total
        }
        return this.knowledgeBases
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch knowledge bases'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchKnowledgeBase(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getKnowledgeBase(id)
        this.currentKnowledgeBase = data
        this.knowledgeBaseStats = {
          document_count: data.document_count || 0
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async createKnowledgeBase(knowledgeBaseData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.createKnowledgeBase(knowledgeBaseData)
        this.knowledgeBases.push(data)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to create knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateKnowledgeBase(id, knowledgeBaseData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateKnowledgeBase(id, knowledgeBaseData)
        const index = this.knowledgeBases.findIndex(kb => kb.id === id)
        if (index !== -1) {
          this.knowledgeBases[index] = data
        }
        if (this.currentKnowledgeBase?.id === id) {
          this.currentKnowledgeBase = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteKnowledgeBase(id) {
      this.loading = true
      this.error = null
      try {
        await knowledgeBaseAPI.deleteKnowledgeBase(id)
        this.knowledgeBases = this.knowledgeBases.filter(kb => kb.id !== id)
        if (this.currentKnowledgeBase?.id === id) {
          this.currentKnowledgeBase = null
          this.knowledgeBaseStats = null
        }
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to delete knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchKnowledgeBaseStats(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getKnowledgeBaseStats(id)
        this.knowledgeBaseStats = {
          document_count: data.document_count || 0
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch stats'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchIndexingSettings(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getIndexingSettings(id)
        this.indexingSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch indexing settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateIndexingSettings(id, settings) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateIndexingSettings(id, settings)
        this.indexingSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update indexing settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchRetrievalSettings(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getRetrievalSettings(id)
        this.retrievalSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch retrieval settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateRetrievalSettings(id, settings) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateRetrievalSettings(id, settings)
        this.retrievalSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update retrieval settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchGovernanceSettings(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getGovernanceSettings(id)
        this.governanceSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch governance settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateGovernanceSettings(id, settings) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateGovernanceSettings(id, settings)
        this.governanceSettings = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update governance settings'
        throw error
      } finally {
        this.loading = false
      }
    },

    // Document Actions
    async fetchDocuments(knowledgeBaseId, page = 1, pageSize = 20) {
      this.loading = true
      this.error = null
      try {
        let response
        if (knowledgeBaseId) {
          response = await knowledgeBaseAPI.getKnowledgeBaseDocuments(knowledgeBaseId, page, pageSize)
        } else {
          response = await documentAPI.getDocuments({ page, page_size: pageSize })
        }
        const { data } = response
        this.documents = data.documents || []
        this.pagination = {
          page: data.page,
          pageSize: data.page_size,
          total: data.total
        }
        return this.documents
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch documents'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchDocument(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.getDocument(id)
        this.currentDocument = data
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchDocumentPreview(id, maxChars = 4000) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.getDocumentPreview(id, maxChars)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch document preview'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchDocumentSegments(id, params = {}) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.getDocumentSegments(id, params)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch document segments'
        throw error
      } finally {
        this.loading = false
      }
    },

    async createDocument(documentData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.createDocument(documentData)
        this.documents.push(data)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to create document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateDocument(id, documentData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.updateDocument(id, documentData)
        const index = this.documents.findIndex(doc => doc.id === id)
        if (index !== -1) {
          this.documents[index] = data
        }
        if (this.currentDocument?.id === id) {
          this.currentDocument = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async uploadDocument(knowledgeBaseId, file, options = {}) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.uploadDocument(knowledgeBaseId, file, options)
        this.documents.push(data)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to upload document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteDocument(documentId) {
      this.loading = true
      this.error = null
      try {
        await documentAPI.deleteDocument(documentId)
        this.documents = this.documents.filter(doc => doc.id !== documentId)
        if (this.currentDocument?.id === documentId) {
          this.currentDocument = null
        }
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to delete document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async searchDocuments(query, topK = 10) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.searchDocuments(query, topK)
        return data.results || []
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to search documents'
        throw error
      } finally {
        this.loading = false
      }
    },

    async testKnowledgeRetrieval(id, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.testRetrieval(id, payload)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to test retrieval'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchEvaluationDatasets(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.listEvaluationDatasets(id)
        this.evaluationDatasets = data || []
        return this.evaluationDatasets
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch evaluation datasets'
        throw error
      } finally {
        this.loading = false
      }
    },

    async createEvaluationDataset(id, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.createEvaluationDataset(id, payload)
        const index = this.evaluationDatasets.findIndex(item => item.id === data.id)
        if (index === -1) {
          this.evaluationDatasets.unshift(data)
        } else {
          this.evaluationDatasets[index] = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to create evaluation dataset'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateEvaluationDataset(id, datasetId, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateEvaluationDataset(id, datasetId, payload)
        const index = this.evaluationDatasets.findIndex(item => item.id === data.id)
        if (index === -1) {
          this.evaluationDatasets.unshift(data)
        } else {
          this.evaluationDatasets[index] = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update evaluation dataset'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteEvaluationDataset(id, datasetId) {
      this.loading = true
      this.error = null
      try {
        await knowledgeBaseAPI.deleteEvaluationDataset(id, datasetId)
        this.evaluationDatasets = this.evaluationDatasets.filter(item => item.id !== datasetId)
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to delete evaluation dataset'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchEvaluationRuns(id, limit = 20) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.listEvaluationRuns(id, limit)
        this.evaluationRuns = data || []
        return this.evaluationRuns
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch evaluation runs'
        throw error
      } finally {
        this.loading = false
      }
    },

    async runEvaluation(id, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.runEvaluation(id, payload)
        this.currentEvaluationRun = data
        this.evaluationRuns.unshift(data)
        this.evaluationRuns = this.evaluationRuns.slice(0, 20)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to run evaluation'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchEvaluationRun(id, runId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.getEvaluationRun(id, runId)
        this.currentEvaluationRun = data
        const index = this.evaluationRuns.findIndex(item => item.id === data.id)
        if (index !== -1) {
          this.evaluationRuns[index] = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to fetch evaluation run'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateEvaluationFeedback(id, runId, payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.updateEvaluationFeedback(id, runId, payload)
        this.currentEvaluationRun = data
        const index = this.evaluationRuns.findIndex(item => item.id === data.id)
        if (index !== -1) {
          this.evaluationRuns[index] = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to update evaluation feedback'
        throw error
      } finally {
        this.loading = false
      }
    },

    async applyEvaluationRunConfig(id, runId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeBaseAPI.applyEvaluationRunConfig(id, runId)
        return data
      } catch (error) {
        this.error = error.response?.data?.detail || 'Failed to apply evaluation config'
        throw error
      } finally {
        this.loading = false
      }
    },

    clearError() {
      this.error = null
    },

    clearCurrentKnowledgeBase() {
      this.currentKnowledgeBase = null
      this.knowledgeBaseStats = null
    },

    clearCurrentDocument() {
      this.currentDocument = null
    },

    clearDocuments() {
      this.documents = []
    },

    clearEvaluationState() {
      this.evaluationDatasets = []
      this.evaluationRuns = []
      this.currentEvaluationRun = null
    }
  }
})
