<template>
  <div class="knowledge-list-container">
    <Navbar />

    <div class="content-wrapper">
      <div class="header">
        <div class="header-left">
          <h1>📚 知识库</h1>
          <p class="subtitle">管理您的知识文档和资料</p>
        </div>
        <button @click="goToCreate" class="btn-create">
          <span class="icon">✨</span>
          <span>创建知识库</span>
        </button>
      </div>

      <div class="search-bar">
        <div class="search-input-wrapper">
          <span class="search-icon">🔍</span>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索知识库..."
            class="search-input"
            @input="handleSearch"
          />
        </div>
        <div class="filter-buttons">
          <button
            v-for="filter in filters"
            :key="filter.value"
            :class="['filter-btn', { active: activeFilter === filter.value }]"
            @click="activeFilter = filter.value"
          >
            <span class="filter-icon">{{ filter.icon }}</span>
            <span>{{ filter.label }}</span>
          </button>
        </div>
      </div>

      <div v-if="loading" class="loading-state">
        <div class="spinner-large"></div>
        <p>加载中...</p>
      </div>

      <div v-if="error" class="error-banner">
        <span class="error-icon">⚠️</span>
        <span>{{ error }}</span>
      </div>

      <div v-if="!loading && filteredKnowledgeBases.length === 0 && !searchQuery" class="empty-state">
        <div class="empty-icon">📚</div>
        <h2>还没有知识库</h2>
        <p>创建您的第一个知识库，开始管理知识文档</p>
        <button @click="goToCreate" class="btn-create-large">
          <span class="icon">✨</span>
          <span>创建第一个知识库</span>
        </button>
      </div>

      <div v-if="!loading && filteredKnowledgeBases.length === 0 && searchQuery" class="empty-state">
        <div class="empty-icon">🔍</div>
        <h2>未找到匹配的知识库</h2>
        <p>尝试使用其他关键词搜索</p>
      </div>

      <div v-if="!loading && filteredKnowledgeBases.length > 0" class="knowledge-grid">
        <div
          v-for="kb in filteredKnowledgeBases"
          :key="kb.id"
          class="knowledge-card"
          @click="goToDetail(kb.id)"
        >
          <div class="card-icon">
            📚
          </div>
          <div class="card-content">
            <div class="card-header">
              <h3>{{ kb.name }}</h3>
              <div class="card-actions" @click.stop>
                <button @click="goToEdit(kb.id)" class="action-btn" title="编辑">
                  <span>✏️</span>
                </button>
                <button @click="handleDelete(kb.id)" class="action-btn danger" title="删除">
                  <span>🗑️</span>
                </button>
              </div>
            </div>
            <p class="description">{{ kb.description || '暂无描述' }}</p>
            <div class="card-footer">
              <div class="badge">{{ kb.document_count || 0 }} 个文档</div>
              <span class="meta">{{ formatDate(kb.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'
import Navbar from '@/components/Navbar.vue'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const knowledgeBases = ref([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const activeFilter = ref('all')

const filters = [
  { value: 'all', label: '全部', icon: '📋' }
]

const filteredKnowledgeBases = computed(() => {
  let result = knowledgeBases.value

  // 按类型筛选 - 知识库没有 source_type，移除此过滤
  // if (activeFilter.value !== 'all') {
  //   result = result.filter(kb => kb.source_type === activeFilter.value)
  // }

  // 按搜索关键词筛选
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(kb => {
      const name = (kb.name || '').toLowerCase()
      const description = (kb.description || '').toLowerCase()
      return name.includes(query) || description.includes(query)
    })
  }

  return result
})

onMounted(async () => {
  await loadKnowledgeBases()
})

const loadKnowledgeBases = async () => {
  loading.value = true
  error.value = ''
  try {
    knowledgeBases.value = await knowledgeStore.fetchKnowledgeBases()
  } catch (err) {
    error.value = err.response?.data?.detail || '加载知识库失败'
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  // 搜索逻辑已在 computed 中处理
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
  if (!confirm('确定要删除这个知识库吗？此操作将删除知识库中的所有文档，且无法撤销。')) {
    return
  }

  try {
    await knowledgeStore.deleteKnowledgeBase(id)
    await loadKnowledgeBases()
  } catch (err) {
    error.value = err.response?.data?.detail || '删除知识库失败'
  }
}

const formatDate = (dateString) => {
  if (!dateString) return '未知'
  const date = new Date(dateString)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`

  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.knowledge-list-container {
  min-height: 100vh;
  background: linear-gradient(180deg, #f8f9ff 0%, #ffffff 100%);
}

.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  padding: 40px 24px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}

.header-left h1 {
  font-size: 36px;
  font-weight: 700;
  color: var(--gray-900);
  margin: 0 0 8px 0;
}

.subtitle {
  font-size: 16px;
  color: var(--gray-600);
  margin: 0;
}

.btn-create {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 24px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-md);
}

.btn-create:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.btn-create .icon {
  font-size: 18px;
}

.search-bar {
  background: white;
  border-radius: var(--radius-xl);
  padding: 24px;
  margin-bottom: 32px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--gray-200);
}

.search-input-wrapper {
  position: relative;
  margin-bottom: 16px;
}

.search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 20px;
  color: var(--gray-400);
}

.search-input {
  width: 100%;
  padding: 14px 16px 14px 48px;
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-lg);
  font-size: 15px;
  font-family: inherit;
  transition: all var(--transition-base);
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.filter-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--gray-100);
  color: var(--gray-700);
  border: 2px solid transparent;
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-base);
}

.filter-btn:hover {
  background: var(--gray-200);
}

.filter-btn.active {
  background: var(--primary-50);
  color: var(--primary-700);
  border-color: var(--primary-500);
}

.filter-icon {
  font-size: 16px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: var(--gray-500);
}

.spinner-large {
  width: 48px;
  height: 48px;
  border: 4px solid var(--gray-200);
  border-top-color: var(--primary-600);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: var(--radius-lg);
  margin-bottom: 24px;
  font-size: 14px;
  border: 1px solid #FCA5A5;
}

.error-icon {
  font-size: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 24px;
  opacity: 0.5;
}

.empty-state h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--gray-900);
  margin: 0 0 12px 0;
}

.empty-state p {
  font-size: 16px;
  color: var(--gray-600);
  margin: 0 0 32px 0;
}

.btn-create-large {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 32px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: var(--radius-xl);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-lg);
}

.btn-create-large:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-xl);
}

.btn-create-large .icon {
  font-size: 20px;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.knowledge-card {
  background: white;
  border-radius: var(--radius-xl);
  padding: 24px;
  cursor: pointer;
  transition: all var(--transition-base);
  border: 2px solid var(--gray-200);
  position: relative;
  overflow: hidden;
}

.knowledge-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--gradient-primary);
  transform: scaleX(0);
  transition: transform var(--transition-base);
}

.knowledge-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-xl);
  border-color: var(--primary-300);
}

.knowledge-card:hover::before {
  transform: scaleX(1);
}

.card-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  margin-bottom: 16px;
  box-shadow: var(--shadow-md);
}

.card-content {
  flex: 1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  gap: 12px;
}

.card-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--gray-900);
  margin: 0;
  flex: 1;
  line-height: 1.4;
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-base);
}

.knowledge-card:hover .card-actions {
  opacity: 1;
}

.action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-100);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 16px;
}

.action-btn:hover {
  background: var(--gray-200);
  transform: scale(1.1);
}

.action-btn.danger:hover {
  background: #FEE2E2;
}

.description {
  font-size: 14px;
  color: var(--gray-600);
  line-height: 1.6;
  margin: 0 0 16px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--gray-200);
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: var(--primary-100);
  color: var(--primary-700);
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

.meta {
  font-size: 12px;
  color: var(--gray-500);
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .knowledge-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
  }
}

@media (max-width: 768px) {
  .content-wrapper {
    padding: 24px 16px;
  }

  .header {
    flex-direction: column;
    gap: 20px;
  }

  .header-left h1 {
    font-size: 28px;
  }

  .btn-create {
    width: 100%;
    justify-content: center;
  }

  .knowledge-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .filter-buttons {
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 8px;
  }

  .filter-btn {
    white-space: nowrap;
  }
}
</style>
