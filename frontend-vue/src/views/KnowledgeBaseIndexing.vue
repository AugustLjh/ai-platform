<template>
  <div class="kb-settings-wrapper">
    <div class="kb-settings-container">
      <div v-if="loading" class="loading">加载中...</div>

      <div v-if="error" class="error-banner">
        <span class="error-icon">⚠️</span>
        <span>{{ error }}</span>
      </div>

      <div v-if="!loading" class="settings-content">
        <div class="page-header">
          <div>
            <div class="title-row">
              <button class="back-btn" @click="goBack" title="返回">←</button>
              <h1>索引方式</h1>
            </div>
            <p class="subtitle">
              配置知识库的切分与向量索引方式，影响文档入库与检索效果。
            </p>
          </div>
          <div class="header-actions">
            <button class="btn-secondary" @click="goToRetrieval">检索方式</button>
            <button class="btn-primary" :disabled="saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-title">索引设置</div>

          <div class="form-row">
            <label>索引方式</label>
            <select v-model="form.indexing_method">
              <option value="chunk">分块索引</option>
              <option value="full">整篇索引</option>
            </select>
          </div>

          <div class="form-grid" v-if="form.indexing_method === 'chunk'">
            <div class="form-row">
              <label>分块长度</label>
              <input type="number" min="50" max="2000" step="50" v-model.number="form.chunk_size" />
            </div>
            <div class="form-row">
              <label>重叠长度</label>
              <input type="number" min="0" max="500" step="10" v-model.number="form.chunk_overlap" />
            </div>
          </div>

          <div class="section-title">Embedding 模型</div>
          <div class="form-row">
            <label>向量模型</label>
            <select v-model="form.embedding_model_id" :disabled="modelsLoading">
              <option value="">不指定</option>
              <option v-for="model in embeddingModels" :key="model.id" :value="model.id">
                {{ model.display_name }} ({{ model.model_id }})
              </option>
            </select>
          </div>
          <div v-if="embeddingModels.length === 0" class="hint">
            暂无可用模型，请先在“模型管理”中添加或启用。
            <span class="hint-link" @click="goToModels">前往模型管理</span>
          </div>
        </div>

        <div v-if="success" class="success-banner">{{ success }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'
import { useModelsStore } from '@/store/models'

const router = useRouter()
const route = useRoute()
const knowledgeStore = useKnowledgeStore()
const modelsStore = useModelsStore()

const knowledgeBaseId = route.params.id

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const form = ref({
  indexing_method: 'chunk',
  chunk_size: 500,
  chunk_overlap: 50,
  embedding_model_id: ''
})

const embeddingModels = computed(() => modelsStore.enabledEmbeddingModels)
const modelsLoading = computed(() => modelsStore.loading)

const loadSettings = async () => {
  loading.value = true
  error.value = ''
  try {
    const settings = await knowledgeStore.fetchIndexingSettings(knowledgeBaseId)
    form.value = {
      indexing_method: settings.indexing_method || 'chunk',
      chunk_size: settings.chunk_size ?? 500,
      chunk_overlap: settings.chunk_overlap ?? 50,
      embedding_model_id: settings.embedding_model_id || ''
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '加载索引设置失败'
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const payload = {
      ...form.value,
      embedding_model_id: form.value.embedding_model_id || null
    }
    await knowledgeStore.updateIndexingSettings(knowledgeBaseId, payload)
    success.value = '索引设置已保存'
  } catch (err) {
    error.value = err.response?.data?.detail || '保存索引设置失败'
  } finally {
    saving.value = false
  }
}

const goBack = () => {
  router.push(`/knowledge/${knowledgeBaseId}`)
}

const goToRetrieval = () => {
  router.push(`/knowledge/${knowledgeBaseId}/retrieval`)
}

const goToModels = () => {
  router.push('/models')
}

onMounted(async () => {
  await loadSettings()
  try {
    await modelsStore.fetchModels()
  } catch (err) {
    console.error('Failed to load models:', err)
  }
})
</script>

<style scoped>
.kb-settings-wrapper {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: #f3f6fb;
  display: flex;
  flex-direction: column;
  overflow: auto;
  color: #0f172a;
}

.kb-settings-container {
  max-width: 1000px;
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

.error-icon {
  font-size: 16px;
}

.success-banner {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(34, 197, 94, 0.15);
  color: #047857;
  border: 1px solid rgba(34, 197, 94, 0.4);
  font-size: 14px;
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
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  color: #0f172a;
}

.subtitle {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  line-height: 1.6;
  max-width: 640px;
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
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

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.settings-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 16px 0;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.form-row label {
  font-size: 13px;
  color: #64748b;
}

.form-row input,
.form-row select {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
}

.form-row input:focus,
.form-row select:focus {
  border-color: #93a4b8;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.hint {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.hint-link {
  color: #2563eb;
  cursor: pointer;
  margin-left: 6px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
