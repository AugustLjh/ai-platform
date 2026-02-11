<template>
  <div class="settings-container">
    <div class="settings-content">
      <div class="settings-header">
        <h1>设置</h1>
        <p>配置聊天模型与对话偏好</p>
      </div>

      <div class="settings-grid">
        <div class="settings-card">
          <div class="card-title">聊天模型</div>
          <p class="card-desc">选择当前聊天使用的模型。</p>

          <div v-if="modelsLoading" class="loading">加载模型列表中...</div>
          <div v-else-if="modelsError" class="error">{{ modelsError }}</div>

          <div v-else>
            <select v-model="selectedModelId" :disabled="enabledModels.length === 0">
              <option v-if="enabledModels.length === 0" value="">暂无可用模型</option>
              <option v-for="model in enabledModels" :key="model.id" :value="model.id">
                {{ model.display_name }} ({{ model.model_id }})
              </option>
            </select>

            <div v-if="enabledModels.length === 0" class="tip">
              请先前往模型管理页面添加并启用模型。
            </div>
          </div>

          <router-link to="/models" class="btn-link">前往模型管理</router-link>
        </div>

        <div class="settings-card">
          <div class="card-title">对话参数</div>
          <div class="form-row">
            <label>Temperature</label>
            <input type="number" min="0" max="2" step="0.1" v-model.number="temperature" />
          </div>
          <div class="form-row">
            <label>Max Tokens</label>
            <input type="number" min="1" max="8000" v-model.number="maxTokens" />
          </div>

          <div class="toggle-row">
            <label>
              <input type="checkbox" v-model="useRag" />
              <span>启用知识库检索（RAG）</span>
            </label>
          </div>
          <div class="toggle-row">
            <label>
              <input type="checkbox" v-model="useAgent" />
              <span>启用智能体模式</span>
            </label>
          </div>

          <div class="tip">设置会自动保存到本地浏览器。</div>
        </div>

        <div class="settings-card">
          <div class="card-title">个人偏好</div>
          <p class="card-desc">更多个性化设置即将开放。</p>
          <div class="tip">你可以在个人中心查看账户信息。</div>
          <router-link to="/profile" class="btn-link">前往个人中心</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useChatStore } from '@/store/chat'
import { useModelsStore } from '@/store/models'

const chatStore = useChatStore()
const modelsStore = useModelsStore()

const enabledModels = computed(() => modelsStore.enabledModels)
const selectedModelId = computed({
  get: () => modelsStore.selectedModelId,
  set: (value) => modelsStore.selectModel(value)
})
const modelsLoading = computed(() => modelsStore.loading)
const modelsError = computed(() => modelsStore.error)

const temperature = computed({
  get: () => chatStore.config.temperature,
  set: (value) => chatStore.updateConfig({ temperature: value })
})

const maxTokens = computed({
  get: () => chatStore.config.maxTokens,
  set: (value) => chatStore.updateConfig({ maxTokens: value })
})

const useRag = computed({
  get: () => chatStore.config.useRAG,
  set: (value) => chatStore.updateConfig({ useRAG: value })
})

const useAgent = computed({
  get: () => chatStore.config.useAgent,
  set: (value) => chatStore.updateConfig({ useAgent: value })
})

onMounted(async () => {
  try {
    await modelsStore.fetchModels()
  } catch (error) {
    console.error('Failed to load models:', error)
  }
})
</script>

<style scoped>
.settings-container {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gray-50);
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.settings-content {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px;
  width: 100%;
}

.settings-header {
  margin-bottom: 24px;
}

.settings-header h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
}

.settings-header p {
  margin: 0;
  color: var(--gray-600);
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.settings-card {
  background: white;
  padding: 24px;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--gray-800);
}

.card-desc {
  margin: 0;
  color: var(--gray-600);
  font-size: 14px;
}

select,
input[type="number"] {
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--gray-300);
  font-size: 14px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-row label {
  font-size: 12px;
  color: var(--gray-500);
}

.toggle-row {
  font-size: 14px;
  color: var(--gray-700);
}

.toggle-row input {
  margin-right: 8px;
}

.tip {
  font-size: 12px;
  color: var(--gray-500);
}

.loading {
  font-size: 14px;
  color: var(--gray-500);
}

.error {
  color: var(--error);
  font-size: 13px;
}

.btn-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 14px;
  border-radius: var(--radius-md);
  background: var(--gray-100);
  color: var(--gray-700);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  align-self: flex-start;
}

.btn-link:hover {
  background: var(--gray-200);
}
</style>
