<template>
  <div class="agents-page">
    <section class="agents-hero">
      <div class="hero-copy">
        <div class="hero-kicker">Agent Chat</div>
        <h1>每个智能体都应该先进入聊天，再按需配置</h1>
        <p>
          在这里创建智能体、进入专属聊天页发起运行，配置和删除操作收纳为次级入口，避免主路径过重。
        </p>

        <div class="hero-actions">
          <button type="button" class="btn btn-primary" @click="openCreatePanel()">
            新建智能体
          </button>
          <button type="button" class="btn btn-secondary" @click="loadData">
            刷新列表
          </button>
        </div>

        <div class="preset-list">
          <button
            v-for="preset in presets"
            :key="preset.id"
            type="button"
            class="preset-chip"
            @click="openCreatePanel(preset.id)"
          >
            {{ preset.label }}
          </button>
        </div>
      </div>

      <div class="hero-stats">
        <article class="stat-card">
          <div class="stat-label">Agents</div>
          <div class="stat-value">{{ agents.length }}</div>
        </article>
        <article class="stat-card">
          <div class="stat-label">Recent Runs</div>
          <div class="stat-value">{{ runs.length }}</div>
        </article>
        <article class="stat-card">
          <div class="stat-label">LLM Models</div>
          <div class="stat-value">{{ enabledModels.length }}</div>
        </article>
      </div>
    </section>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="agents-grid">
      <div class="agents-list card">
        <div class="section-head">
          <div>
            <h2>智能体列表</h2>
            <p>点击任意卡片直接进入聊天页，编辑和删除收纳到卡片右上角菜单。</p>
          </div>
        </div>

        <div v-if="loading && agents.length === 0" class="panel-empty">
          正在加载智能体列表...
        </div>

        <div v-else-if="agents.length === 0" class="panel-empty">
          还没有任何智能体。先创建一个，然后直接进入它的聊天页。
        </div>

        <div v-else class="agent-cards">
          <article
            v-for="agent in agents"
            :key="agent.id"
            class="agent-card"
            @click="openAgent(agent.id)"
          >
            <div class="agent-card-top">
              <div>
                <div class="agent-status">{{ statusLabel(agent.status) }}</div>
                <h3>{{ agent.name }}</h3>
              </div>
              <div class="agent-card-actions">
                <span class="agent-model">{{ resolveModelName(agent.model) }}</span>
                <div class="agent-menu-wrap">
                  <button
                    type="button"
                    class="agent-menu-trigger"
                    :aria-expanded="openMenuAgentId === agent.id ? 'true' : 'false'"
                    @click.stop="toggleAgentMenu(agent.id)"
                  >
                    ⋯
                  </button>
                  <div v-if="openMenuAgentId === agent.id" class="agent-menu">
                    <button type="button" class="agent-menu-item" @click.stop="editAgent(agent.id)">
                      编辑智能体
                    </button>
                    <button type="button" class="agent-menu-item danger" @click.stop="deleteAgent(agent)">
                      删除智能体
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <p class="agent-desc">{{ agent.description || '还没有描述。建议补充任务边界与约束。' }}</p>

            <div class="agent-card-meta">
              <span>更新于 {{ formatTime(agent.updatedAt || agent.createdAt) }}</span>
              <span>{{ runCountByAgent(agent.id) }} 次运行</span>
            </div>

            <div v-if="latestRunByAgent(agent.id)" class="agent-run-preview">
              最近一次运行：{{ statusLabel(latestRunByAgent(agent.id).status) }}
              <span>{{ formatTime(latestRunByAgent(agent.id).updatedAt || latestRunByAgent(agent.id).createdAt) }}</span>
            </div>
          </article>
        </div>
      </div>

      <aside class="create-panel card">
        <div class="section-head">
          <div>
            <h2>创建智能体</h2>
            <p>先定义一个最小可用智能体，创建后会直接进入它的聊天页。</p>
          </div>
        </div>

        <form class="create-form" @submit.prevent="handleCreateAgent">
          <label class="field">
            <span>名称</span>
            <input v-model="form.name" class="input" maxlength="80" placeholder="例如：代码分析助手" />
          </label>

          <label class="field">
            <span>描述</span>
            <textarea
              v-model="form.description"
              class="input textarea"
              rows="3"
              placeholder="描述该 agent 的主要职责、边界和交付方式。"
            ></textarea>
          </label>

          <label class="field">
            <span>模型</span>
            <select v-model="form.model" class="input">
              <option value="">使用平台默认模型</option>
              <option v-for="model in enabledModels" :key="model.id" :value="model.id">
                {{ model.display_name }} ({{ model.model_id }})
              </option>
            </select>
          </label>

          <label class="field">
            <span>System Prompt</span>
            <textarea
              v-model="form.systemPrompt"
              class="input textarea prompt-textarea"
              rows="10"
              placeholder="定义角色、边界、输出风格与约束。"
            ></textarea>
          </label>

          <div class="preset-grid">
            <button
              v-for="preset in presets"
              :key="preset.id"
              type="button"
              class="preset-card"
              @click="applyPreset(preset.id)"
            >
              <strong>{{ preset.label }}</strong>
              <span>{{ preset.description }}</span>
            </button>
          </div>

          <button type="submit" class="btn btn-primary submit-btn" :disabled="submitting">
            {{ submitting ? '创建中...' : '创建并进入聊天' }}
          </button>
        </form>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentsStore } from '@/store/agents'
