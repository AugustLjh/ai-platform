<template>
  <div class="agent-page">
    <AgentPageHeader
      :agent-id="agent?.id || ''"
      kicker="Agent Extensions"
      :title="agent?.name || '扩展绑定'"
      :description="agent?.description || '为当前智能体选择 skill、知识库和 MCP 来源，工具列表只保留为生效结果。'"
    >
      <template #actions>
        <button type="button" class="btn btn-secondary" @click="reloadPage">刷新</button>
        <button type="button" class="btn btn-secondary" @click="syncSkills">同步 Skills</button>
        <button type="button" class="btn btn-primary" :disabled="saving || !agent" @click="saveBindings">
          {{ saving ? '保存中...' : '保存扩展绑定' }}
        </button>
      </template>
    </AgentPageHeader>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">已绑定 Skills</span>
        <strong>{{ selectedSkillIds.length }}</strong>
        <p>包含系统固定 skill</p>
      </article>
      <article class="summary-card">
        <span class="summary-label">挂载知识库</span>
        <strong>{{ selectedKnowledgeBaseIds.length }}</strong>
        <p>当前 agent 可检索的知识来源</p>
      </article>
      <article class="summary-card">
        <span class="summary-label">绑定 MCP</span>
        <strong>{{ selectedMCPServerIds.length }}</strong>
        <p>只统计显式绑定的 server</p>
      </article>
      <article class="summary-card accent">
        <span class="summary-label">生效工具</span>
        <strong>{{ availableTools.length }}</strong>
        <p>基于最近一次保存后的 runtime 能力结果</p>
      </article>
    </section>

    <div v-if="isDirty" class="info-banner">
      当前选择还没有保存，生效能力预览仍然基于最近一次已保存配置。
    </div>

    <section class="extensions-grid">
      <div class="stack">
        <div class="card">
          <div class="section-head">
            <div>
              <h2>Skills</h2>
              <p>Skill 是能力包和行为约束，决定这个智能体该如何完成任务。</p>
            </div>
          </div>

          <div v-if="skills.length === 0" class="panel-empty">当前还没有发现技能包。</div>
          <div v-else class="catalog-list">
            <label v-for="skill in skills" :key="skill.id" :class="['catalog-item', { fixed: isFixedSkill(skill) }]">
              <span class="catalog-main">
                <strong>{{ skill.name }}</strong>
                <span>{{ skill.slug }} · v{{ skill.version }}</span>
                <small v-if="skill.description">{{ skill.description }}</small>
                <div class="skill-meta">
                  <span v-if="skillIntentSummary(skill)" class="meta-tag">{{ skillIntentSummary(skill) }}</span>
                  <span v-if="skillPhaseSummary(skill)" class="meta-tag">{{ skillPhaseSummary(skill) }}</span>
                  <span v-if="skillToolPolicySummary(skill)" class="meta-tag">{{ skillToolPolicySummary(skill) }}</span>
                  <span v-if="skillOutputSummary(skill)" class="meta-tag">{{ skillOutputSummary(skill) }}</span>
                </div>
              </span>
              <span v-if="isFixedSkill(skill)" class="fixed-pill">系统固定</span>
              <input
                v-model="selectedSkillIds"
                type="checkbox"
                class="selector"
                :value="skill.id"
                :disabled="isFixedSkill(skill)"
              />
            </label>
          </div>
        </div>

        <div class="card">
          <div class="section-head">
            <div>
              <h2>知识库</h2>
              <p>挂载后才允许当前 agent 检索这些知识库。</p>
            </div>
          </div>

          <div v-if="knowledgeBases.length === 0" class="panel-empty">当前没有可挂载的知识库。</div>
          <div v-else class="catalog-list">
            <label v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id" class="catalog-item">
              <span class="catalog-main">
                <strong>{{ knowledgeBase.name }}</strong>
                <span>{{ knowledgeAccessLabel(knowledgeBase.access_level) }}</span>
                <small v-if="knowledgeBase.description">{{ knowledgeBase.description }}</small>
              </span>
              <input
                v-model="selectedKnowledgeBaseIds"
                type="checkbox"
                class="selector"
                :value="knowledgeBase.id"
              />
            </label>
          </div>
        </div>

        <div class="card">
          <div class="section-head">
            <div>
              <h2>MCP Servers</h2>
              <p>MCP 是外部执行能力来源，只有绑定后其工具才会进入当前 agent 的 runtime。</p>
            </div>
            <router-link to="/mcp" class="inline-action">管理 MCP</router-link>
          </div>

          <div v-if="mcpServers.length === 0" class="panel-empty">当前没有配置 MCP server。</div>
          <div v-else class="catalog-list">
            <label v-for="server in mcpServers" :key="server.id" class="catalog-item">
              <span class="catalog-main">
                <strong>{{ server.name }}</strong>
                <span>{{ server.transport }} · {{ server.status }}</span>
                <small>{{ server.tools?.length || 0 }} 个 catalog tools</small>
              </span>
              <input
                v-model="selectedMCPServerIds"
                type="checkbox"
                class="selector"
                :value="server.id"
              />
            </label>
          </div>
        </div>
      </div>

      <aside class="stack">
        <div class="card">
          <div class="section-head">
            <div>
              <h2>生效能力</h2>
              <p>这是最近一次已保存配置下，当前 agent 实际可见的 runtime 工具结果。</p>
            </div>
          </div>

          <div class="tool-kind-summary">
            <span>内置 {{ countToolsByKind('builtin') }}</span>
            <span>知识库 {{ countToolsByKind('knowledge') }}</span>
            <span>MCP {{ countToolsByKind('mcp') }}</span>
            <span>项目上下文 {{ countToolsByKind('engineering') }}</span>
          </div>

          <div v-if="availableTools.length === 0" class="panel-empty">当前没有加载到任何工具。</div>
          <div v-else class="tool-list">
            <article v-for="tool in availableTools" :key="tool.name" class="tool-item">
              <div class="tool-head">
                <div>
                  <strong>{{ tool.name }}</strong>
                  <p>{{ tool.description || '暂无描述' }}</p>
                  <p v-if="tool.kind === 'engineering'" class="tool-source">
                    内部项目上下文能力 · 当前仅访问会话历史与已挂载文档
                  </p>
                  <p v-if="tool.kind === 'mcp' && tool.metadata?.server_name" class="tool-source">
                    来源 {{ tool.metadata.server_name }} · {{ tool.metadata.source_tool_name || tool.name }}
                  </p>
                </div>
                <span :class="['tool-kind', `kind-${tool.kind}`]">{{ toolKindLabel(tool.kind) }}</span>
              </div>

              <div class="tool-schema">
                <span class="tool-schema-label">参数字段</span>
                <div v-if="toolSchemaKeys(tool).length === 0" class="tool-schema-empty">无参数</div>
                <div v-else class="tool-schema-tags">
                  <span v-for="key in toolSchemaKeys(tool)" :key="`${tool.name}-${key}`" class="schema-tag">
                    {{ key }}
                  </span>
                </div>
              </div>
            </article>
          </div>
        </div>

        <div class="card">
          <div class="section-head">
            <div>
              <h2>页面说明</h2>
              <p>配置层和结果层已经分开，这里只负责来源绑定与结果预览。</p>
            </div>
          </div>

          <ul class="tips-list">
            <li>Skill 决定行为策略和工作流，不直接等于工具。</li>
            <li>MCP 提供外部执行能力，绑定后才可能进入运行时工具列表。</li>
            <li>工具列表保留为只读结果视图，用于理解和排查当前 agent 的实际能力边界。</li>
          </ul>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AgentPageHeader from '@/components/agent/AgentPageHeader.vue'
