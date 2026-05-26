<template>
  <div class="models-container">
    <div class="models-layout">
      <div class="models-header">
        <div class="header-content">
          <h1>🤖 模型管理</h1>
          <p>管理和配置 AI 聊天模型</p>
        </div>
        <button @click="showCreateModal = true" class="btn-create">
          <span class="icon">➕</span>
          <span>添加模型</span>
        </button>
      </div>

      <!-- 加载状态 -->
      <div v-if="modelsStore.loading" class="loading-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="modelsStore.error" class="error-state">
        <span class="error-icon">⚠️</span>
        <p>{{ modelsStore.error }}</p>
        <button @click="loadModels" class="btn-retry">重试</button>
      </div>

      <!-- 模型列表 -->
      <div v-else class="models-grid">
        <div
          v-for="model in modelsStore.models"
          :key="model.id"
          :class="['model-card', { disabled: !model.enabled, default: model.is_default }]"
        >
          <div class="model-header">
            <div class="model-icon">
              <span v-if="model.provider === 'openai'">🟢</span>
              <span v-else-if="model.provider === 'deepseek'">🔵</span>
              <span v-else-if="model.provider === 'local'">💻</span>
              <span v-else-if="model.provider === 'jina'">🟣</span>
              <span v-else-if="model.provider === 'qwen'">🟠</span>
              <span v-else-if="model.provider === 'wenxin'">🔴</span>
              <span v-else-if="model.provider === 'glm'">🟡</span>
              <span v-else-if="model.provider === 'kimi'">⚫</span>
              <span v-else-if="model.provider === 'doubao'">🟤</span>
              <span v-else>🤖</span>
            </div>
            <div class="model-info">
              <h3>{{ model.display_name }}</h3>
              <p class="model-id">{{ model.model_id }}</p>
            </div>
            <div class="model-badges">
              <span v-if="model.is_default" class="badge badge-default">默认</span>
              <span v-if="!model.enabled" class="badge badge-disabled">已禁用</span>
              <span class="badge badge-type">{{ getModelTypeLabel(model.model_type) }}</span>
            </div>
          </div>

          <div class="model-details">
            <div class="detail-item">
              <span class="label">提供商:</span>
              <span class="value">{{ getProviderName(model.provider) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">类型:</span>
              <span class="value">{{ getModelTypeLabel(model.model_type) }}</span>
            </div>
            <div class="detail-item" v-if="model.api_base">
              <span class="label">API Base:</span>
              <span class="value truncate">{{ model.api_base }}</span>
            </div>
            <div class="detail-item">
              <span class="label">API Key:</span>
              <span class="value">{{ model.has_api_key ? '已配置 ✓' : '未配置' }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Endpoint:</span>
              <span class="value truncate">{{ model.config.endpoint_protocol || defaultEndpointProtocol(model.provider) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Temperature:</span>
              <span class="value">{{ model.config.temperature || 0.7 }}</span>
            </div>
            <div class="detail-item">
              <span class="label">Max Tokens:</span>
              <span class="value">{{ model.config.max_tokens || 2000 }}</span>
            </div>
            <div class="detail-item">
              <span class="label">输入模态:</span>
              <span class="value">{{ formatModalities(model.config.input_modalities) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">输出模态:</span>
              <span class="value">{{ formatModalities(model.config.output_modalities) }}</span>
            </div>
            <div class="detail-item">
              <span class="label">能力摘要:</span>
              <span class="value">{{ formatCapabilitySummary(model.config) }}</span>
            </div>
          </div>

          <div class="model-actions">
            <button @click="editModel(model)" class="btn-action btn-edit">
              <span>✏️</span>
              <span>编辑</span>
            </button>
            <button
              @click="toggleModelStatus(model)"
              :class="['btn-action', model.enabled ? 'btn-disable' : 'btn-enable']"
            >
              <span>{{ model.enabled ? '🚫' : '✅' }}</span>
              <span>{{ model.enabled ? '禁用' : '启用' }}</span>
            </button>
            <button
              @click="deleteModel(model)"
              class="btn-action btn-delete"
              :disabled="model.is_default"
            >
              <span>🗑️</span>
              <span>删除</span>
            </button>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="modelsStore.models.length === 0" class="empty-state">
          <div class="empty-icon">📦</div>
          <h3>暂无模型</h3>
          <p>点击右上角"添加模型"按钮创建第一个模型</p>
        </div>
      </div>
    </div>

    <!-- 创建/编辑模型弹窗 -->
    <div v-if="showCreateModal || showEditModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <h2>{{ showEditModal ? '编辑模型' : '添加模型' }}</h2>
          <button @click="closeModal" class="btn-close">×</button>
        </div>

        <form @submit.prevent="handleSubmit" class="modal-form">
          <div class="form-group">
            <label>模型名称 *</label>
            <input
              v-model="formData.name"
              type="text"
              placeholder="例如: gpt-4"
              required
              :disabled="showEditModal"
            />
          </div>

          <div class="form-group">
            <label>显示名称 *</label>
            <input
              v-model="formData.display_name"
              type="text"
              placeholder="例如: GPT-4"
              required
            />
          </div>

          <div class="form-group">
            <label>模型类型 *</label>
            <select v-model="formData.model_type" required>
              <option value="llm">LLM</option>
              <option value="embedding">Embedding</option>
              <option value="rerank">Rerank</option>
            </select>
          </div>

          <div class="form-group">
            <label>提供商 *</label>
            <select v-model="formData.provider" required :disabled="showEditModal">
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="jina">Jina</option>
              <option value="qwen">通义千问</option>
              <option value="wenxin">文心一言</option>
              <option value="glm">智谱 GLM</option>
              <option value="kimi">Kimi</option>
              <option value="doubao">豆包</option>
              <option value="local">本地模型</option>
              <option value="mock">Mock (测试)</option>
            </select>
          </div>

          <div class="form-group">
            <label>模型 ID *</label>
            <input
              v-model="formData.model_id"
              type="text"
              placeholder="例如: gpt-4, deepseek-chat"
              required
              :disabled="showEditModal"
            />
          </div>

          <div class="form-group">
            <label>API Base URL</label>
            <input
              v-model="formData.api_base"
              type="url"
              placeholder="例如: https://api.deepseek.com"
            />
            <small>留空使用默认值</small>
          </div>

          <div class="form-group">
            <label>API Key</label>
            <input
              v-model="formData.api_key"
              type="password"
              placeholder="输入 API Key"
            />
            <small v-if="showEditModal && currentModel?.has_api_key">
              留空保持原有配置
            </small>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Temperature</label>
              <input
                v-model.number="formData.config.temperature"
                type="number"
                step="0.1"
                min="0"
                max="2"
              />
            </div>

            <div class="form-group">
              <label>Max Tokens</label>
              <input
                v-model.number="formData.config.max_tokens"
                type="number"
                min="1"
                max="8000"
              />
            </div>
          </div>

          <div class="form-row" v-if="formData.model_type === 'llm'">
            <div class="form-group">
              <label>Task Type</label>
              <input value="chat.completion" type="text" disabled />
              <small>智能体主链路固定为聊天补全任务。</small>
            </div>
            <div class="form-group">
              <label>Endpoint Protocol</label>
              <select v-model="formData.config.endpoint_protocol">
                <option v-for="option in endpointProtocolOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>输入模态</label>
              <div class="modality-options">
                <label
                  v-for="option in inputModalityOptions"
                  :key="option.value"
                  :class="['modality-option', { disabled: !isInputModalityAllowed(option.value) }]"
                >
                  <input
                    v-model="formData.config.input_modalities"
                    type="checkbox"
                    :value="option.value"
                    :disabled="option.value === 'text' || !isInputModalityAllowed(option.value)"
                  />
                  <span>{{ option.label }}</span>
                </label>
              </div>
              <small>{{ endpointInputHint }}</small>
            </div>
            <div class="form-group">
              <label>输出模态</label>
              <input value="text" type="text" disabled />
              <small>当前阶段智能体聊天输出固定为文本。</small>
            </div>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input v-model="formData.config.supports_tools" type="checkbox" />
              <span>支持工具调用</span>
            </label>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input v-model="formData.enabled" type="checkbox" />
              <span>启用此模型</span>
            </label>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input v-model="formData.is_default" type="checkbox" />
              <span>设为默认模型</span>
            </label>
          </div>

          <div class="modal-actions">
            <button type="button" @click="closeModal" class="btn-cancel">
              取消
            </button>
            <button type="submit" class="btn-submit" :disabled="submitting">
              <span v-if="submitting" class="spinner-small"></span>
              <span v-else>{{ showEditModal ? '保存' : '创建' }}</span>
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click.self="showDeleteModal = false">
      <div class="modal-content modal-small">
        <div class="modal-header">
          <h2>确认删除</h2>
          <button @click="showDeleteModal = false" class="btn-close">×</button>
        </div>

        <div class="modal-body">
          <p>确定要删除模型 <strong>{{ modelToDelete?.display_name }}</strong> 吗？</p>
          <p class="warning-text">此操作无法撤销。</p>
        </div>

        <div class="modal-actions">
          <button @click="showDeleteModal = false" class="btn-cancel">
            取消
          </button>
          <button @click="confirmDelete" class="btn-delete" :disabled="submitting">
            <span v-if="submitting" class="spinner-small"></span>
            <span v-else>删除</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useModelsStore } from '@/store/models'
import {
  ENDPOINT_PROTOCOL_OPTIONS,
  MODEL_INPUT_MODALITY_OPTIONS,
  defaultEndpointProtocolForProvider,
  getEndpointSupportedInputModalities
} from '@/utils/modelCapabilities'

const modelsStore = useModelsStore()

const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const submitting = ref(false)
const currentModel = ref(null)
const modelToDelete = ref(null)

const inputModalityOptions = MODEL_INPUT_MODALITY_OPTIONS
const endpointProtocolOptions = ENDPOINT_PROTOCOL_OPTIONS
const defaultEndpointProtocol = defaultEndpointProtocolForProvider

const currentEndpointProtocol = () => (
  formData.value.config.endpoint_protocol || defaultEndpointProtocol(formData.value.provider)
)

const allowedInputModalities = () => getEndpointSupportedInputModalities(currentEndpointProtocol()) || ['text']

const endpointInputHint = computed(() => `当前协议 adapter 支持输入: ${allowedInputModalities().join(', ')}`)

const isInputModalityAllowed = (modality) => allowedInputModalities().includes(modality)

const normalizeFormInputModalities = () => {
  const allowed = allowedInputModalities()
  const selected = parseModalities(formData.value.config.input_modalities, 'text')
  formData.value.config.input_modalities = selected.filter((item) => allowed.includes(item))
  if (!formData.value.config.input_modalities.includes('text')) {
    formData.value.config.input_modalities.unshift('text')
  }
}

const formData = ref({
  name: '',
  display_name: '',
  model_type: 'llm',
  provider: 'openai',
  model_id: '',
  api_base: '',
  api_key: '',
  config: {
    task_type: 'chat.completion',
    endpoint_protocol: 'openai.chat_completions',
    temperature: 0.7,
    max_tokens: 2000,
    input_modalities: ['text'],
    output_modalities: ['text'],
    supports_tools: false
  },
  enabled: true,
  is_default: false
})

onMounted(async () => {
  await loadModels()
})

const loadModels = async () => {
  try {
    await modelsStore.fetchModels()
  } catch (error) {
    console.error('Failed to load models:', error)
  }
}

const getProviderName = (provider) => {
  const names = {
    openai: 'OpenAI',
    deepseek: 'DeepSeek',
    local: '本地模型',
    jina: 'Jina',
    qwen: '通义千问',
    wenxin: '文心一言',
    glm: '智谱 GLM',
    kimi: 'Kimi',
    doubao: '豆包',
    mock: 'Mock (测试)'
  }
  return names[provider] || provider
}

const getModelTypeLabel = (type) => {
  const label = type || 'llm'
  if (label === 'embedding') return 'Embedding'
  if (label === 'rerank') return 'Rerank'
  return 'LLM'
}

const parseModalities = (value, fallback = 'text') => {
  const items = Array.isArray(value) ? value : String(value || fallback).split(',')
  const normalized = items
    .map((item) => item.trim())
    .filter(Boolean)
  return normalized.includes('text') ? normalized : ['text', ...normalized]
}

watch(
  () => formData.value.config.endpoint_protocol,
  () => {
    normalizeFormInputModalities()
  }
)

watch(
  () => formData.value.provider,
  (provider) => {
    if (!showEditModal.value) {
      formData.value.config.endpoint_protocol = defaultEndpointProtocol(provider)
      normalizeFormInputModalities()
    }
  }
)

const formatModalities = (value) => {
  const list = Array.isArray(value) ? value : parseModalities(value)
  return list.length > 0 ? list.join(', ') : 'text'
}

const formatCapabilitySummary = (config = {}) => {
  const input = formatModalities(config.input_modalities)
  const output = 'text'
  return `输入 ${input} / 输出 ${output}`
}

const editModel = (model) => {
  currentModel.value = model
  formData.value = {
    name: model.name,
    display_name: model.display_name,
    model_type: model.model_type || 'llm',
    provider: model.provider,
    model_id: model.model_id,
    api_base: model.api_base || '',
    api_key: '',
    config: {
      task_type: 'chat.completion',
      endpoint_protocol: model.config.endpoint_protocol || defaultEndpointProtocol(model.provider),
      temperature: model.config.temperature || 0.7,
      max_tokens: model.config.max_tokens || 2000,
      input_modalities: parseModalities(model.config.input_modalities, 'text'),
      output_modalities: ['text'],
      supports_tools: Boolean(model.config.supports_tools)
    },
    enabled: model.enabled,
    is_default: model.is_default
  }
  normalizeFormInputModalities()
  showEditModal.value = true
}

const deleteModel = (model) => {
  if (model.is_default) {
    alert('无法删除默认模型')
    return
  }
  modelToDelete.value = model
  showDeleteModal.value = true
}

const toggleModelStatus = async (model) => {
  try {
    submitting.value = true
    await modelsStore.updateModel(model.id, {
      enabled: !model.enabled
    })
    await loadModels()
  } catch (error) {
    alert(`操作失败: ${error.message}`)
  } finally {
    submitting.value = false
  }
}

const handleSubmit = async () => {
  try {
    submitting.value = true

    normalizeFormInputModalities()
    const inputModalities = parseModalities(formData.value.config.input_modalities, 'text')
    const outputModalities = ['text']
    const data = {
      ...formData.value,
      config: {
        temperature: formData.value.config.temperature,
        max_tokens: formData.value.config.max_tokens,
        task_type: 'chat.completion',
        endpoint_protocol: formData.value.config.endpoint_protocol || defaultEndpointProtocol(formData.value.provider),
        input_modalities: inputModalities,
        output_modalities: outputModalities,
        supports_vision: inputModalities.includes('image'),
        supports_video_input: inputModalities.includes('video'),
        supports_file_input: inputModalities.includes('file'),
        supports_audio_input: inputModalities.includes('audio'),
        supports_audio_output: false,
        supports_tools: Boolean(formData.value.config.supports_tools)
      }
    }

    // 如果编辑模式且没有输入新的 API Key，则不发送
    if (showEditModal.value && !data.api_key) {
      delete data.api_key
    }

    if (showEditModal.value) {
      await modelsStore.updateModel(currentModel.value.id, data)
    } else {
      await modelsStore.createModel(data)
    }

    await loadModels()
    closeModal()
  } catch (error) {
    alert(`操作失败: ${error.message}`)
  } finally {
    submitting.value = false
  }
}

const confirmDelete = async () => {
  try {
    submitting.value = true
    await modelsStore.deleteModel(modelToDelete.value.id)
    await loadModels()
    showDeleteModal.value = false
    modelToDelete.value = null
  } catch (error) {
    alert(`删除失败: ${error.message}`)
  } finally {
    submitting.value = false
  }
}

const closeModal = () => {
  showCreateModal.value = false
  showEditModal.value = false
  currentModel.value = null
  formData.value = {
    name: '',
    display_name: '',
    model_type: 'llm',
    provider: 'openai',
    model_id: '',
    api_base: '',
    api_key: '',
    config: {
      task_type: 'chat.completion',
      endpoint_protocol: defaultEndpointProtocol('openai'),
      temperature: 0.7,
      max_tokens: 2000,
      input_modalities: ['text'],
      output_modalities: ['text'],
      supports_tools: false
    },
    enabled: true,
    is_default: false
  }
  normalizeFormInputModalities()
}
</script>

<style scoped>
.models-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gray-50);
  overflow: auto;
}

.models-layout {
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  padding: 32px 24px;
}

/* Header */
.models-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 2px solid var(--gray-200);
}

.header-content h1 {
  font-size: 32px;
  font-weight: 700;
  color: var(--gray-900);
  margin: 0 0 8px 0;
}

.header-content p {
  font-size: 16px;
  color: var(--gray-600);
  margin: 0;
}

.btn-create {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
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

/* Loading & Error States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--gray-200);
  border-top-color: var(--primary-500);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state .error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.error-state p {
  color: var(--gray-700);
  margin-bottom: 16px;
}

.btn-retry {
  padding: 10px 20px;
  background: var(--primary-500);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 600;
}

/* Models Grid */
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 24px;
}

.model-card {
  background: white;
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-xl);
  padding: 24px;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-sm);
}

.model-card:hover {
  border-color: var(--primary-300);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.model-card.disabled {
  opacity: 0.6;
  background: var(--gray-50);
}

.model-card.default {
  border-color: var(--primary-500);
  background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
}

.model-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-200);
}

