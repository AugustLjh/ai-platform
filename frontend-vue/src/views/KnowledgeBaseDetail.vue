<template>
  <div class="knowledge-detail-wrapper">
    <div class="knowledge-detail-container">
      <div v-if="loading" class="loading">加载中...</div>

      <div v-if="error" class="error-banner">
        <span class="error-icon">⚠️</span>
        <span>{{ error }}</span>
      </div>

      <div v-if="!loading && knowledgeBase" class="docs-page">
        <div class="page-header">
          <div class="title-group">
            <div class="title-row">
              <button class="back-btn" @click="goBack" title="返回">←</button>
              <h1>{{ knowledgeBase.name }}</h1>
              <span class="count-pill">{{ totalCount }}</span>
              <span class="count-pill">{{ getAccessLevelLabel(knowledgeBase.access_level) }}</span>
            </div>
            <p class="subtitle">
              {{ knowledgeBase.description || '管理当前知识库中的文档、预览切分结果，并直接验证入库状态。' }}
            </p>
          </div>
          <div class="header-actions">
            <button @click="goToSettings" class="btn-secondary">知识库设置</button>
            <button @click="goToRetrievalTest" class="btn-secondary">召回测试</button>
            <button @click="goToEdit" class="btn-secondary">元数据</button>
            <label class="btn-primary upload-btn">
              <span class="plus">+</span>
              添加文件
              <input
                type="file"
                @change="handleFileUpload"
                accept=".txt,.text,.log,.md,.markdown,.pdf,.html,.htm,.csv,.tsv,.xlsx,.docx,.rtf,.pptx,.json,.jsonl,.yaml,.yml,.xml"
                style="display: none"
              />
            </label>
          </div>
        </div>

        <div class="toolbar">
          <div class="filter-select">
            <select v-model="statusFilter">
              <option v-for="option in statusOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <div class="search-input">
            <span class="search-icon">🔍</span>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索"
            />
          </div>
        </div>

        <div v-if="uploadError" class="error-banner subtle">
          <span class="error-icon">⚠️</span>
          <span>{{ uploadError }}</span>
        </div>

        <div v-if="filteredDocuments.length > 0" class="table-card">
          <div class="table-row table-header">
            <div class="col col-check"><span class="checkbox"></span></div>
            <div class="col col-index">#</div>
            <div class="col col-name">名称</div>
            <div class="col col-mode">类型</div>
            <div class="col col-chars">大小</div>
            <div class="col col-recall">更新时间</div>
            <div class="col col-date">上传时间</div>
            <div class="col col-status">状态</div>
            <div class="col col-actions">操作</div>
          </div>
          <div
            v-for="(doc, index) in filteredDocuments"
            :key="doc.id"
            class="table-row"
          >
            <div class="col col-check"><span class="checkbox"></span></div>
            <div class="col col-index">{{ index + 1 }}</div>
            <div class="col col-name">
              <div class="name-cell">
                <span class="doc-title">{{ doc.title }}</span>
              </div>
            </div>
            <div class="col col-mode">
              <span class="pill">{{ getFileType(doc) }}</span>
            </div>
            <div class="col col-chars">{{ formatFileSize(getDocumentSize(doc)) }}</div>
            <div class="col col-recall">
              {{ formatDateTime(doc.updated_at || doc.created_at) }}
            </div>
            <div class="col col-date">
              {{ formatDateTime(doc.created_at) }}
            </div>
            <div class="col col-status">
              <span :class="['status-dot', `status-${getStatus(doc)}`]"></span>
              <span :class="['status-text', `status-${getStatus(doc)}`]">
                {{ getStatusLabel(doc) }}
              </span>
            </div>
            <div class="col col-actions">
              <button
                @click="handlePreviewDocument(doc)"
                class="icon-btn"
                title="预览文档"
              >
                👁️
              </button>
              <button
                @click="handleViewSegments(doc)"
                class="icon-btn"
                title="查看分段"
              >
                🧩
              </button>
              <button
                @click="handleDeleteDocument(doc.id)"
                class="icon-btn"
                title="删除"
              >
                🗑️
              </button>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <div class="empty-icon">📄</div>
          <div class="empty-title">还没有文档</div>
          <div class="empty-subtitle">上传第一个文档开始使用</div>
        </div>

        <div v-if="showPreviewModal" class="modal-overlay" @click.self="closePreviewModal">
          <div class="modal-card">
            <div class="modal-header">
              <h3>文档预览 · {{ selectedDocument?.title || '-' }}</h3>
              <button class="modal-close" @click="closePreviewModal">✕</button>
            </div>
            <div v-if="modalLoading" class="modal-loading">加载中...</div>
            <div v-else-if="modalError" class="error-banner subtle">
              <span class="error-icon">⚠️</span>
              <span>{{ modalError }}</span>
            </div>
            <div v-else-if="previewData" class="modal-content">
              <div class="preview-meta">
                <span>总字符：{{ previewData.total_chars }}</span>
                <span>预览长度：{{ previewData.preview_chars }}</span>
                <span>状态：{{ previewData.truncated ? '已截断' : '完整' }}</span>
              </div>
              <div v-if="selectedDocumentAiMeta.hasContent" class="ai-insight-panel">
                <div class="ai-insight-header">
                  <span class="ai-insight-title">AI 加工结果</span>
                  <span v-if="selectedDocumentAiMeta.documentType" class="insight-pill">
                    {{ selectedDocumentAiMeta.documentType }}
                  </span>
                </div>
                <p v-if="selectedDocumentAiMeta.summary" class="ai-summary">
                  {{ selectedDocumentAiMeta.summary }}
                </p>
                <div v-if="selectedDocumentAiMeta.keywords.length" class="insight-tags">
                  <span
                    v-for="keyword in selectedDocumentAiMeta.keywords"
                    :key="keyword"
                    class="insight-tag"
                  >
                    {{ keyword }}
                  </span>
                </div>
                <div v-if="selectedDocumentAiMeta.faq.length" class="faq-list">
                  <div
                    v-for="(item, index) in selectedDocumentAiMeta.faq"
                    :key="`${index}-${item.question}`"
                    class="faq-card"
                  >
                    <div class="faq-question">{{ item.question }}</div>
                    <div class="faq-answer">{{ item.answer }}</div>
                  </div>
                </div>
              </div>
              <pre class="preview-text">{{ previewData.preview }}</pre>
            </div>
          </div>
        </div>

        <div v-if="showSegmentsModal" class="modal-overlay" @click.self="closeSegmentsModal">
          <div class="modal-card modal-wide">
            <div class="modal-header">
              <h3>分段详情 · {{ selectedDocument?.title || '-' }}</h3>
              <button class="modal-close" @click="closeSegmentsModal">✕</button>
            </div>
            <div class="segment-toolbar">
              <div class="segment-field">
                <label>索引方式</label>
                <select v-model="segmentIndexingMethod">
                  <option value="structured">自然结构分块</option>
                  <option value="paragraph">按段落分块</option>
                  <option value="chunk">固定长度分块</option>
                  <option value="full">整篇索引</option>
                </select>
              </div>
              <div class="segment-field">
                <label>分段大小</label>
                <input v-model.number="segmentChunkSize" type="number" min="50" max="2000" />
              </div>
              <div class="segment-field">
                <label>重叠大小</label>
                <input v-model.number="segmentChunkOverlap" type="number" min="0" max="500" />
              </div>
              <button class="btn-secondary" @click="reloadSegments" :disabled="modalLoading">重新切分</button>
            </div>

            <div v-if="modalLoading" class="modal-loading">加载中...</div>
            <div v-else-if="modalError" class="error-banner subtle">
              <span class="error-icon">⚠️</span>
              <span>{{ modalError }}</span>
            </div>
            <div v-else-if="segmentsData" class="modal-content">
              <div class="preview-meta">
                <span>索引方式：{{ segmentsData.indexing_method }}</span>
                <span>分段大小：{{ segmentsData.chunk_size }}</span>
                <span>重叠：{{ segmentsData.chunk_overlap }}</span>
                <span>总分段：{{ segmentsData.total_segments }}</span>
                <span v-if="segmentsData.truncated">仅展示前 {{ segmentsData.returned_segments }} 段</span>
              </div>
              <div class="segments-list">
                <div v-for="segment in segmentsData.segments" :key="segment.segment_index" class="segment-card">
                  <div class="segment-head">
                    <strong>#{{ segment.segment_index }}</strong>
                    <span v-if="segment.citation_label">{{ segment.citation_label }}</span>
                    <span v-else-if="segment.section_title">{{ segment.section_title }}</span>
                    <span v-if="segment.segment_type">{{ segment.segment_type }}</span>
                    <span>{{ segment.start_offset }} - {{ segment.end_offset }}</span>
                    <span>{{ segment.char_count }} 字符</span>
                  </div>
                  <pre class="segment-content">{{ segment.content }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'

const router = useRouter()
const route = useRoute()
const knowledgeStore = useKnowledgeStore()

const knowledgeBase = ref(null)
const documents = ref([])
const loading = ref(false)
const error = ref('')
const uploadError = ref('')
const searchQuery = ref('')
const statusFilter = ref('all')
const showPreviewModal = ref(false)
const showSegmentsModal = ref(false)
const selectedDocument = ref(null)
const previewData = ref(null)
const segmentsData = ref(null)
const modalLoading = ref(false)
const modalError = ref('')
const segmentIndexingMethod = ref('structured')
const segmentChunkSize = ref(500)
const segmentChunkOverlap = ref(50)
const textEncoder = new TextEncoder()

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'available', label: '可用' },
  { value: 'processing', label: '处理中' },
  { value: 'failed', label: '失败' }
]