import { useAgentsStore } from '@/store/agents'
import { useKnowledgeStore } from '@/store/knowledge'
import { useToastStore } from '@/store/toast'

const route = useRoute()
const agentsStore = useAgentsStore()
const knowledgeStore = useKnowledgeStore()
const toastStore = useToastStore()

const saving = ref(false)
const selectedSkillIds = ref([])
const selectedMCPServerIds = ref([])
const selectedKnowledgeBaseIds = ref([])

const agent = computed(() => agentsStore.currentAgent)
const skills = computed(() => agentsStore.skills)
const availableTools = computed(() => agentsStore.availableTools)
const mcpServers = computed(() => agentsStore.mcpServers)
const knowledgeBases = computed(() => knowledgeStore.knowledgeBases)
const errorMessage = computed(() => agentsStore.error || knowledgeStore.error || '')
const fixedSkillIds = computed(() => skills.value
  .filter((skill) => isFixedSkill(skill))
  .map((skill) => skill.id)
  .filter(Boolean))

const normalizeIds = (value = []) => [...new Set((Array.isArray(value) ? value : []).filter(Boolean))].sort()

const isDirty = computed(() => {
  const skillIds = normalizeIds(selectedSkillIds.value)
  const agentSkillIds = normalizeIds(agent.value?.skillIds)
  const knowledgeIds = normalizeIds(selectedKnowledgeBaseIds.value)
  const agentKnowledgeIds = normalizeIds(agent.value?.knowledgeBaseIds)
  const serverIds = normalizeIds(selectedMCPServerIds.value)
  const agentServerIds = normalizeIds(agent.value?.mcpServerIds)

  return JSON.stringify(skillIds) !== JSON.stringify(agentSkillIds) ||
    JSON.stringify(knowledgeIds) !== JSON.stringify(agentKnowledgeIds) ||
    JSON.stringify(serverIds) !== JSON.stringify(agentServerIds)
})