.model-icon {
  font-size: 32px;
  flex-shrink: 0;
}

.model-info {
  flex: 1;
  min-width: 0;
}

.model-info h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--gray-900);
  margin: 0 0 4px 0;
}

.model-id {
  font-size: 13px;
  color: var(--gray-500);
  font-family: 'Courier New', monospace;
  margin: 0;
}

.model-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.badge {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.badge-default {
  background: var(--primary-100);
  color: var(--primary-700);
}

.badge-disabled {
  background: var(--gray-200);
  color: var(--gray-600);
}

.badge-type {
  background: rgba(59, 130, 246, 0.15);
  color: #2563eb;
}

/* Model Details */
.model-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.detail-item .label {
  font-size: 13px;
  color: var(--gray-600);
  font-weight: 500;
}

.detail-item .value {
  font-size: 14px;
  color: var(--gray-900);
  font-weight: 600;
}

.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

/* Model Actions */
.model-actions {
  display: flex;
  gap: 8px;
}

.btn-action {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  border: 2px solid var(--gray-300);
  border-radius: var(--radius-md);
  background: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
}

.btn-action:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-edit {
  border-color: var(--primary-300);
  color: var(--primary-700);
}

.btn-edit:hover:not(:disabled) {
  background: var(--primary-50);
  border-color: var(--primary-500);
}

.btn-enable {
  border-color: var(--green-300);
  color: var(--green-700);
}

.btn-enable:hover:not(:disabled) {
  background: var(--green-50);
  border-color: var(--green-500);
}

.btn-disable {
  border-color: var(--orange-300);
  color: var(--orange-700);
}

.btn-disable:hover:not(:disabled) {
  background: var(--orange-50);
  border-color: var(--orange-500);
}

.btn-delete {
  border-color: var(--red-300);
  color: var(--red-700);
}

.btn-delete:hover:not(:disabled) {
  background: var(--red-50);
  border-color: var(--red-500);
}

/* Empty State */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  font-size: 20px;
  color: var(--gray-700);
  margin: 0 0 8px 0;
}

