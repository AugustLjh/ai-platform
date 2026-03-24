<template>
  <div class="workspace-page">
    <section class="workspace-hero">
      <div>
        <div class="hero-kicker">Agent Workspace</div>
        <h1>{{ agent?.name || '智能体工作区' }}</h1>
        <p>{{ agent?.description || '在这里维护 agent definition，并发起新的 run。' }}</p>
      </div>
      <div class="hero-actions">
        <router-link to="/agents" class="btn btn-secondary">返回列表</router-link>
        <button type="button" class="btn btn-primary" @click="saveAgent" :disabled="saving">
          {{ saving ? '保存中...' : '保存定义' }}
        </button>
      </div>
    </section>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="workspace-grid">
      <div class="workspace-main">
        <div class="panel card">
          <div class="panel-head">
            <div>
              <h2>智能体定义</h2>
              <p>调整模型、描述和 system prompt，保存后用于后续 run。</p>
            </div>
          </div>

          <div v-if="!agent" class="panel-empty">
            正在加载智能体定义...
          </div>

          <form v-else class="agent-form" @submit.prevent="saveAgent">
            <label class="field">
              <span>名称</span>
              <input v-model="editForm.name" class="input" />
            </label>

            <label class="field">
              <span>描述</span>
              <textarea v-model="editForm.description" class="input textarea" rows="3"></textarea>
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

            <label class="field">
              <span>System Prompt</span>
              <textarea v-model="editForm.systemPrompt" class="input textarea prompt-textarea" rows="10"></textarea>
            </label>
          </form>
        </div>

        <div class="panel card">
          <div class="panel-head">
            <div>
              <h2>启动新 Run</h2>
              <p>当前 planner v1 适合先验证 direct answer、calculator、get_current_time 和 echo_json。</p>
            </div>
          </div>

          <form class="run-form" @submit.prevent="startRun">
            <label class="field">
              <span>任务输入</span>
              <textarea
                v-model="runMessage"
                class="input textarea run-textarea"
                rows="5"
                placeholder="例如：现在几点 / 42 * (13 + 2) / echo_json {&quot;ok&quot;: true}"
              ></textarea>
            </label>

            <label class="field">
              <span>关联会话 ID（可选）</span>
              <input v-model="sessionId" class="input" placeholder="留空即可" />
            </label>

            <div class="quick-prompts">
              <button
                v-for="prompt in quickPrompts"
                :key="prompt"
                type="button"
                class="prompt-chip"
                @click="runMessage = prompt"
              >
                {{ prompt }}
              </button>
            </div>

            <button type="submit" class="btn btn-primary run-submit" :disabled="running">
              {{ running ? '启动中...' : '启动 Run' }}
            </button>
          </form>
        </div>
      </div>

      <aside class="workspace-side">
        <div class="panel card side-panel">
          <div class="panel-head">
            <div>
              <h2>能力目录</h2>
              <p>当前列出平台已经暴露的 skills 与 MCP servers 底座。</p>
            </div>
          </div>

          <div class="catalog-section">
            <div class="catalog-head">
              <strong>Skills</strong>
              <button type="button" class="catalog-action" @click="syncSkills">同步</button>
            </div>
            <div v-if="skills.length === 0" class="mini-empty">当前还没有发现技能包。</div>
            <div v-else class="catalog-list">
              <div v-for="skill in skills.slice(0, 6)" :key="skill.id" class="catalog-item">
                <strong>{{ skill.name }}</strong>
                <span>{{ skill.slug }} · v{{ skill.version }}</span>
              </div>
            </div>
          </div>

          <div class="catalog-section">
            <div class="catalog-head">
              <strong>MCP Servers</strong>
            </div>
            <div v-if="mcpServers.length === 0" class="mini-empty">当前没有配置 MCP server。</div>
            <div v-else class="catalog-list">
              <div v-for="server in mcpServers.slice(0, 6)" :key="server.id" class="catalog-item">
                <strong>{{ server.name }}</strong>
                <span>{{ server.transport }} · {{ server.status }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel card side-panel">
          <div class="panel-head">
            <div>
              <h2>最近运行</h2>
              <p>刷新后仍可回到历史 run 详情页继续查看。</p>
            </div>
          </div>

          <div v-if="agentRuns.length === 0" class="panel-empty compact">
            这个智能体还没有 run。
          </div>

          <div v-else class="run-list">
            <button
              v-for="run in agentRuns.slice(0, 8)"
              :key="run.id"
              type="button"
              class="run-item"
              @click="openRun(run.id)"
            >
              <div class="run-item-top">
                <strong>{{ statusLabel(run.status) }}</strong>
                <span>{{ formatTime(run.updatedAt || run.createdAt) }}</span>
              </div>
              <p>{{ run.input?.message || run.input?.prompt || '无输入摘要' }}</p>
            </button>
          </div>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentsStore } from '@/store/agents'
import { useModelsStore } from '@/store/models'
import { useToastStore } from '@/store/toast'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const modelsStore = useModelsStore()
const toastStore = useToastStore()

const saving = ref(false)
const running = ref(false)
const runMessage = ref('')
const sessionId = ref('')

const quickPrompts = [
  '现在几点',
  '42 * (13 + 2)',
  'echo_json {"ok": true, "source": "agent-workspace"}',
  '请总结这个智能体应该如何工作'
]

const editForm = reactive({
  name: '',
  description: '',
  model: '',
  systemPrompt: ''
})

