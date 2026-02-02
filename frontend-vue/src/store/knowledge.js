import { defineStore } from 'pinia'
import { knowledgeAPI } from '@/api'

export const useKnowledgeStore = defineStore('knowledge', {
  state: () => ({
    knowledgeBases: [],
    currentKnowledgeBase: null,
    documents: [],
    loading: false,
    error: null
  }),

  actions: {
    async fetchKnowledgeBases() {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.getKnowledgeBases()
        // Handle paginated response from documents API
        this.knowledgeBases = data.documents || []
        return this.knowledgeBases
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to fetch knowledge bases'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchKnowledgeBase(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.getKnowledgeBase(id)
        this.currentKnowledgeBase = data
        return data
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to fetch knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async createKnowledgeBase(knowledgeBaseData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.createKnowledgeBase(knowledgeBaseData)
        this.knowledgeBases.push(data)
        return data
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to create knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateKnowledgeBase(id, knowledgeBaseData) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.updateKnowledgeBase(id, knowledgeBaseData)
        const index = this.knowledgeBases.findIndex(kb => kb.id === id)
        if (index !== -1) {
          this.knowledgeBases[index] = data
        }
        if (this.currentKnowledgeBase?.id === id) {
          this.currentKnowledgeBase = data
        }
        return data
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to update knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteKnowledgeBase(id) {
      this.loading = true
      this.error = null
      try {
        await knowledgeAPI.deleteKnowledgeBase(id)
        this.knowledgeBases = this.knowledgeBases.filter(kb => kb.id !== id)
        if (this.currentKnowledgeBase?.id === id) {
          this.currentKnowledgeBase = null
        }
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to delete knowledge base'
        throw error
      } finally {
        this.loading = false
      }
    },

    async fetchDocuments(knowledgeBaseId) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.getDocuments(knowledgeBaseId)
        // Handle paginated response
        this.documents = data.documents || []
        return this.documents
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to fetch documents'
        throw error
      } finally {
        this.loading = false
      }
    },

    async uploadDocument(knowledgeBaseId, file) {
      this.loading = true
      this.error = null
      try {
        const { data } = await knowledgeAPI.uploadDocument(knowledgeBaseId, file)
        this.documents.push(data)
        return data
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to upload document'
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteDocument(knowledgeBaseId, documentId) {
      this.loading = true
      this.error = null
      try {
        await knowledgeAPI.deleteDocument(knowledgeBaseId, documentId)
        this.documents = this.documents.filter(doc => doc.id !== documentId)
      } catch (error) {
        this.error = error.response?.data?.error || 'Failed to delete document'
        throw error
      } finally {
        this.loading = false
      }
    },

    clearError() {
      this.error = null
    }
  }
})