const knowledgeBaseId = route.params.id

const totalCount = computed(() => {
  if (knowledgeBase.value && typeof knowledgeBase.value.document_count === 'number') {
    return knowledgeBase.value.document_count
  }
  return documents.value.length
})

const filteredDocuments = computed(() => {
  let result = documents.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(doc => {
      const name = (doc.title || '').toLowerCase()
      return name.includes(query)
    })
  }

  if (statusFilter.value !== 'all') {
    result = result.filter(doc => getStatus(doc) === statusFilter.value)
  }

  return result
})

const selectedDocumentAiMeta = computed(() => {
  const metadata = normalizeMetadata(selectedDocument.value?.metadata)
  const keywords = normalizeStringList(metadata.ai_keywords || metadata.ai_tags)
  const faq = normalizeFaqList(metadata.ai_faq)
  const summary = typeof metadata.ai_summary === 'string' ? metadata.ai_summary : ''
  const documentType = typeof metadata.ai_document_type === 'string' ? metadata.ai_document_type : ''

  return {
    summary,
    keywords,
    faq,
    documentType,
    hasContent: Boolean(summary || keywords.length || faq.length || documentType)
  }
})

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
    if (knowledgeBase.value) {
      knowledgeBase.value.document_count = knowledgeStore.pagination.total || documents.value.length
    }
  } catch (err) {
    console.error('加载文档失败:', err)
  }
}

