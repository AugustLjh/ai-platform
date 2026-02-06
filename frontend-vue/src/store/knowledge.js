import { defineStore } from 'pinia'
import { knowledgeBaseAPI, documentAPI } from '@/api'

export const useKnowledgeStore = defineStore('knowledge', {
  state: () => ({
    knowledgeBases: [],
    currentKnowledgeBase: null,
    knowledgeBaseStats: null,
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

    async uploadDocument(knowledgeBaseId, file) {
      this.loading = true
      this.error = null
      try {
        const { data } = await documentAPI.uploadDocument(knowledgeBaseId, file)
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
    }
  }
})