const isFixedSkill = (skill) => Boolean(skill?.metadata?.fixed_binding) || skill?.slug === 'implementation-planner'

const mergeFixedSkillIds = (skillIds = []) => {
  const merged = new Set(Array.isArray(skillIds) ? skillIds.filter(Boolean) : [])
  fixedSkillIds.value.forEach((skillId) => merged.add(skillId))
  return [...merged]
}

const syncSelections = () => {
  selectedSkillIds.value = mergeFixedSkillIds(agent.value?.skillIds)
  selectedMCPServerIds.value = Array.isArray(agent.value?.mcpServerIds) ? [...agent.value.mcpServerIds] : []
  selectedKnowledgeBaseIds.value = Array.isArray(agent.value?.knowledgeBaseIds) ? [...agent.value.knowledgeBaseIds] : []
}

const loadPage = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) return

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchSkills().catch(() => []),
    agentsStore.fetchMCPServers().catch(() => []),
    knowledgeStore.fetchKnowledgeBases(1, 100).catch(() => []),
    agentsStore.fetchTools(agentId).catch(() => [])
  ])
  syncSelections()
}

const reloadPage = async () => {
  try {
    await loadPage()
    toastStore.showToast({ type: 'success', message: '已刷新扩展绑定页' })
  } catch (error) {
    console.error('Failed to reload extensions page:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || knowledgeStore.error || '刷新失败' })
  }
}

const syncSkills = async () => {
  try {
    await agentsStore.syncSkills()
    selectedSkillIds.value = mergeFixedSkillIds(selectedSkillIds.value)
    toastStore.showToast({ type: 'success', message: 'Skills 已同步' })
  } catch (error) {
    console.error('Failed to sync skills:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '同步 skills 失败' })
  }
}

const saveBindings = async () => {
  if (!agent.value?.id) return
  saving.value = true
  try {
    await agentsStore.updateAgentSkills(agent.value.id, mergeFixedSkillIds(selectedSkillIds.value))
    await agentsStore.updateAgentMCPServers(agent.value.id, selectedMCPServerIds.value)
    await agentsStore.updateAgentKnowledgeBases(agent.value.id, selectedKnowledgeBaseIds.value)
    await agentsStore.fetchTools(agent.value.id)
    toastStore.showToast({ type: 'success', message: '扩展绑定已保存' })
  } catch (error) {
    console.error('Failed to save extensions:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '保存失败' })
  } finally {
    saving.value = false
  }
}

const toolKindLabel = (kind) => {
  const mapping = {
    builtin: '内置',
    knowledge: '知识库',
    mcp: 'MCP',
    engineering: '项目上下文'
  }
  return mapping[kind] || kind || '未知'
}

const skillIntentSummary = (skill) => {
  const intents = Array.isArray(skill?.metadata?.activation_intents) ? skill.metadata.activation_intents.filter(Boolean) : []
  return intents.length > 0 ? `意图: ${intents.join(' / ')}` : ''
}

const skillPhaseSummary = (skill) => {
  const phases = Array.isArray(skill?.metadata?.activation_phases) ? skill.metadata.activation_phases.filter(Boolean) : []
  return phases.length > 0 ? `阶段: ${phases.join(' / ')}` : ''
}

const skillToolPolicySummary = (skill) => {
  if (!Array.isArray(skill?.toolAllowlist) || skill.toolAllowlist.length === 0) {
    return '工具策略: 不限'
  }
  return `工具策略: ${skill.toolAllowlist.length} 项`
}

const skillOutputSummary = (skill) => {
  const keys = Object.keys(skill?.outputSchema?.properties || {})
  return keys.length > 0 ? `输出字段: ${keys.join(', ')}` : ''
}

const knowledgeAccessLabel = (accessLevel) => {
  if (accessLevel === 'user') {
    return '个人知识库'
  }
  return '共享知识库'
}

const toolSchemaKeys = (tool) => Object.keys(tool?.inputSchema?.properties || {})

const countToolsByKind = (kind) => availableTools.value.filter((tool) => tool.kind === kind).length

watch(() => route.params.id, async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to reload extensions page:', error)
  }
})

onMounted(async () => {
  try {
    await loadPage()
  } catch (error) {
    console.error('Failed to load extensions page:', error)
  }
})
</script>

<style scoped>
.agent-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  padding: 20px;
  border-radius: 24px;
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.1);
  box-shadow: var(--shadow-sm);
}

