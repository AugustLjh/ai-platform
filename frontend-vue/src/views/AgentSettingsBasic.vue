<template>
  <div class="agent-page">
    <AgentPageHeader
      :agent-id="agent?.id || ''"
      kicker="Agent Settings"
      :title="agent?.name || '智能体基础设置'"
      :description="agent?.description || '管理名称、模型和基础 system prompt。扩展来源与运行历史已拆分到独立页面。'"
    >
      <template #actions>
        <button type="button" class="btn btn-secondary" @click="reloadPage">刷新</button>
        <button type="button" class="btn btn-primary" :disabled="saving || !agent" @click="saveAgent">
          {{ saving ? '保存中...' : '保存基础设置' }}
        </button>
      </template>
    </AgentPageHeader>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="page-grid">
      <div class="card">
        <div class="section-head">
          <div>
            <h2>基础定义</h2>
            <p>这些字段定义这个智能体的默认角色、输出方式和模型选择。</p>
          </div>
        </div>

        <div v-if="!agent" class="panel-empty">正在加载智能体定义...</div>

        <form v-else class="agent-form" @submit.prevent="saveAgent">
          <label class="field">
            <span>名称</span>
            <input v-model="editForm.name" class="input" maxlength="80" />
          </label>

          <label class="field">
            <span>描述</span>
            <textarea v-model="editForm.description" class="input textarea" rows="4"></textarea>
          </label>

          <label class="field">
            <span>模型</span>
            <select v-model="editForm.model" class="input">
              <option value="">使用平台默认模型</option>
              <option v-for="model in enabledModels" :key="model.id" :value="model.id">
                {{ model.display_name }} ({{ model.model_id }})
              </option>
            </select>
          </label>

          <div class="field">
            <span>默认 Workspace 绑定</span>
            <div class="workspace-policy-grid">
              <select v-model="editForm.workspaceMode" class="input">
                <option value="none">每次会话手动选择</option>
                <option value="existing">默认复制允许目录</option>
              </select>
              <select
                v-if="editForm.workspaceMode === 'existing'"
                v-model="editForm.workspacePath"
                class="input"
              >
                <option value="">请选择允许目录</option>
                <option
                  v-for="source in workspaceSources"
                  :key="source.path"
                  :value="source.path"
                >
                  {{ formatWorkspaceSource(source) }}
                </option>
              </select>
            </div>
            <p class="field-help">
              默认绑定只会复制到 run 级隔离 workspace，运行中的写入不会直接落到原项目目录。
            </p>
            <p v-if="workspaceError" class="field-error">{{ workspaceError }}</p>
          </div>

          <label class="field">
            <span>System Prompt</span>
            <textarea v-model="editForm.systemPrompt" class="input textarea prompt-textarea" rows="14"></textarea>
          </label>
        </form>
      </div>

      <aside class="page-side">
        <div class="card side-card">
          <div class="section-head">
            <div>
              <h2>使用建议</h2>
              <p>基础设置只定义身份和边界，不要把工具接入、知识来源和运行策略都堆进 system prompt。</p>
            </div>
          </div>

          <ul class="tips-list">
            <li>角色描述聚焦职责、边界和交付风格，不要重复扩展来源里的内容。</li>
            <li>模型选择只处理通用能力差异，领域能力优先放到扩展绑定页的 skill 组合。</li>
            <li>如果 prompt 很长且在描述工具使用方式，通常意味着应该拆成 skill，而不是继续堆在这里。</li>
          </ul>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AgentPageHeader from '@/components/agent/AgentPageHeader.vue'
import { useAgentsStore } from '@/store/agents'
import { useModelsStore } from '@/store/models'
import { useToastStore } from '@/store/toast'
import { agentsAPI } from '@/api'
import { formatWorkspaceSource, getAgentWorkspaceBindingPolicy } from '@/utils/workspaceBindings'

const route = useRoute()
const agentsStore = useAgentsStore()
const modelsStore = useModelsStore()
const toastStore = useToastStore()

const saving = ref(false)
const workspaceSources = ref([])
const workspaceError = ref('')

const editForm = reactive({
  name: '',
  description: '',
  model: '',
  systemPrompt: '',
  workspaceMode: 'none',
  workspacePath: ''
})

const agent = computed(() => agentsStore.currentAgent)
const enabledModels = computed(() => modelsStore.enabledModels)
const errorMessage = computed(() => agentsStore.error || modelsStore.error || '')

