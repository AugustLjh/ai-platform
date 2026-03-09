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
              <h1>知识库设置</h1>
            </div>
            <p class="subtitle">
              统一管理索引与检索配置。索引方式在创建时确定，后续不可修改。
            </p>
          </div>
          <div class="header-actions">
            <button class="btn-secondary" @click="goToRetrievalTest">召回测试</button>
            <button class="btn-primary" :disabled="saving" @click="handleSave">
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <div class="section-title">索引设置</div>

          <div class="form-row">
            <label>索引方式（已锁定）</label>
            <select :value="lockedIndexingMethod" disabled>
              <option value="chunk">分块索引</option>
              <option value="full">整篇索引</option>
            </select>
            <div class="hint">
              索引方式在创建知识库时选择，创建后不可更换。
            </div>
          </div>

          <div class="form-grid" v-if="lockedIndexingMethod === 'chunk'">
            <div class="form-row">
              <label>分块长度</label>
              <input type="number" min="50" max="2000" step="50" v-model.number="form.chunk_size" />
            </div>
            <div class="form-row">
              <label>重叠长度</label>
              <input type="number" min="0" max="500" step="10" v-model.number="form.chunk_overlap" />
            </div>
          </div>

          <div class="form-row">
            <label>Embedding 模型</label>
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

        <div class="settings-card">
          <div class="section-header">
            <div class="section-title">AI 治理设置</div>
            <div class="section-badge">配置版本 v{{ form.governance_config_version }}</div>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>低质量阈值</label>
              <input type="number" min="0" max="5" step="0.5" v-model.number="form.low_quality_threshold" />
              <div class="hint">评分小于等于该阈值的回答会沉淀为低质量样本。</div>
            </div>
            <div class="form-row">
              <label>预算提醒（USD）</label>
              <input type="number" min="0" step="0.1" v-model.number="form.budget_alert_usd" placeholder="留空表示不提醒" />
            </div>
          </div>

          <div v-for="scene in governanceScenes" :key="scene.key" class="governance-route-card">
            <div class="route-header">
              <div>
                <div class="route-title">{{ scene.label }}</div>
                <div class="route-desc">{{ scene.description }}</div>
              </div>
              <label class="toggle-inline">
                <input type="checkbox" v-model="form.routes[scene.key].enabled" />
                <span>启用路由</span>
              </label>
            </div>

            <div class="form-grid">
              <div class="form-row">
                <label>主模型</label>
                <select v-model="form.routes[scene.key].primary_model_id" :disabled="modelsLoading || !form.routes[scene.key].enabled">
                  <option value="">默认模型</option>
                  <option v-for="model in llmModels" :key="model.id" :value="model.id">
                    {{ model.display_name }} ({{ model.model_id }})
                  </option>
                </select>
              </div>
              <div class="form-row">
                <label>备模型</label>
                <select v-model="form.routes[scene.key].fallback_model_id" :disabled="modelsLoading || !form.routes[scene.key].enabled">
                  <option value="">不配置</option>
                  <option v-for="model in llmModels" :key="`${scene.key}-${model.id}`" :value="model.id">
                    {{ model.display_name }} ({{ model.model_id }})
                  </option>
                </select>
              </div>
            </div>
          </div>

          <div v-if="llmModels.length === 0" class="hint">
            暂无可用聊天模型，请先在“模型管理”中添加或启用。
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
const lockedIndexingMethod = ref('chunk')

const form = ref({
  chunk_size: 500,
  chunk_overlap: 50,
  embedding_model_id: '',
  retrieval_method: 'vector',
  top_k: 5,
  score_threshold: 0,
  enable_rerank: false,
  rerank_model_id: '',
  governance_config_version: 1,
  budget_alert_usd: null,
  low_quality_threshold: 2,
  routes: {
    chat: { enabled: true, primary_model_id: '', fallback_model_id: '' },
    rag_chat: { enabled: true, primary_model_id: '', fallback_model_id: '' },
    agent_chat: { enabled: true, primary_model_id: '', fallback_model_id: '' }
  }
})

const embeddingModels = computed(() => modelsStore.enabledEmbeddingModels)
const rerankModels = computed(() => modelsStore.enabledRerankModels)
const llmModels = computed(() => modelsStore.enabledModels)
const modelsLoading = computed(() => modelsStore.loading)
const governanceScenes = [
  { key: 'chat', label: '普通对话', description: '未启用知识库和 Agent 时使用。' },
  { key: 'rag_chat', label: '知识库问答', description: '知识库检索问答场景的主备模型。' },
  { key: 'agent_chat', label: 'Agent/工具调用', description: '启用 Agent 或工具调用时使用。' }
]