const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return

  uploadError.value = ''
  try {
    await knowledgeStore.uploadDocument(knowledgeBaseId, file, {
      accessLevel: knowledgeBase.value?.access_level || 'tenant'
    })
    await loadDocuments()
    event.target.value = ''
  } catch (err) {
    if (isDuplicateConflict(err)) {
      const detail = extractApiDetail(err)
      const shouldContinue = window.confirm(buildDuplicateConfirmMessage(detail))
      if (shouldContinue) {
        try {
          await knowledgeStore.uploadDocument(knowledgeBaseId, file, {
            accessLevel: knowledgeBase.value?.access_level || 'tenant',
            skipDuplicateCheck: true
          })
          await loadDocuments()
        } catch (retryErr) {
          uploadError.value = extractApiErrorMessage(retryErr, '上传文档失败')
        }
      }
      event.target.value = ''
      return
    }
    uploadError.value = extractApiErrorMessage(err, '上传文档失败')
  }
}

const handleDeleteDocument = async (documentId) => {
  if (!confirm('确定要删除这个文档吗？')) {
    return
  }

  try {
    await knowledgeStore.deleteDocument(documentId)
    await loadDocuments()
  } catch (err) {
    uploadError.value = extractApiErrorMessage(err, '删除文档失败')
  }
}

