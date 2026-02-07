import { defineStore } from 'pinia'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'

export const useModelsStore = defineStore('models', {
  state: () => ({
    models: [],
    selectedModelId: localStorage.getItem('selected_model_id') || null,
    loading: false,
    error: null
  }),

  getters: {
    enabledModels(state) {
      return state.models.filter(m => m.enabled)
    },

    selectedModel(state) {
      return state.models.find(m => m.id === state.selectedModelId) || null
    },

    defaultModel(state) {
      return state.models.find(m => m.is_default) || state.enabledModels[0] || null
    }
  },

  actions: {
    async fetchModels() {
      this.loading = true
      this.error = null

      try {
        const response = await axios.get(`${API_BASE_URL}/api/v1/models`, {
          params: { enabled_only: false }
        })

        this.models = response.data.models || []

        // Set default model if none selected
        if (!this.selectedModelId && this.defaultModel) {
          this.selectedModelId = this.defaultModel.id
          localStorage.setItem('selected_model_id', this.selectedModelId)
        }

        return this.models
      } catch (error) {
        this.error = error.response?.data?.error || error.message
        console.error('Failed to fetch models:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    selectModel(modelId) {
      const model = this.models.find(m => m.id === modelId)
      if (model && model.enabled) {
        this.selectedModelId = modelId
        localStorage.setItem('selected_model_id', modelId)
      }
    },

    async createModel(modelData) {
      this.loading = true
      this.error = null

      try {
        const response = await axios.post(`${API_BASE_URL}/api/v1/models`, modelData)
        this.models.push(response.data)
        return response.data
      } catch (error) {
        this.error = error.response?.data?.error || error.message
        console.error('Failed to create model:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateModel(modelId, modelData) {
      this.loading = true
      this.error = null

      try {
        const response = await axios.put(`${API_BASE_URL}/api/v1/models/${modelId}`, modelData)
        const index = this.models.findIndex(m => m.id === modelId)
        if (index !== -1) {
          this.models[index] = response.data
        }
        return response.data
      } catch (error) {
        this.error = error.response?.data?.error || error.message
        console.error('Failed to update model:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async deleteModel(modelId) {
      this.loading = true
      this.error = null

      try {
        await axios.delete(`${API_BASE_URL}/api/v1/models/${modelId}`)
        this.models = this.models.filter(m => m.id !== modelId)

        // If deleted model was selected, select default
        if (this.selectedModelId === modelId) {
          this.selectedModelId = this.defaultModel?.id || null
          if (this.selectedModelId) {
            localStorage.setItem('selected_model_id', this.selectedModelId)
          } else {
            localStorage.removeItem('selected_model_id')
          }
        }
      } catch (error) {
        this.error = error.response?.data?.error || error.message
        console.error('Failed to delete model:', error)
        throw error
      } finally {
        this.loading = false
      }
    }
  }
})
