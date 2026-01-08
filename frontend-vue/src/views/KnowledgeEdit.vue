<template>
  <div class="knowledge-edit-container">
    <div class="header">
      <button @click="goBack" class="btn-back">← Back</button>
      <h1>Edit Knowledge Base</h1>
    </div>

    <div v-if="loading" class="loading">Loading...</div>

    <div v-if="!loading && knowledgeBase" class="form-card">
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label>Name *</label>
          <input
            v-model="form.name"
            type="text"
            required
            placeholder="Enter knowledge base name"
          />
        </div>

        <div class="form-group">
          <label>Description</label>
          <textarea
            v-model="form.description"
            rows="4"
            placeholder="Enter description (optional)"
          ></textarea>
        </div>

        <div class="form-group">
          <label>Type</label>
          <select v-model="form.type">
            <option value="general">General</option>
            <option value="technical">Technical</option>
            <option value="business">Business</option>
            <option value="personal">Personal</option>
          </select>
        </div>

        <div class="form-group">
          <label>
            <input type="checkbox" v-model="form.is_public" />
            Make this knowledge base public
          </label>
        </div>

        <div v-if="error" class="error">{{ error }}</div>

        <div class="form-actions">
          <button type="button" @click="goBack" class="btn-secondary">
            Cancel
          </button>
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? 'Saving...' : 'Save Changes' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'

const router = useRouter()
const route = useRoute()
const knowledgeStore = useKnowledgeStore()

const knowledgeBase = ref(null)
const form = ref({
  name: '',
  description: '',
  type: 'general',
  is_public: false
})

const loading = ref(false)
const saving = ref(false)
const error = ref('')

const knowledgeBaseId = route.params.id

onMounted(async () => {
  await loadKnowledgeBase()
})

const loadKnowledgeBase = async () => {
  loading.value = true
  error.value = ''
  try {
    knowledgeBase.value = await knowledgeStore.fetchKnowledgeBase(knowledgeBaseId)
    form.value = {
      name: knowledgeBase.value.name,
      description: knowledgeBase.value.description || '',
      type: knowledgeBase.value.type || 'general',
      is_public: knowledgeBase.value.is_public || false
    }
  } catch (err) {
    error.value = err.response?.data?.error || 'Failed to load knowledge base'
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  saving.value = true
  error.value = ''

  try {
    await knowledgeStore.updateKnowledgeBase(knowledgeBaseId, form.value)
    router.push(`/knowledge/${knowledgeBaseId}`)
  } catch (err) {
    error.value = err.response?.data?.error || 'Failed to update knowledge base'
  } finally {
    saving.value = false
  }
}

const goBack = () => {
  router.push(`/knowledge/${knowledgeBaseId}`)
}
</script>

<style scoped>
.knowledge-edit-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 32px;
  color: #111827;
  margin: 0;
}

.btn-back {
  padding: 8px 16px;
  background: #F3F4F6;
  color: #374151;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-back:hover {
  background: #E5E7EB;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #6B7280;
}

.form-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 32px;
}

.form-group {
  margin-bottom: 24px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #374151;
}

.form-group input[type="text"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
}

.form-group input[type="text"]:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.form-group input[type="checkbox"] {
  margin-right: 8px;
}

.form-group label:has(input[type="checkbox"]) {
  display: flex;
  align-items: center;
  font-weight: normal;
  cursor: pointer;
}

.error {
  padding: 12px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 8px;
  margin-bottom: 20px;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 32px;
}

.btn-primary {
  padding: 12px 24px;
  background: #4F46E5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #4338CA;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 12px 24px;
  background: #E5E7EB;
  color: #374151;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-secondary:hover {
  background: #D1D5DB;
}
</style>