.summary-card.accent {
  background:
    radial-gradient(circle at top right, rgba(20, 184, 166, 0.18) 0%, rgba(20, 184, 166, 0) 34%),
    white;
}

.summary-label {
  display: block;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
}

.summary-card strong {
  display: block;
  margin-top: 12px;
  font-size: 34px;
}

.summary-card p {
  margin-top: 8px;
  color: var(--gray-600);
}

.extensions-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 24px;
}

.stack {
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

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.section-head h2 {
  font-size: 22px;
}

.section-head p {
  margin-top: 6px;
  color: var(--gray-600);
}

.inline-action {
  color: #0f766e;
  font-weight: 600;
}

.error-banner,
.info-banner {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
}

.error-banner {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.info-banner {
  background: rgba(13, 148, 136, 0.08);
  border: 1px solid rgba(13, 148, 136, 0.16);
  color: #115e59;
}

.panel-empty {
  margin-top: 18px;
  color: var(--gray-500);
}

.catalog-list,
.tool-list {
  margin-top: 18px;
  display: grid;
  gap: 12px;
}

.catalog-item,
.tool-item {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.7);
}

.catalog-item.fixed {
  background: rgba(15, 118, 110, 0.08);
  border-color: rgba(13, 148, 136, 0.22);
}

.catalog-main {
  display: grid;
  gap: 4px;
}

.skill-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.catalog-main strong {
  color: var(--gray-900);
}

.catalog-main span,
.catalog-main small {
  color: var(--gray-600);
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: var(--gray-700);
  font-size: 12px;
  font-weight: 600;
}

.selector {
  width: 18px;
  height: 18px;
  margin-top: 4px;
}

.fixed-pill {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  background: rgba(13, 148, 136, 0.12);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.tool-kind-summary {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tool-kind-summary span {
  padding: 8px 12px;
  border-radius: var(--radius-full);
  background: rgba(15, 23, 42, 0.05);
  color: var(--gray-700);
  font-size: 13px;
  font-weight: 600;
}

.tool-item {
  display: grid;
  gap: 12px;
}

.tool-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.tool-head p {
  margin-top: 4px;
  color: var(--gray-600);
}

.tool-source {
  font-size: 12px;
}

.tool-kind {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.kind-builtin {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.kind-knowledge {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.kind-mcp {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.tool-schema {
  display: grid;
  gap: 8px;
}

.tool-schema-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
}

.tool-schema-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.schema-tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: var(--radius-full);
  background: rgba(15, 23, 42, 0.06);
  color: var(--gray-700);
  font-size: 12px;
}

.tool-schema-empty {
  color: var(--gray-500);
  font-size: 13px;
}

.tips-list {
  margin-top: 18px;
  padding-left: 18px;
  color: var(--gray-700);
  display: grid;
  gap: 12px;
}

@media (max-width: 1100px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .extensions-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