const agent = computed(() => agentsStore.currentAgent)
const agentRuns = computed(() => agentsStore.currentAgentRuns)
const skills = computed(() => agentsStore.skills)
const mcpServers = computed(() => agentsStore.mcpServers)
const enabledModels = computed(() => modelsStore.enabledModels)
const errorMessage = computed(() => agentsStore.error || modelsStore.error || '')

const syncEditForm = () => {
  editForm.name = agent.value?.name || ''
  editForm.description = agent.value?.description || ''
  editForm.model = agent.value?.model || modelsStore.defaultModel?.id || ''
  editForm.systemPrompt = agent.value?.systemPrompt || ''
}

const loadWorkspace = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) return

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchRuns(),
    agentsStore.fetchSkills().catch(() => []),
    agentsStore.fetchMCPServers().catch(() => []),
    modelsStore.fetchModels()
  ])
  syncEditForm()
}

const saveAgent = async () => {
  if (!agent.value?.id) return
  saving.value = true
  try {
    await agentsStore.updateAgent(agent.value.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim(),
      system_prompt: editForm.systemPrompt,
      model: editForm.model || '',
      config: agent.value.config || {},
      metadata: agent.value.metadata || {}
    })
    toastStore.showToast({ type: 'success', message: '智能体定义已保存' })
  } catch (error) {
    console.error('Failed to update agent:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '保存失败' })
  } finally {
    saving.value = false
  }
}

const startRun = async () => {
  if (!agent.value?.id) return
  if (!runMessage.value.trim()) {
    toastStore.showToast({ type: 'error', message: '请先输入任务内容' })
    return
  }

  running.value = true
  try {
    const run = await agentsStore.createRun(agent.value.id, {
      input: {
        message: runMessage.value.trim()
      },
      session_id: sessionId.value.trim(),
      metadata: {},
      auto_start: true
    })
    toastStore.showToast({ type: 'success', message: 'Run 已启动' })
    router.push(`/agents/runs/${run.id}`)
  } catch (error) {
    console.error('Failed to create run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '启动 run 失败' })
  } finally {
    running.value = false
  }
}

const syncSkills = async () => {
  try {
    await agentsStore.syncSkills()
    toastStore.showToast({ type: 'success', message: 'Skills 已同步' })
  } catch (error) {
    console.error('Failed to sync skills:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '同步 skills 失败' })
  }
}

const openRun = (runId) => {
  router.push(`/agents/runs/${runId}`)
}

const statusLabel = (status) => {
  const mapping = {
    queued: '排队中',
    running: '运行中',
    waiting_user: '等待输入',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return mapping[status] || status || '未知状态'
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

watch(() => route.params.id, async () => {
  try {
    await loadWorkspace()
  } catch (error) {
    console.error('Failed to reload workspace:', error)
  }
})

onMounted(async () => {
  try {
    await loadWorkspace()
  } catch (error) {
    console.error('Failed to load workspace:', error)
  }
})
</script>

<style scoped>
.workspace-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.workspace-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(110, 231, 183, 0.35) 0%, rgba(110, 231, 183, 0) 30%),
    linear-gradient(135deg, #102532 0%, #0e5e58 100%);
  color: white;
}

.hero-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
}

.workspace-hero h1 {
  font-size: 34px;
  margin-top: 10px;
}

.workspace-hero p {
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.8);
  max-width: 760px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-actions .btn-secondary {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.84fr);
  gap: 24px;
}

.workspace-main,
.workspace-side {
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

.panel-head h2 {
  font-size: 22px;
}

.panel-head p {
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
  padding: 28px;
  border-radius: 20px;
  background: var(--gray-50);
  text-align: center;
  color: var(--gray-500);
}

.panel-empty.compact {
  padding: 18px;
}

.agent-form,
.run-form {
  margin-top: 18px;
  display: grid;
  gap: 14px;
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
}

.prompt-textarea {
  min-height: 260px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
}

.run-textarea {
  min-height: 140px;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.prompt-chip {
  border: 1px solid rgba(16, 163, 127, 0.16);
  background: rgba(16, 163, 127, 0.06);
  color: var(--primary-700);
  border-radius: var(--radius-full);
  padding: 8px 14px;
  cursor: pointer;
}

.run-submit {
  width: fit-content;
}

.catalog-section + .catalog-section {
  margin-top: 18px;
}

.catalog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.catalog-action {
  border: none;
  background: transparent;
  color: var(--primary-700);
  font-weight: 700;
  cursor: pointer;
}

.mini-empty {
  padding: 14px;
  border-radius: 16px;
  background: var(--gray-50);
  color: var(--gray-500);
  font-size: 14px;
}

.catalog-list,
.run-list {
  display: grid;
  gap: 12px;
}

.catalog-item,
.run-item {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--gray-200);
  background: linear-gradient(180deg, #ffffff 0%, #fbfdfd 100%);
}

.catalog-item strong,
.run-item strong {
  display: block;
  color: var(--gray-900);
}

.catalog-item span,
.run-item span,
.run-item p {
  color: var(--gray-600);
  font-size: 13px;
}

.catalog-item span {
  margin-top: 4px;
  display: block;
}

.run-item {
  text-align: left;
  cursor: pointer;
}

.run-item-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.run-item p {
  margin-top: 8px;
  line-height: 1.5;
}

@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .workspace-page {
    padding: 18px;
  }

  .workspace-hero,
  .card {
    padding: 20px;
    border-radius: 24px;
  }

  .workspace-hero {
    flex-direction: column;
  }

  .workspace-hero h1 {
    font-size: 28px;
  }

  .run-submit {
    width: 100%;
  }
}
</style>
