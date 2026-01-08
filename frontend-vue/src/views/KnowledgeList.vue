<template>
  <div class="knowledge-list-container">
    <div class="header">
      <h1>Knowledge Bases</h1>
      <button @click="goToCreate" class="btn-primary">
        + Create New
      </button>
    </div>

    <div v-if="loading" class="loading">Loading...</div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="!loading && knowledgeBases.length === 0" class="empty-state">
      <p>No knowledge bases yet</p>
      <button @click="goToCreate" class="btn-secondary">Create your first knowledge base</button>
    </div>

    <div v-if="!loading && knowledgeBases.length > 0" class="knowledge-grid">
      <div
        v-for="kb in knowledgeBases"
        :key="kb.id"
        class="knowledge-card"
        @click="goToDetail(kb.id)"
      >
        <div class="card-header">
          <h3>{{ kb.name }}</h3>
          <div class="card-actions" @click.stop>
            <button @click="goToEdit(kb.id)" class="btn-icon" title="Edit">
              ✏️
            </button>
            <button @click="handleDelete(kb.id)" class="btn-icon" title="Delete">
              🗑️
            </button>
          </div>
        </div>
        <p class="description">{{ kb.description || 'No description' }}</p>
        <div class="card-footer">
          <span class="meta">{{ kb.document_count || 0 }} documents</span>
          <span class="meta">{{ formatDate(kb.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const knowledgeBases = ref([])
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  await loadKnowledgeBases()
})

const loadKnowledgeBases = async () => {
  loading.value = true
  error.value = ''
  try {
    knowledgeBases.value = await knowledgeStore.fetchKnowledgeBases()
  } catch (err) {
    error.value = err.response?.data?.error || 'Failed to load knowledge bases'
  } finally {
    loading.value = false
  }
}

const goToCreate = () => {
  router.push('/knowledge/create')
}

const goToDetail = (id) => {
  router.push(`/knowledge/${id}`)
}

const goToEdit = (id) => {
  router.push(`/knowledge/${id}/edit`)
}

const handleDelete = async (id) => {
  if (!confirm('Are you sure you want to delete this knowledge base?')) {
    return
  }

  try {
    await knowledgeStore.deleteKnowledgeBase(id)
    await loadKnowledgeBases()
  } catch (err) {
    error.value = err.response?.data?.error || 'Failed to delete knowledge base'
  }
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  return date.toLocaleDateString()
}
</script>

<style scoped>
.knowledge-list-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 32px;
  color: #111827;
  margin: 0;
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

.btn-icon {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s;
}

.btn-icon:hover {
  background: #F3F4F6;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #6B7280;
}

.error {
  padding: 12px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 8px;
  margin-bottom: 20px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #6B7280;
}

.empty-state p {
  font-size: 18px;
  margin-bottom: 20px;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
}

.knowledge-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 24px;
  cursor: pointer;
  transition: all 0.2s;
}

.knowledge-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.card-header h3 {
  font-size: 18px;
  color: #111827;
  margin: 0;
  flex: 1;
}

.card-actions {
  display: flex;
  gap: 4px;
}

.description {
  color: #6B7280;
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid #E5E7EB;
}

.meta {
  font-size: 12px;
  color: #9CA3AF;
}
</style>