const loadSettings = async () => {
  loading.value = true
  error.value = ''
  try {
    const [indexingSettings, retrievalSettings, governanceSettings] = await Promise.all([
      knowledgeStore.fetchIndexingSettings(knowledgeBaseId),
      knowledgeStore.fetchRetrievalSettings(knowledgeBaseId),
      knowledgeStore.fetchGovernanceSettings(knowledgeBaseId)
    ])

    lockedIndexingMethod.value = indexingSettings.indexing_method || 'chunk'

    form.value = {
      chunk_size: indexingSettings.chunk_size ?? 500,
      chunk_overlap: indexingSettings.chunk_overlap ?? 50,
      embedding_model_id: indexingSettings.embedding_model_id || '',
      retrieval_method: retrievalSettings.retrieval_method || 'vector',
      top_k: retrievalSettings.top_k ?? 5,
      score_threshold: retrievalSettings.score_threshold ?? 0,
      enable_rerank: retrievalSettings.enable_rerank ?? false,
      rerank_model_id: retrievalSettings.rerank_model_id || '',
      governance_config_version: governanceSettings.config_version || 1,
      budget_alert_usd: governanceSettings.budget_alert_usd ?? null,
      low_quality_threshold: governanceSettings.low_quality_threshold ?? 2,
      routes: {
        chat: {
          enabled: governanceSettings.routes?.chat?.enabled ?? true,
          primary_model_id: governanceSettings.routes?.chat?.primary_model_id || '',
          fallback_model_id: governanceSettings.routes?.chat?.fallback_model_id || ''
        },
        rag_chat: {
          enabled: governanceSettings.routes?.rag_chat?.enabled ?? true,
          primary_model_id: governanceSettings.routes?.rag_chat?.primary_model_id || '',
          fallback_model_id: governanceSettings.routes?.rag_chat?.fallback_model_id || ''
        },
        agent_chat: {
          enabled: governanceSettings.routes?.agent_chat?.enabled ?? true,
          primary_model_id: governanceSettings.routes?.agent_chat?.primary_model_id || '',
          fallback_model_id: governanceSettings.routes?.agent_chat?.fallback_model_id || ''
        }
      }
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '加载设置失败'
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  error.value = ''
  success.value = ''

  try {
    await knowledgeStore.updateIndexingSettings(knowledgeBaseId, {
      indexing_method: lockedIndexingMethod.value,
      chunk_size: form.value.chunk_size,
      chunk_overlap: form.value.chunk_overlap,
      embedding_model_id: form.value.embedding_model_id || null
    })

    await knowledgeStore.updateRetrievalSettings(knowledgeBaseId, {
      retrieval_method: form.value.retrieval_method,
      top_k: form.value.top_k,
      score_threshold: form.value.score_threshold,
      enable_rerank: form.value.enable_rerank,
      rerank_model_id: form.value.enable_rerank ? (form.value.rerank_model_id || null) : null
    })

    const governanceRoutes = {}
    for (const scene of governanceScenes) {
      governanceRoutes[scene.key] = {
        enabled: form.value.routes[scene.key].enabled,
        primary_model_id: form.value.routes[scene.key].primary_model_id || null,
        fallback_model_id: form.value.routes[scene.key].fallback_model_id || null
      }
    }

    const governanceData = await knowledgeStore.updateGovernanceSettings(knowledgeBaseId, {
      budget_alert_usd: form.value.budget_alert_usd === '' || form.value.budget_alert_usd === null ? null : Number(form.value.budget_alert_usd),
      low_quality_threshold: Number(form.value.low_quality_threshold ?? 2),
      routes: governanceRoutes
    })
    form.value.governance_config_version = governanceData.config_version || form.value.governance_config_version

    success.value = '知识库设置已保存'
  } catch (err) {
    error.value = err.response?.data?.detail || '保存设置失败'
  } finally {
    saving.value = false
  }
}

const goBack = () => {
  router.push(`/knowledge/${knowledgeBaseId}`)
}

const goToRetrievalTest = () => {
  router.push(`/knowledge/${knowledgeBaseId}/retrieval-test`)
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

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-badge {
  padding: 6px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
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

.form-row select:disabled {
  background: #f8fafc;
  color: #64748b;
  cursor: not-allowed;
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

.toggle-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #334155;
  font-size: 13px;
}

.governance-route-card {
  margin-top: 16px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #dbe4ee;
  background: #f8fafc;
}

.route-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.route-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.route-desc {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
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
