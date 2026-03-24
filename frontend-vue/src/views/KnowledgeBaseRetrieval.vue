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
              <h1>检索方式</h1>
            </div>
            <p class="subtitle">
              配置检索策略与重排模型，决定命中范围与排序质量。
            </p>
          </div>
          <div class="header-actions">
            <button class="btn-secondary" @click="goToIndexing">索引方式</button>
            <button class="btn-primary" :disabled="saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-title">检索设置</div>

          <div class="form-row">
            <label>检索方式</label>
            <select v-model="form.retrieval_method">
              <option value="vector">向量检索</option>
              <option value="keyword">关键词检索</option>
              <option value="hybrid">混合检索</option>
            </select>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>召回数量 Top K</label>
              <input type="number" min="1" max="50" step="1" v-model.number="form.top_k" />
            </div>
            <div class="form-row">
              <label>相似度阈值</label>
              <input type="number" min="0" max="1" step="0.01" v-model.number="form.score_threshold" />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>向量候选数</label>
              <input type="number" min="1" max="200" step="1" v-model.number="form.vector_top_k" />
            </div>
            <div class="form-row">
              <label>关键词候选数</label>
              <input type="number" min="1" max="200" step="1" v-model.number="form.keyword_top_k" />
            </div>
            <div class="form-row">
              <label>融合算法</label>
              <select v-model="form.fusion_algorithm">
                <option value="rrf">RRF</option>
              </select>
            </div>
            <div class="form-row">
              <label>RRF K</label>
              <input type="number" min="1" max="200" step="1" v-model.number="form.rrf_k" />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>向量权重</label>
              <input type="number" min="0" max="5" step="0.05" v-model.number="form.vector_weight" />
            </div>
            <div class="form-row">
              <label>关键词权重</label>
              <input type="number" min="0" max="5" step="0.05" v-model.number="form.keyword_weight" />
            </div>
            <div class="form-row">
              <label>最大候选数</label>
              <input type="number" min="1" max="300" step="1" v-model.number="form.max_candidates" />
            </div>
          </div>

          <div class="form-row toggle-row">
            <label>查询改写</label>
            <input type="checkbox" v-model="form.query_rewrite" />
          </div>

          <div class="section-title">Rerank 设置</div>
          <div class="form-row toggle-row">
            <label>启用 Rerank</label>
            <input type="checkbox" v-model="form.enable_rerank" />
          </div>

          <div class="form-row">
            <label>Rerank 模型</label>
            <select v-model="form.rerank_model_id" :disabled="modelsLoading || !form.enable_rerank">
              <option value="">不指定</option>
              <option v-for="model in rerankModels" :key="model.id" :value="model.id">
                {{ model.display_name }} ({{ model.model_id }})
              </option>
            </select>
          </div>
          <div v-if="rerankModels.length === 0" class="hint">
            暂无可用模型，请先在“模型管理”中添加或启用。
            <span class="hint-link" @click="goToModels">前往模型管理</span>
          </div>
        </div>

        <div class="settings-card test-card">
          <div class="section-title">召回测试</div>

          <div class="form-row">
            <label>测试问题</label>
            <textarea v-model="testQuery" placeholder="输入一个问题，测试当前检索设置的召回效果"></textarea>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>测试 Top K（可选）</label>
              <input type="number" min="1" max="50" step="1" v-model.number="testTopK" />
            </div>
            <div class="form-row">
              <label>测试阈值（可选）</label>
              <input type="number" min="0" max="1" step="0.01" v-model.number="testScoreThreshold" />
            </div>
          </div>

          <button class="btn-secondary" :disabled="testing || !testQuery.trim()" @click="runRetrievalTest">
            {{ testing ? '测试中...' : '开始召回测试' }}
          </button>

          <div v-if="testError" class="error-banner test-error">
            <span class="error-icon">⚠️</span>
            <span>{{ testError }}</span>
          </div>

          <div v-if="testMeta" class="test-meta">
            <span>检索方式：{{ testMeta.retrieval_method }}</span>
            <span>Top K：{{ testMeta.top_k }}</span>
            <span>阈值：{{ testMeta.score_threshold }}</span>
            <span>命中：{{ testMeta.total }}</span>
          </div>

          <div v-if="testResults.length > 0" class="test-results">
            <div v-for="(item, idx) in testResults" :key="item.document.id" class="test-result-item">
              <div class="result-head">
                <strong>{{ idx + 1 }}. {{ item.document.title }}</strong>
                <span>Score: {{ item.score.toFixed(4) }}</span>
              </div>
              <div class="result-source">{{ item.document.source || '-' }}</div>
              <div class="result-segments">
                <div v-for="segment in item.matched_segments" :key="`${item.document.id}-${segment.segment_index}`" class="segment-item">
                  <div class="segment-head">
                    <span>#{{ segment.segment_index }}</span>
                    <span v-if="segment.citation_label">{{ segment.citation_label }}</span>
                    <span v-else-if="segment.section_title">{{ segment.section_title }}</span>
                    <span>{{ segment.start_offset }} - {{ segment.end_offset }}</span>
                    <span>匹配 {{ segment.match_score ?? 0 }}</span>
                  </div>
                  <div class="segment-text">{{ segment.content }}</div>
                </div>
              </div>
            </div>
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
import { normalizeRetrievalSettings } from '@/utils/knowledgeSettings'

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
  retrieval_method: 'hybrid',
  top_k: 5,
  score_threshold: 0,
  vector_top_k: 40,
  keyword_top_k: 40,
  fusion_algorithm: 'rrf',
  rrf_k: 60,
  vector_weight: 0.65,
  keyword_weight: 0.35,
  max_candidates: 100,
  enable_rerank: false,
  rerank_model_id: '',
  query_rewrite: true
})
const testQuery = ref('')
const testTopK = ref(null)
const testScoreThreshold = ref(null)
const testing = ref(false)
const testError = ref('')
const testMeta = ref(null)
const testResults = ref([])

