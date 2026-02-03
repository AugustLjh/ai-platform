<template>
  <div class="knowledge-detail-wrapper">
    <Navbar />
    <div class="knowledge-detail-container">
    <div v-if="loading" class="loading">加载中...</div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="!loading && knowledgeBase">
      <div class="header">
        <button @click="goBack" class="btn-back">← 返回</button>
        <div class="header-content">
          <h1>{{ knowledgeBase.title || knowledgeBase.name }}</h1>
          <div class="header-actions">
            <button @click="goToEdit" class="btn-secondary">编辑</button>
            <button @click="handleDelete" class="btn-danger">删除</button>
          </div>
        </div>
      </div>

      <div class="info-card">
        <div class="info-row">
          <span class="label">内容：</span>
          <span class="value">{{ knowledgeBase.content || knowledgeBase.description || '暂无描述' }}</span>
        </div>
        <div class="info-row">
          <span class="label">来源：</span>
          <span class="value">{{ knowledgeBase.source || '手动创建' }}</span>
        </div>
        <div class="info-row">
          <span class="label">类型：</span>
          <span class="value">{{ knowledgeBase.source_type || 'manual' }}</span>
        </div>
        <div class="info-row">
          <span class="label">访问级别：</span>
          <span class="value">{{ knowledgeBase.access_level === 'tenant' ? '租户共享' : '个人私有' }}</span>
        </div>
        <div class="info-row">
          <span class="label">创建时间：</span>
          <span class="value">{{ formatDate(knowledgeBase.created_at) }}</span>
        </div>
      </div>

      <div class="documents-section">
        <div class="section-header">
          <h2>文档 ({{ documents.length }})</h2>
          <label class="btn-primary upload-btn">
            + 上传文档
            <input
              type="file"
              @change="handleFileUpload"
              accept=".txt,.pdf,.doc,.docx,.md"
              style="display: none"
            />
          </label>
        </div>

        <div v-if="uploadError" class="error">{{ uploadError }}</div>

        <div v-if="documents.length === 0" class="empty-state">
          <p>还没有文档</p>
          <p class="hint">上传第一个文档开始使用</p>
        </div>

        <div v-if="documents.length > 0" class="documents-list">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="document-item"
          >
            <div class="doc-icon">📄</div>
            <div class="doc-info">
              <div class="doc-name">{{ doc.title || doc.name }}</div>
              <div class="doc-meta">
                {{ doc.source_type || 'manual' }} • {{ formatDate(doc.created_at || doc.uploaded_at) }}
              </div>
            </div>
            <button
              @click="handleDeleteDocument(doc.id)"
              class="btn-icon-danger"
              title="删除"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'
import Navbar from '@/components/Navbar.vue'

const router = useRouter()
const route = useRoute()
const knowledgeStore = useKnowledgeStore()

const knowledgeBase = ref(null)
const documents = ref([])
const loading = ref(false)
const error = ref('')
const uploadError = ref('')

const knowledgeBaseId = route.params.id

onMounted(async () => {
  await loadKnowledgeBase()
  await loadDocuments()
})

const loadKnowledgeBase = async () => {
  loading.value = true
  error.value = ''
  try {
    knowledgeBase.value = await knowledgeStore.fetchKnowledgeBase(knowledgeBaseId)
  } catch (err) {
    error.value = err.response?.data?.error || '加载知识库失败'
  } finally {
    loading.value = false
  }
}

const loadDocuments = async () => {
  try {
    documents.value = await knowledgeStore.fetchDocuments(knowledgeBaseId)
  } catch (err) {
    console.error('加载文档失败:', err)
  }
}

const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return

  uploadError.value = ''
  try {
    await knowledgeStore.uploadDocument(knowledgeBaseId, file)
    await loadDocuments()
    event.target.value = ''
  } catch (err) {
    uploadError.value = err.response?.data?.error || '上传文档失败'
  }
}

const handleDeleteDocument = async (documentId) => {
  if (!confirm('确定要删除这个文档吗？')) {
    return
  }

  try {
    await knowledgeStore.deleteDocument(knowledgeBaseId, documentId)
    await loadDocuments()
  } catch (err) {
    uploadError.value = err.response?.data?.error || '删除文档失败'
  }
}

const handleDelete = async () => {
  if (!confirm('确定要删除这个知识库吗？此操作无法撤销。')) {
    return
  }

  try {
    await knowledgeStore.deleteKnowledgeBase(knowledgeBaseId)
    router.push('/knowledge')
  } catch (err) {
    error.value = err.response?.data?.error || '删除知识库失败'
  }
}

const goBack = () => {
  router.push('/knowledge')
}

const goToEdit = () => {
  router.push(`/knowledge/${knowledgeBaseId}/edit`)
}

const getTypeLabel = (type) => {
  const typeMap = {
    'general': '通用',
    'technical': '技术',
    'business': '商业',
    'personal': '个人'
  }
  return typeMap[type] || type || '通用'
}

const formatDate = (dateString) => {
  if (!dateString) return '未知'
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-CN')
}

const formatFileSize = (bytes) => {
  if (!bytes) return '未知'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.knowledge-detail-wrapper {
  min-height: 100vh;
  background: linear-gradient(180deg, #f8f9ff 0%, #ffffff 100%);
}

.knowledge-detail-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 40px 20px;
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

.header {
  margin-bottom: 32px;
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
  margin-bottom: 16px;
}

.btn-back:hover {
  background: #E5E7EB;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content h1 {
  font-size: 32px;
  color: #111827;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.btn-secondary {
  padding: 10px 20px;
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

.btn-danger {
  padding: 10px 20px;
  background: #DC2626;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-danger:hover {
  background: #B91C1C;
}

.info-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 32px;
}

.info-row {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid #F3F4F6;
}

.info-row:last-child {
  border-bottom: none;
}

.label {
  font-weight: 500;
  color: #6B7280;
  width: 150px;
}

.value {
  color: #111827;
  flex: 1;
}

.documents-section {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.section-header h2 {
  font-size: 20px;
  color: #111827;
  margin: 0;
}

.btn-primary {
  padding: 10px 20px;
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

.upload-btn {
  display: inline-block;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6B7280;
}

.empty-state p {
  margin: 8px 0;
}

.hint {
  font-size: 14px;
  color: #9CA3AF;
}

.documents-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  transition: background 0.2s;
}

.document-item:hover {
  background: #F3F4F6;
}

.doc-icon {
  font-size: 24px;
}

.doc-info {
  flex: 1;
}

.doc-name {
  font-weight: 500;
  color: #111827;
  margin-bottom: 4px;
}

.doc-meta {
  font-size: 12px;
  color: #6B7280;
}

.btn-icon-danger {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s;
}

.btn-icon-danger:hover {
  background: #FEE2E2;
}
</style>
