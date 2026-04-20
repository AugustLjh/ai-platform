<template>
  <div class="knowledge-list-container">
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
          <div class="folder-tab"></div>
          <div class="card-top">
            <div class="card-icon">📁</div>
            <div class="card-actions" @click.stop>
              <button @click="goToEdit(kb.id)" class="action-btn" title="编辑">
                <span>✏️</span>
              </button>
              <button @click="handleDelete(kb.id)" class="action-btn danger" title="删除">
                <span>🗑️</span>
              </button>
            </div>
          </div>
          <h3 class="card-title">{{ kb.name }}</h3>
          <p class="description">{{ kb.description || '暂无描述' }}</p>
          <div class="card-footer">
            <div class="badge">{{ kb.document_count || 0 }} 个文档</div>
            <div class="badge">{{ kb.access_level === 'user' ? '仅自己可见' : '租户共享' }}</div>
            <span class="meta">{{ formatDate(kb.created_at) }}</span>
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

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const knowledgeBases = ref([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const activeFilter = ref('all')

const filters = [
  { value: 'all', label: '全部', icon: '📋' },
  { value: 'tenant', label: '租户共享', icon: '🏢' },
  { value: 'user', label: '仅自己可见', icon: '👤' }
]

const filteredKnowledgeBases = computed(() => {
  let result = knowledgeBases.value

  if (activeFilter.value !== 'all') {
    result = result.filter(kb => kb.access_level === activeFilter.value)
  }

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
  flex: 1;
  min-height: 0;
  width: 100%;
  background: #f3f6fb;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.content-wrapper {
  flex: 1;
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 40px 24px;
  box-sizing: border-box;
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
  color: #0f172a;
  margin: 0 0 8px 0;
}

.subtitle {
  font-size: 16px;
  color: #64748b;
  margin: 0;
}

.btn-create {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 24px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
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
  background: #ffffff;
  border-radius: var(--radius-xl);
  padding: 24px;
  margin-bottom: 32px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  border: 1px solid #e2e8f0;
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
  color: #94a3b8;
}

.search-input {
  width: 100%;
  padding: 14px 16px 14px 48px;
  border: 1px solid #dbe2ec;
  border-radius: var(--radius-lg);
  font-size: 15px;
  font-family: inherit;
  transition: all var(--transition-base);
  background: #ffffff;
  color: #0f172a;
}

.search-input:focus {
  outline: none;
  border-color: #93a4b8;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
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
  background: #f8fafc;
  color: #64748b;
  border: 1px solid #dbe2ec;
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-base);
}

.filter-btn:hover {
  background: #f1f5f9;
  color: #334155;
}

.filter-btn.active {
  background: #eef2ff;
  color: #1e293b;
  border-color: #93a4b8;
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
  color: #64748b;
}

.spinner-large {
  width: 48px;
  height: 48px;
  border: 4px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: var(--radius-lg);
  margin-bottom: 24px;
  font-size: 14px;
  border: 1px solid #fca5a5;
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
  color: #0f172a;
  margin: 0 0 12px 0;
}

.empty-state p {
  font-size: 16px;
  color: #64748b;
  margin: 0 0 32px 0;
}

.btn-create-large {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 32px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
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
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.knowledge-card {
  background: #ffffff;
  border-radius: 14px;
  padding: 22px 14px 14px;
  cursor: pointer;
  transition: all var(--transition-base);
  border: 1px solid #e2e8f0;
  position: relative;
  overflow: visible;
  min-height: 150px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.folder-tab {
  position: absolute;
  top: -10px;
  left: 14px;
  width: 74px;
  height: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
}

.knowledge-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.14);
  border-color: #93a4b8;
}

.card-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: #eef2ff;
  border-radius: 10px;
  color: #1e293b;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 8px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  margin: 0 0 8px 0;
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
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 14px;
}

.action-btn:hover {
  background: #e2e8f0;
  transform: scale(1.1);
}

.action-btn.danger:hover {
  background: #fee2e2;
}

.description {
  font-size: 12px;
  color: #64748b;
  line-height: 1.6;
  margin: 0 0 12px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px dashed #dbe2ec;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: #eef2ff;
  color: #334155;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

.meta {
  font-size: 12px;
  color: #64748b;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .knowledge-grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px;
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

  .card-actions {
    opacity: 1;
  }
}
</style>