const closePreviewModal = () => {
  showPreviewModal.value = false
  previewData.value = null
  modalError.value = ''
}

const closeSegmentsModal = () => {
  showSegmentsModal.value = false
  segmentsData.value = null
  modalError.value = ''
}

const handlePreviewDocument = async (doc) => {
  selectedDocument.value = doc
  showPreviewModal.value = true
  previewData.value = null
  modalError.value = ''
  modalLoading.value = true
  try {
    previewData.value = await knowledgeStore.fetchDocumentPreview(doc.id, 6000)
  } catch (err) {
    modalError.value = err.response?.data?.detail || '加载文档预览失败'
  } finally {
    modalLoading.value = false
  }
}

const handleViewSegments = async (doc) => {
  selectedDocument.value = doc
  showSegmentsModal.value = true
  segmentsData.value = null
  modalError.value = ''
  modalLoading.value = true
  try {
    const data = await knowledgeStore.fetchDocumentSegments(doc.id)
    segmentsData.value = data
    segmentIndexingMethod.value = data.indexing_method || 'structured'
    segmentChunkSize.value = data.chunk_size
    segmentChunkOverlap.value = data.chunk_overlap
  } catch (err) {
    modalError.value = err.response?.data?.detail || '加载分段详情失败'
  } finally {
    modalLoading.value = false
  }
}

const reloadSegments = async () => {
  if (!selectedDocument.value) return

  modalError.value = ''
  modalLoading.value = true
  try {
    segmentsData.value = await knowledgeStore.fetchDocumentSegments(selectedDocument.value.id, {
      indexing_method: segmentIndexingMethod.value,
      chunk_size: segmentChunkSize.value,
      chunk_overlap: segmentChunkOverlap.value,
      max_segments: 400
    })
  } catch (err) {
    modalError.value = err.response?.data?.detail || '重新切分失败'
  } finally {
    modalLoading.value = false
  }
}

const goBack = () => {
  router.push('/knowledge')
}

const goToEdit = () => {
  router.push(`/knowledge/${knowledgeBaseId}/edit`)
}

const goToSettings = () => {
  router.push(`/knowledge/${knowledgeBaseId}/settings`)
}

const goToRetrievalTest = () => {
  router.push(`/knowledge/${knowledgeBaseId}/retrieval-test`)
}

const getFileType = (doc) => {
  if (doc.source_type) return doc.source_type.toUpperCase()
  const name = doc.title || ''
  const index = name.lastIndexOf('.')
  if (index === -1) return '-'
  return name.slice(index + 1).toUpperCase()
}

const getStatus = (doc) => {
  if (doc.index_status === 'failed' || doc.last_index_error) return 'failed'
  if (doc.index_status === 'ready' || doc.indexed) return 'available'
  if (doc.index_status === 'running' || doc.index_status === 'pending') return 'processing'
  return 'processing'
}

const getStatusLabel = (doc) => {
  const status = getStatus(doc)
  if (status === 'available') return '可用'
  if (status === 'processing') return '处理中'
  if (status === 'failed') return '失败'
  return '可用'
}

const getAccessLevelLabel = (accessLevel) => (
  accessLevel === 'user' ? '仅自己可见' : '租户共享'
)

const getDocumentSize = (doc) => {
  const metadata = normalizeMetadata(doc.metadata)
  if (typeof metadata.file_size === 'number') return metadata.file_size
  if (typeof metadata.size === 'number') return metadata.size
  if (typeof metadata.content_length === 'number') return metadata.content_length
  return textEncoder.encode(doc.content || '').length
}