const rerankModels = computed(() => modelsStore.enabledRerankModels)
const modelsLoading = computed(() => modelsStore.loading)

const loadSettings = async () => {
  loading.value = true
  error.value = ''
  try {
    form.value = normalizeRetrievalSettings(await knowledgeStore.fetchRetrievalSettings(knowledgeBaseId))
  } catch (err) {
    error.value = err.response?.data?.detail || '加载检索设置失败'
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
      rerank_model_id: form.value.enable_rerank ? (form.value.rerank_model_id || null) : null
    }
    await knowledgeStore.updateRetrievalSettings(knowledgeBaseId, payload)
    success.value = '检索设置已保存'
  } catch (err) {
    error.value = err.response?.data?.detail || '保存检索设置失败'
  } finally {
    saving.value = false
  }
}

const runRetrievalTest = async () => {
  if (!testQuery.value.trim()) return

  testing.value = true
  testError.value = ''
  testMeta.value = null
  testResults.value = []

  try {
    const topK = Number.isFinite(testTopK.value) ? testTopK.value : null
    const scoreThreshold = Number.isFinite(testScoreThreshold.value) ? testScoreThreshold.value : null
    const data = await knowledgeStore.testKnowledgeRetrieval(knowledgeBaseId, {
      query: testQuery.value.trim(),
      top_k: topK,
      score_threshold: scoreThreshold
    })
    testMeta.value = data
    testResults.value = data.results || []
  } catch (err) {
    testError.value = err.response?.data?.detail || '召回测试失败'
  } finally {
    testing.value = false
  }
}

const goBack = () => {
  router.push(`/knowledge/${knowledgeBaseId}`)
}

const goToIndexing = () => {
  router.push(`/knowledge/${knowledgeBaseId}/indexing`)
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

.settings-card + .settings-card {
  margin-top: 16px;
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

.form-row textarea {
  min-height: 90px;
  resize: vertical;
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
}

.form-row textarea:focus {
  border-color: #93a4b8;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.toggle-row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
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

.test-card .btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.test-error {
  margin-top: 14px;
  margin-bottom: 0;
}

.test-meta {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: #64748b;
}

.test-results {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.test-result-item {
  border: 1px solid #d6deea;
  border-radius: 10px;
  background: #f8fafc;
  padding: 12px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
  color: #0f172a;
  font-size: 13px;
}

.result-source {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
}

.result-segments {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.segment-item {
  border: 1px solid #d6deea;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px;
}

.segment-head {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}

.segment-text {
  font-size: 12px;
  color: #334155;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