import { useModelsStore } from '@/store/models'
import { useToastStore } from '@/store/toast'

const router = useRouter()
const route = useRoute()
const agentsStore = useAgentsStore()
const modelsStore = useModelsStore()
const toastStore = useToastStore()

const submitting = ref(false)
const openMenuAgentId = ref('')

const presets = [
  {
    id: 'writing',
    label: '写作助手',
    name: '写作助手',
    description: '负责生成结构清晰、可落地的文章、方案和说明文。',
    systemPrompt: '你是一个高质量写作助手。先明确目标读者和交付结构，再输出条理清晰、语言克制、可直接使用的内容。'
  },
  {
    id: 'knowledge',
    label: '知识研究',
    name: '知识研究助手',
    description: '聚焦问题拆解、资料梳理和结论提炼。',
    systemPrompt: '你是一个研究型智能体。先拆解问题，再给出结论、依据和待验证点。不要凭空编造事实。'
  },
  {
    id: 'code',
    label: '代码分析',
    name: '代码分析助手',
    description: '适合定位问题、解释实现和给出修复建议。',
    systemPrompt: '你是一个严谨的软件工程智能体。优先识别风险、回归点和缺失测试，再给出明确的修复建议。'
  },
  {
    id: 'creative',
    label: '创意策划',
    name: '创意策划助手',
    description: '用于 brainstorm、概念发散与方向收敛。',
    systemPrompt: '你是一个创意策划智能体。输出要有明显方向感，不要泛泛堆砌想法。先给创意框架，再给具体方案。'
  }
]

const form = reactive({
  name: '',
  description: '',
  model: '',
  systemPrompt: ''
})

const agents = computed(() => agentsStore.sortedAgents)
const runs = computed(() => agentsStore.sortedRuns)
const enabledModels = computed(() => modelsStore.enabledModels)
const loading = computed(() => agentsStore.loading || modelsStore.loading)
const errorMessage = computed(() => agentsStore.error || modelsStore.error || '')

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.model = modelsStore.defaultModel?.id || ''
  form.systemPrompt = ''
}

const applyPreset = (presetId) => {
  const preset = presets.find((item) => item.id === presetId)
  if (!preset) return
  form.name = preset.name
  form.description = preset.description
  form.systemPrompt = preset.systemPrompt
  if (!form.model && modelsStore.defaultModel?.id) {
    form.model = modelsStore.defaultModel.id
  }
}

const openCreatePanel = (presetId = '') => {
  resetForm()
  if (presetId) {
    applyPreset(presetId)
  }
}

const syncPresetFromRoute = () => {
  const starter = String(route.query.starter || '')
  if (!starter) return
  openCreatePanel(starter)
}

const loadData = async () => {
  await Promise.all([
    agentsStore.fetchAgents(),
    agentsStore.fetchRuns(),
    modelsStore.fetchModels()
  ])
}

const openAgent = (agentId) => {
  router.push(`/agents/${agentId}`)
}

const editAgent = (agentId) => {
  openMenuAgentId.value = ''
  router.push(`/agents/${agentId}/settings`)
}