const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const formatFileSize = (bytes) => {
  if (typeof bytes !== 'number') return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

const normalizeMetadata = (metadata) => {
  if (!metadata) return {}
  if (typeof metadata === 'string') {
    try {
      return JSON.parse(metadata)
    } catch (_error) {
      return {}
    }
  }
  return metadata
}

const normalizeStringList = (value) => {
  const raw = typeof value === 'string'
    ? (() => {
        try {
          return JSON.parse(value)
        } catch (_error) {
          return value.split(/[，,]/).map(item => item.trim())
        }
      })()
    : value

  if (!Array.isArray(raw)) return []

  return raw
    .map(item => typeof item === 'string' ? item.trim() : '')
    .filter(Boolean)
}

const normalizeFaqList = (value) => {
  const raw = typeof value === 'string'
    ? (() => {
        try {
          return JSON.parse(value)
        } catch (_error) {
          return []
        }
      })()
    : value

  if (!Array.isArray(raw)) return []

  return raw
    .map(item => ({
      question: typeof item?.question === 'string' ? item.question.trim() : '',
      answer: typeof item?.answer === 'string' ? item.answer.trim() : ''
    }))
    .filter(item => item.question && item.answer)
}

const extractApiDetail = (error) => {
  return error?.response?.data?.detail ?? error?.response?.data?.error ?? null
}

const extractApiErrorMessage = (error, fallback) => {
  const detail = extractApiDetail(error)
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (detail && typeof detail.message === 'string' && detail.message.trim()) {
    return detail.message
  }
  return fallback
}

const isDuplicateConflict = (error) => {
  const detail = extractApiDetail(error)
  return error?.response?.status === 409 && detail?.code === 'duplicate_document_detected'
}

const formatDuplicateItems = (items, formatter) => {
  return items
    .slice(0, 3)
    .map((item, index) => `${index + 1}. ${formatter(item)}`)
    .join('\n')
}

const buildDuplicateConfirmMessage = (detail) => {
  const duplicateCheck = detail?.duplicate_check || {}
  const exactMatches = Array.isArray(duplicateCheck.exact_matches) ? duplicateCheck.exact_matches : []
  const similarMatches = Array.isArray(duplicateCheck.similar_matches) ? duplicateCheck.similar_matches : []
  const lines = [
    typeof detail?.message === 'string' ? detail.message : '发现重复或高相似文档。'
  ]

  if (exactMatches.length) {
    lines.push('')
    lines.push('重复文档：')
    lines.push(formatDuplicateItems(exactMatches, item => `${item.title || '未命名文档'}${item.source ? ` (${item.source})` : ''}`))
  }

  if (similarMatches.length) {
    lines.push('')
    lines.push('高相似文档：')
    lines.push(formatDuplicateItems(similarMatches, item => {
      const similarity = typeof item.similarity === 'number' ? `，相似度 ${(item.similarity * 100).toFixed(1)}%` : ''
      return `${item.title || '未命名文档'}${similarity}`
    }))
  }

  lines.push('')
  lines.push('继续上传会保留一份新的副本，是否继续？')

  return lines.join('\n')
}
</script>

<style scoped>
.knowledge-detail-wrapper {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: #f3f6fb;
  display: flex;
  flex-direction: column;
  overflow: auto;
  color: #0f172a;
}

.knowledge-detail-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px 56px;
  width: 100%;
  box-sizing: border-box;
}

.loading {
  text-align: center;
  padding: 60px 20px;
  color: #64748b;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.16);
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.4);
  margin-bottom: 16px;
  font-size: 14px;
}

.error-banner.subtle {
  margin-top: 16px;
}

.error-icon {
  font-size: 16px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.title-row h1 {
  font-size: 26px;
  font-weight: 600;
  margin: 0;
  color: #0f172a;
}

.back-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #d0d7e2;
  background: #ffffff;
  color: #334155;
  cursor: pointer;
  transition: all 0.2s ease;
}

.back-btn:hover {
  background: #f1f5f9;
  color: #1e293b;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #334155;
  font-size: 12px;
  border: 1px solid #dbe2ec;
}

.subtitle {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  line-height: 1.6;
  max-width: 720px;
}

.learn-more {
  color: #2563eb;
  margin-left: 6px;
  cursor: pointer;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-secondary {
  padding: 10px 18px;
  background: #ffffff;
  color: #1e293b;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  border-color: #93a4b8;
  color: #1e293b;
}

.btn-primary {
  padding: 10px 18px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.35);
}