.empty-state p {
  font-size: 14px;
  color: var(--gray-500);
  margin: 0;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: white;
  border-radius: var(--radius-xl);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: var(--shadow-xl);
}

.modal-small {
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--gray-200);
}

.modal-header h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--gray-900);
  margin: 0;
}

.btn-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-100);
  border: none;
  border-radius: var(--radius-md);
  font-size: 24px;
  color: var(--gray-600);
  cursor: pointer;
  transition: all var(--transition-base);
}

.btn-close:hover {
  background: var(--gray-200);
  color: var(--gray-900);
}

.modal-body {
  padding: 24px;
}

.warning-text {
  color: var(--red-600);
  font-weight: 600;
  margin-top: 8px;
}

.modal-form {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-700);
  margin-bottom: 8px;
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  transition: all var(--transition-base);
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.form-group input:disabled,
.form-group select:disabled {
  background: var(--gray-100);
  cursor: not-allowed;
}

.form-group small {
  display: block;
  font-size: 12px;
  color: var(--gray-500);
  margin-top: 4px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-group input[type="checkbox"] {
  width: auto;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  gap: 12px;
  padding: 24px;
  border-top: 1px solid var(--gray-200);
}

.btn-cancel,
.btn-submit {
  flex: 1;
  padding: 12px 24px;
  border: none;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
}

.btn-cancel {
  background: var(--gray-100);
  color: var(--gray-700);
}

.btn-cancel:hover {
  background: var(--gray-200);
}

.btn-submit {
  background: var(--gradient-primary);
  color: white;
  box-shadow: var(--shadow-sm);
}

.btn-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner-small {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* Responsive */
@media (max-width: 768px) {
  .models-grid {
    grid-template-columns: 1fr;
  }

  .models-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .btn-create {
    width: 100%;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