const deleteAgent = async (agent) => {
  openMenuAgentId.value = ''
  const confirmed = window.confirm(`确认删除智能体“${agent.name}”吗？`)
  if (!confirmed) {
    return
  }

  try {
    await agentsStore.archiveAgent(agent.id)
    toastStore.showToast({ type: 'success', message: '智能体已删除' })
  } catch (error) {
    console.error('Failed to archive agent:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '删除智能体失败' })
  }
}

const toggleAgentMenu = (agentId) => {
  openMenuAgentId.value = openMenuAgentId.value === agentId ? '' : agentId
}

const handleCreateAgent = async () => {
  if (!form.name.trim()) {
    toastStore.showToast({ type: 'error', message: '请先填写智能体名称' })
    return
  }

  submitting.value = true
  try {
    const agent = await agentsStore.createAgent({
      name: form.name.trim(),
      description: form.description.trim(),
      system_prompt: form.systemPrompt.trim(),
      model: form.model || '',
      config: {},
      metadata: {}
    })
    toastStore.showToast({ type: 'success', message: '智能体已创建' })
    router.push(`/agents/${agent.id}`)
  } catch (error) {
    console.error('Failed to create agent:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '创建智能体失败' })
  } finally {
    submitting.value = false
  }
}

const runCountByAgent = (agentId) => runs.value.filter((run) => run.agentDefinitionId === agentId).length
const latestRunByAgent = (agentId) => runs.value.find((run) => run.agentDefinitionId === agentId) || null

const resolveModelName = (modelId) => {
  if (!modelId) return '默认模型'
  const model = modelsStore.models.find((item) => item.id === modelId)
  return model?.display_name || model?.model_id || modelId
}

const statusLabel = (status) => {
  const mapping = {
    active: 'ACTIVE',
    archived: 'ARCHIVED',
    completed: '已完成',
    queued: '排队中',
    running: '运行中',
    failed: '失败',
    cancelled: '已取消',
    waiting_user: '等待输入'
  }
  return mapping[status] || status || '未知'
}

const formatTime = (value) => {
  if (!value) return '未知时间'
  return new Date(value).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

watch(() => route.query.starter, syncPresetFromRoute)

const handleDocumentClick = () => {
  openMenuAgentId.value = ''
}

onMounted(async () => {
  resetForm()
  document.addEventListener('click', handleDocumentClick)
  try {
    await loadData()
    syncPresetFromRoute()
  } catch (error) {
    console.error('Failed to load agents page:', error)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<style scoped>
.agents-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.agents-hero {
  display: grid;
  grid-template-columns: 1.4fr 0.9fr;
  gap: 22px;
  padding: 32px;
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.22) 0%, rgba(255, 255, 255, 0) 34%),
    linear-gradient(135deg, #092b36 0%, #0d5c55 52%, #c08457 100%);
  color: white;
  box-shadow: var(--shadow-xl);
}

.hero-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.78);
}

.hero-copy h1 {
  font-size: 38px;
  line-height: 1.05;
  margin-top: 12px;
}

.hero-copy p {
  margin-top: 14px;
  max-width: 720px;
  color: rgba(255, 255, 255, 0.82);
  font-size: 16px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  margin-top: 22px;
}

.hero-actions .btn-secondary {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.preset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.preset-chip {
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.08);
  color: white;
  border-radius: var(--radius-full);
  padding: 8px 14px;
  cursor: pointer;
  transition: transform var(--transition-base), background var(--transition-base);
}

.preset-chip:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.14);
}

.hero-stats {
  display: grid;
  gap: 14px;
}

.stat-card {
  padding: 18px 20px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
}

.stat-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
}

.stat-value {
  margin-top: 8px;
  font-size: 34px;
  font-weight: 700;
}

.error-banner {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.agents-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.85fr);
  gap: 24px;
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

.panel-empty {
  margin-top: 18px;
  padding: 36px;
  border-radius: 20px;
  text-align: center;
  background: var(--gray-50);
  color: var(--gray-500);
}

.agent-cards {
  display: grid;
  gap: 16px;
  margin-top: 18px;
}

.agent-card {
  padding: 20px;
  border-radius: 22px;
  border: 1px solid var(--gray-200);
  background: linear-gradient(180deg, #ffffff 0%, #fbfdfd 100%);
  cursor: pointer;
  transition: transform var(--transition-base), box-shadow var(--transition-base), border-color var(--transition-base);
}

.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: rgba(16, 163, 127, 0.3);
}

.agent-card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.agent-card-actions {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.agent-status {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--primary-700);
}

.agent-card h3 {
  margin-top: 6px;
  font-size: 22px;
}

.agent-model {
  flex-shrink: 0;
  display: inline-flex;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  background: rgba(16, 163, 127, 0.09);
  color: var(--primary-700);
  font-size: 12px;
  font-weight: 700;
}

.agent-menu-wrap {
  position: relative;
}

.agent-menu-trigger {
  width: 34px;
  height: 34px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: white;
  color: var(--gray-700);
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.agent-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 148px;
  padding: 8px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: white;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
  display: grid;
  gap: 4px;
  z-index: 10;
}

.agent-menu-item {
  border: none;
  background: transparent;
  text-align: left;
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--gray-800);
  cursor: pointer;
}

.agent-menu-item:hover {
  background: var(--gray-50);
}

.agent-menu-item.danger {
  color: #b91c1c;
}

.agent-desc {
  margin-top: 14px;
  color: var(--gray-600);
}

.agent-card-meta,
.agent-run-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-top: 14px;
  font-size: 13px;
}

.agent-card-meta {
  color: var(--gray-500);
}

.agent-run-preview {
  color: var(--gray-700);
}

.create-form {
  display: grid;
  gap: 14px;
  margin-top: 18px;
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

.textarea {
  resize: vertical;
  min-height: 96px;
}

.prompt-textarea {
  min-height: 220px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.preset-card {
  padding: 14px;
  border: 1px solid var(--gray-200);
  border-radius: 18px;
  background: var(--gray-50);
  text-align: left;
  cursor: pointer;
}

.preset-card strong {
  display: block;
  color: var(--gray-900);
}

.preset-card span {
  display: block;
  margin-top: 6px;
  color: var(--gray-600);
  font-size: 13px;
  line-height: 1.5;
}

.submit-btn {
  width: 100%;
  margin-top: 6px;
}

@media (max-width: 1180px) {
  .agents-hero,
  .agents-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .agents-page {
    padding: 18px;
  }

  .agents-hero,
  .card {
    padding: 20px;
    border-radius: 24px;
  }

  .hero-copy h1 {
    font-size: 30px;
  }

  .preset-grid {
    grid-template-columns: 1fr;
  }
}
</style>