.btn-primary:hover {
  filter: brightness(1.05);
}

.plus {
  font-size: 18px;
  line-height: 1;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.filter-select select {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 13px;
  min-width: 160px;
  outline: none;
}

.filter-select select:focus {
  border-color: #93a4b8;
}

.search-input {
  position: relative;
  width: 280px;
}

.search-input input {
  width: 100%;
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  padding: 10px 12px 10px 36px;
  font-size: 13px;
  outline: none;
}

.search-input input::placeholder {
  color: #94a3b8;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 14px;
  color: #94a3b8;
}

.table-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
}

.table-row {
  display: grid;
  grid-template-columns: 36px 44px 2.6fr 1fr 0.9fr 0.9fr 1.2fr 0.9fr 1.2fr;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  font-size: 13px;
  color: #334155;
}

.table-row:not(.table-header) {
  border-top: 1px solid #e2e8f0;
}

.table-row:not(.table-header):hover {
  background: #f8fafc;
}

.table-header {
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
}

.col-index {
  color: #64748b;
}

.checkbox {
  display: inline-block;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid #dbe2ec;
  background: #ffffff;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-title {
  color: #0f172a;
  font-weight: 500;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pill {
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  border: 1px solid #dbe2ec;
  color: #334155;
  font-size: 12px;
}

.col-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
}

.status-dot.status-processing {
  background: #f59e0b;
  box-shadow: 0 0 6px rgba(245, 158, 11, 0.6);
}

.status-dot.status-failed {
  background: #ef4444;
  box-shadow: 0 0 6px rgba(239, 68, 68, 0.6);
}

.status-text {
  color: #15803d;
  font-size: 12px;
}

.status-text.status-processing {
  color: #b45309;
}

.status-text.status-failed {
  color: #b91c1c;
}

.col-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #d0d7e2;
  background: #ffffff;
  color: #1e293b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:hover {
  background: #f1f5f9;
  color: #1e293b;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
  color: #64748b;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 18px;
  color: #0f172a;
  margin-bottom: 6px;
}

.empty-subtitle {
  font-size: 13px;
  color: #64748b;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 60;
}

.modal-card {
  width: min(980px, 100%);
  max-height: 88vh;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-wide {
  width: min(1180px, 100%);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #e2e8f0;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  color: #0f172a;
}

.modal-close {
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 16px;
}

.modal-content {
  padding: 16px 18px;
  overflow: auto;
}

.modal-loading {
  padding: 24px 18px;
  color: #64748b;
}

.preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 12px;
}

.ai-insight-panel {
  background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%);
  border: 1px solid #d7e8ff;
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 16px;
}

.ai-insight-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.ai-insight-title {
  font-size: 13px;
  font-weight: 700;
  color: #1d4ed8;
  letter-spacing: 0.02em;
}

.insight-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.ai-summary {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.7;
  color: #1e293b;
}

.insight-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.insight-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #ffffff;
  color: #2563eb;
  border: 1px solid #cfe0ff;
  font-size: 12px;
  font-weight: 500;
}

.faq-list {
  display: grid;
  gap: 10px;
}

.faq-card {
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid #dbe7f5;
  border-radius: 12px;
  padding: 12px 14px;
}

.faq-question {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 6px;
}

.faq-answer {
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
}

.preview-text,
.segment-content {
  margin: 0;
  background: #f8fafc;
  border: 1px solid #d6deea;
  border-radius: 10px;
  padding: 12px;
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.segment-toolbar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #e2e8f0;
}

.segment-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.segment-field label {
  font-size: 12px;
  color: #64748b;
}

.segment-field input,
.segment-field select {
  width: 140px;
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
}

.segments-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.segment-card {
  background: #f8fafc;
  border: 1px solid #d6deea;
  border-radius: 10px;
  padding: 10px;
}

.segment-head {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
}

@media (max-width: 1024px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .search-input {
    width: 100%;
  }

  .table-card {
    overflow-x: auto;
  }

  .table-row {
    min-width: 900px;
  }
}
</style>