const syncEditForm = () => {
  editForm.name = agent.value?.name || ''
  editForm.description = agent.value?.description || ''
  editForm.model = agent.value?.model || modelsStore.defaultModel?.id || ''
  editForm.systemPrompt = agent.value?.systemPrompt || ''
  const workspacePolicy = getAgentWorkspaceBindingPolicy(agent.value || {})
  editForm.workspaceMode = workspacePolicy.enabled ? workspacePolicy.mode : 'none'
  editForm.workspacePath = workspacePolicy.path || ''
}

const loadWorkspaceSources = async () => {
  workspaceError.value = ''
  try {
    const { data } = await agentsAPI.listWorkspaceSources()
    workspaceSources.value = Array.isArray(data?.sources) ? data.sources : []
  } catch (error) {
    console.error('Failed to load workspace sources:', error)
    workspaceError.value = error?.response?.data?.detail || error?.message || '加载 workspace 目录失败'
  }
}

const loadPage = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) return

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    modelsStore.fetchModels(),
    loadWorkspaceSources()
  ])
  syncEditForm()
}

const buildAgentConfig = () => {
  const currentConfig = agent.value?.config && typeof agent.value.config === 'object' ? agent.value.config : {}
  const workspaceConfig = currentConfig.workspace && typeof currentConfig.workspace === 'object' ? currentConfig.workspace : {}
  const defaultSource = editForm.workspaceMode === 'existing'
    ? {
        enabled: true,
        type: 'existing',
        path: editForm.workspacePath.trim()
      }
    : {
        enabled: false,
        type: 'none',
        path: ''
      }
  return {
    ...currentConfig,
    workspace: {
      ...workspaceConfig,
      default_source: defaultSource
    }
  }
}

const reloadPage = async () => {
  try {
    await loadPage()
    toastStore.showToast({ type: 'success', message: '已刷新基础设置' })
  } catch (error) {
    console.error('Failed to reload basic settings:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || modelsStore.error || '刷新失败' })
  }
}

const saveAgent = async () => {
  if (!agent.value?.id) return
  if (editForm.workspaceMode === 'existing' && !editForm.workspacePath.trim()) {
    toastStore.showToast({ type: 'error', message: '请选择默认绑定的允许目录' })
    return
  }
  saving.value = true
  try {
    await agentsStore.updateAgent(agent.value.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim(),
      system_prompt: editForm.systemPrompt,
      model: editForm.model || '',
      config: buildAgentConfig(),
      metadata: agent.value.metadata || {}
    })
    toastStore.showToast({ type: 'success', message: '基础设置已保存' })
  } catch (error) {
    console.error('Failed to save agent basic settings:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '保存失败' })
  } finally {
    saving.value = false
  }
}

watch(() => route.params.id, async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to reload agent basic settings:', error)
  }
})

onMounted(async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to load agent basic settings:', error)
  }
})
</script>

<style scoped>
.agent-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.page-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
  gap: 24px;
}

.page-side {
  display: grid;
  gap: 22px;
}

.card {
  background: white;
  border-radius: 28px;
  padding: 24px;
  border: 1px solid rgba(16, 163, 127, 0.1);
  box-shadow: var(--shadow-sm);
}

.section-head h2 {
  font-size: 22px;
}

.section-head p {
  margin-top: 6px;
  color: var(--gray-600);
}

.error-banner {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.panel-empty {
  margin-top: 18px;
  color: var(--gray-500);
}

.agent-form {
  margin-top: 22px;
  display: grid;
  gap: 18px;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 13px;
  font-weight: 700;
  color: var(--gray-700);
}

.field-help,
.field-error {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}

.field-help {
  color: var(--gray-500);
}

.field-error {
  color: #b91c1c;
}

.workspace-policy-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.45fr) minmax(0, 1fr);
  gap: 12px;
}

.input {
  width: 100%;
  border: 1px solid var(--gray-200);
  border-radius: 16px;
  padding: 13px 14px;
  background: #fff;
}

.textarea {
  resize: vertical;
  min-height: 120px;
}

.prompt-textarea {
  min-height: 280px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  line-height: 1.6;
}

.side-card {
  align-self: start;
}

.tips-list {
  margin-top: 18px;
  padding-left: 18px;
  color: var(--gray-700);
  display: grid;
  gap: 12px;
}

@media (max-width: 980px) {
  .page-grid {
    grid-template-columns: 1fr;
  }

  .workspace-policy-grid {
    grid-template-columns: 1fr;
  }
}
</style>
