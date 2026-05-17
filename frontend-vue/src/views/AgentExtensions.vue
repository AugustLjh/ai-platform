<template>
  <div class="agent-page">
    <AgentPageHeader
      :agent-id="agent?.id || ''"
      kicker="Agent Extensions"
      :title="agent?.name || '扩展绑定'"
      :description="agent?.description || '为当前智能体选择 skill、知识库、专家能力和 MCP 来源，工具列表只保留为生效结果。'"
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
      <article class="summary-card">
        <span class="summary-label">已授权专家能力</span>
        <strong>{{ selectedSubagentIds.length }}</strong>
        <p>主 agent 可在运行时隐式选择的受治理 capability publication</p>
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

    <div v-if="agentsStore.mcpGovernanceSummary" class="info-banner">
      MCP 治理概况：待治理 {{ agentsStore.mcpGovernanceSummary.recoveringServers || 0 }} 个，
      阻塞 {{ agentsStore.mcpGovernanceSummary.blockedServers || 0 }} 个，
      长期 stale {{ agentsStore.mcpGovernanceSummary.longStaleServers?.length || 0 }} 个。
    </div>

    <div v-if="agentsStore.mcpBulkPreviewContext" class="info-banner">
      最近一次 MCP 批量治理预演：{{ agentsStore.mcpBulkPreviewContext.riskSummary }}
      <router-link :to="manageMCPRoute" class="inline-action">继续处理</router-link>
    </div>

    <div v-if="runtimeStatusSummary" class="info-banner">
      Runtime 治理状态：{{ runtimeStatusSummary }}
    </div>

    <div v-if="selectedMCPWarnings.length > 0" class="warning-banner">
      <strong>当前选中的 MCP 绑定需要关注：</strong>
      <ul class="tips-list compact warning-action-list">
        <li v-for="warning in selectedMCPWarnings" :key="warning.id" class="warning-action-item">
          <span>
            {{ warning.message }}
            <template v-if="warning.impactSummary"> {{ warning.impactSummary }}</template>
          </span>
          <button
            v-if="warning.action"
            type="button"
            class="btn btn-secondary btn-inline"
            :disabled="warningActionBusyKey === warning.id"
            @click="handleMCPWarningAction(warning)"
          >
            {{ warningActionBusyKey === warning.id ? '处理中...' : warning.action.label }}
          </button>
        </li>
      </ul>
    </div>

    <section class="extensions-grid">
      <div class="stack">
        <div class="card scroll-card">
          <div class="section-head">
            <div>
              <h2>Skills</h2>
              <p>Skill 是能力包和行为约束，决定这个智能体该如何完成任务。</p>
            </div>
          </div>

          <div v-if="skills.length === 0" class="panel-empty">当前还没有发现技能包。</div>
          <div v-else class="catalog-list">
            <label v-for="skill in skills" :key="skill.id" :class="['catalog-item', { fixed: isFixedSkill(skill), blocked: isGovernanceBlockedSkill(skill) }]">
              <span class="catalog-main">
                <strong>{{ skill.name }}</strong>
                <span>{{ skill.slug }} · v{{ skill.version }}</span>
                <small v-if="skill.description">{{ skill.description }}</small>
                <div class="skill-meta">
                  <span class="meta-tag">{{ skillContractLabel(skill) }}</span>
                  <span v-if="skillGovernanceStatusLabel(skill)" :class="['meta-tag', 'status-tag', `availability-${skill.contract?.governanceStatus || 'ready'}`]">
                    {{ skillGovernanceStatusLabel(skill) }}
                  </span>
                  <span v-if="skillBindingSummary(skill)" class="meta-tag">{{ skillBindingSummary(skill) }}</span>
                  <span v-if="skillCapabilitySummary(skill)" class="meta-tag">{{ skillCapabilitySummary(skill) }}</span>
                  <span v-if="skillIntentSummary(skill)" class="meta-tag">{{ skillIntentSummary(skill) }}</span>
                  <span v-if="skillPhaseSummary(skill)" class="meta-tag">{{ skillPhaseSummary(skill) }}</span>
                  <span v-if="skillSurfaceSummary(skill)" class="meta-tag">{{ skillSurfaceSummary(skill) }}</span>
                  <span v-if="skillToolPolicySummary(skill)" class="meta-tag">{{ skillToolPolicySummary(skill) }}</span>
                  <span v-if="skillOutputSummary(skill)" class="meta-tag">{{ skillOutputSummary(skill) }}</span>
                </div>
                <div v-if="skillGovernanceErrors(skill).length > 0" class="skill-error-list">
                  <p v-for="error in skillGovernanceErrors(skill)" :key="`${skill.id}-error-${error}`">
                    {{ error }}
                  </p>
                </div>
                <div v-if="skillGovernanceWarnings(skill).length > 0" class="skill-warning-list">
                  <p v-for="warning in skillGovernanceWarnings(skill)" :key="`${skill.id}-${warning}`">
                    {{ warning }}
                  </p>
                </div>
                <div v-if="skillGovernanceRequirements(skill).length > 0" class="skill-warning-list">
                  <p v-for="requirement in skillGovernanceRequirements(skill)" :key="`${skill.id}-requirement-${requirement}`">
                    需补齐：{{ requirement }}
                  </p>
                </div>
              </span>
              <span v-if="isFixedSkill(skill)" class="fixed-pill">系统固定</span>
              <input
                v-model="selectedSkillIds"
                type="checkbox"
                class="selector"
                :value="skill.id"
                :disabled="isFixedSkill(skill) || isGovernanceBlockedSkill(skill)"
              />
            </label>
          </div>
        </div>

        <div class="card scroll-card">
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

        <div class="card scroll-card">
          <div class="section-head">
            <div>
              <h2>专家能力</h2>
              <p>这里授权的是已发布 capability publication，而不是把另一个用户 agent 直接绑成子代理。</p>
            </div>
          </div>

          <div v-if="subagents.length === 0" class="panel-empty">当前没有可授权的专家能力。</div>
          <div v-else class="catalog-list">
            <label v-for="subagent in subagents" :key="subagent.id" class="catalog-item">
              <span class="catalog-main">
                <strong>{{ subagent.name }}</strong>
                <span>{{ subagentStatusLabel(subagent) }} · {{ subagentScopeLabel(subagent) }} · {{ subagentVersionLabel(subagent) }}</span>
                <small v-if="subagent.description">{{ subagent.description }}</small>
                <div class="skill-meta">
                  <span v-if="subagent.slug" class="meta-tag">{{ subagent.slug }}</span>
                  <span v-if="subagent.handoffPrompt" class="meta-tag">含 handoff contract</span>
                  <span v-if="subagent.model" class="meta-tag">模型: {{ subagent.model }}</span>
                  <span v-if="subagentRiskSummary(subagent)" class="meta-tag">{{ subagentRiskSummary(subagent) }}</span>
                  <span v-if="subagentReviewSummary(subagent)" class="meta-tag">{{ subagentReviewSummary(subagent) }}</span>
                </div>
              </span>
              <input
                v-model="selectedSubagentIds"
                type="checkbox"
                class="selector"
                :value="subagent.publicationId || subagent.id"
                :disabled="subagent.status !== 'active'"
              />
            </label>
          </div>
        </div>

        <div class="card scroll-card">
          <div class="section-head">
            <div>
              <h2>MCP Servers</h2>
              <p>MCP 是外部执行能力来源，只有绑定后其工具才会进入当前 agent 的 runtime。</p>
            </div>
            <router-link :to="manageMCPRoute" class="inline-action">管理 MCP</router-link>
          </div>

          <div v-if="focusedMCPServerName" class="info-banner section-banner">
            当前正在检查 MCP server：<strong>{{ focusedMCPServerName }}</strong>
          </div>

          <div v-if="mcpServers.length === 0" class="panel-empty">当前没有配置 MCP server。</div>
          <div v-else class="catalog-list">
            <label
              v-for="server in mcpServers"
              :key="server.id"
              :class="[
                'catalog-item',
                'mcp-server-item',
                serverCardTone(server),
                {
                  selected: isServerSelected(server.id),
                  focused: focusedMCPServerId === server.id
                }
              ]"
            >
              <span class="catalog-main">
                <strong>{{ server.name }}</strong>
                <span>{{ server.transport }} · {{ serverStatusLabel(server) }}</span>
                <small>{{ serverCatalogSummary(server) }}</small>
                <div class="skill-meta">
                  <span
                    v-if="server.connection?.status"
                    :class="['meta-tag', 'status-tag', statusTone('connection', server.connection.status)]"
                  >
                    {{ statusLabel('connection', server.connection.status) }}
                  </span>
                  <span
                    v-if="server.catalog?.status"
                    :class="['meta-tag', 'status-tag', statusTone('catalog', server.catalog.status)]"
                  >
                    {{ statusLabel('catalog', server.catalog.status) }}
                  </span>
                  <span
                    v-if="server.availability?.status"
                    :class="['meta-tag', 'status-tag', statusTone('availability', server.availability.status)]"
                  >
                    {{ statusLabel('availability', server.availability.status) }}
                  </span>
                </div>
                <div class="mcp-server-details">
                  <p v-if="server.connection?.summary">{{ server.connection.summary }}</p>
                  <p v-if="server.catalog?.summary">{{ server.catalog.summary }}</p>
                  <p v-if="server.availability?.summary">{{ server.availability.summary }}</p>
                  <p v-if="server.bindingUsage?.summary">{{ server.bindingUsage.summary }}</p>
                </div>
              </span>
              <input
                v-model="selectedMCPServerIds"
                type="checkbox"
                class="selector"
                :value="server.id"
                :disabled="isServerSelectionLocked(server)"
              />
            </label>
          </div>
        </div>
      </div>

      <aside class="stack">
        <div class="card scroll-card">
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
            <span>项目上下文 {{ countToolsByKind('project-context') }}</span>
            <span>Workspace {{ countToolsByKind('workspace') }}</span>
            <span>Sandbox {{ countToolsByKind('sandbox-exec') }}</span>
          </div>

          <div class="execution-mode-panel">
            <span>执行模式</span>
            <strong>{{ executionModeLabel }}</strong>
            <p>{{ executionModeSummary }}</p>
          </div>

          <div class="capability-grid">
            <article v-for="capability in effectiveCapabilities" :key="capability.key" :class="['capability-item', `status-${capability.status}`]">
              <div>
                <strong>{{ capability.label }}</strong>
                <p>{{ capability.summary }}</p>
              </div>
              <span>{{ capability.statusLabel }}</span>
            </article>
          </div>

          <div v-if="availableTools.length === 0" class="panel-empty">当前没有加载到任何工具。</div>
          <div v-else class="tool-list">
            <article v-for="tool in availableTools" :key="tool.name" class="tool-item">
              <div class="tool-head">
                <div>
                  <strong>{{ tool.name }}</strong>
                  <p>{{ tool.description || '暂无描述' }}</p>
                  <p v-if="tool.kind === 'project-context' || tool.kind === 'engineering'" class="tool-source">
                    内部项目上下文能力 · 当前仅访问会话历史与已挂载文档
                  </p>
                  <p v-if="tool.kind === 'workspace'" class="tool-source">
                    隔离 workspace 只读能力 · {{ tool.metadata?.capability || 'workspace' }} · {{ accessLevelLabel(tool.metadata?.access_level) }}
                  </p>
                  <p v-if="tool.kind === 'mcp' && tool.metadata?.server_name" class="tool-source">
                    来源 {{ tool.metadata.server_name }} · {{ tool.metadata.source_tool_name || tool.name }}
                  </p>
                </div>
                <span :class="['tool-kind', `kind-${tool.kind}`]">{{ toolKindLabel(tool.kind) }}</span>
              </div>

              <div class="tool-policy-tags">
                <span v-if="tool.metadata?.requires_workspace">需要 Workspace</span>
                <span v-if="tool.metadata?.requires_sandbox">需要 Sandbox</span>
                <span v-if="tool.metadata?.side_effect">副作用: {{ sideEffectLabel(tool.metadata.side_effect) }}</span>
                <span v-if="tool.metadata?.risk_level">风险: {{ riskLevelLabel(tool.metadata.risk_level) }}</span>
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
              <h2>运行时治理</h2>
              <p>核对 workspace、sandbox、web、browser 和生命周期调度的真实可用状态。</p>
            </div>
            <button type="button" class="btn btn-secondary" :disabled="runtimeStatusLoading" @click="refreshRuntimeStatus">
              {{ runtimeStatusLoading ? '刷新中...' : '刷新状态' }}
            </button>
          </div>

          <div v-if="runtimeStatus" class="runtime-status-grid">
            <article v-for="item in runtimeGovernanceCards" :key="item.key" :class="['runtime-card', `tone-${item.tone}`]">
              <div class="runtime-card-head">
                <strong>{{ item.label }}</strong>
                <span>{{ item.statusLabel }}</span>
              </div>
              <p>{{ item.summary }}</p>
              <small v-if="item.detail">{{ item.detail }}</small>
            </article>
          </div>
          <div v-else class="panel-empty">当前还没有加载到运行时治理状态。</div>

          <div v-if="workspaceInspectionSummary" class="runtime-inspection-panel">
            <strong>Workspace 生命周期</strong>
            <p>{{ workspaceInspectionSummary }}</p>
            <div v-if="workspaceHealthSummary" class="runtime-health-summary">
              <span>健康摘要</span>
              <p>{{ workspaceHealthSummary }}</p>
            </div>
            <div v-if="workspaceLockSummary" class="runtime-lock-summary">
              <span>锁观测</span>
              <p>{{ workspaceLockSummary }}</p>
            </div>
            <div v-if="workspaceLifecycleLastRunSummary" class="runtime-lifecycle-last-run">
              <span>最近巡检</span>
              <p>{{ workspaceLifecycleLastRunSummary }}</p>
            </div>
            <div v-if="workspaceLifecycleTrendSummary" class="runtime-lifecycle-trend">
              <span>趋势摘要</span>
              <p>{{ workspaceLifecycleTrendSummary }}</p>
            </div>
            <div v-if="workspaceLifecycleHistory.length > 0" class="runtime-lifecycle-history">
              <span>巡检窗口</span>
              <ul>
                <li v-for="item in workspaceLifecycleHistory" :key="item.generatedAt || item.inspection?.generated_at || item.inspection?.generatedAt || item.index">
                  <strong>{{ formatDateTime(item.generatedAt) || '未知时间' }}</strong>
                  <span>{{ workspaceLifecycleHistoryItemSummary(item) }}</span>
                </li>
              </ul>
            </div>
            <div v-if="workspaceLifecycleAlerts.length > 0" class="runtime-alert-list">
              <span>最近告警</span>
              <ul>
                <li v-for="(alert, index) in workspaceLifecycleAlerts" :key="`${alert.type}-${index}`">
                  {{ lifecycleAlertLabel(alert) }}
                </li>
              </ul>
            </div>
            <div v-if="browserSessionSummary" class="runtime-browser-summary">
              <span>Browser 会话</span>
              <p>{{ browserSessionSummary }}</p>
            </div>
            <div v-if="browserSessionHealthSummary" class="runtime-browser-summary">
              <span>Browser 健康</span>
              <p>{{ browserSessionHealthSummary }}</p>
            </div>
            <div v-if="browserSessionTrendSummary" class="runtime-browser-summary">
              <span>Browser 趋势</span>
              <p>{{ browserSessionTrendSummary }}</p>
            </div>
            <div v-if="browserSessionAlerts.length > 0" class="runtime-alert-list">
              <span>Browser 告警</span>
              <ul>
                <li v-for="(alert, index) in browserSessionAlerts" :key="`${alert.type}-${index}`">
                  {{ browserSessionAlertLabel(alert) }}
                </li>
              </ul>
            </div>
            <div class="runtime-action-row">
              <button type="button" class="btn btn-secondary btn-inline" :disabled="cleanupLoading" @click="runWorkspaceCleanup(true)">
                {{ cleanupLoading ? '处理中...' : '试运行清理' }}
              </button>
              <button type="button" class="btn btn-secondary btn-inline" :disabled="cleanupLoading" @click="runWorkspaceLockCleanup(true)">
                {{ cleanupLoading ? '处理中...' : '试运行回收锁' }}
              </button>
            </div>
            <div v-if="workspaceRecoveryActions.length > 0" class="runtime-recovery-list">
              <span>恢复动作</span>
              <ul>
                <li v-for="action in workspaceRecoveryActions" :key="action.key || action.label">
                  <strong>{{ action.label || action.key }}</strong>
                  <span>{{ recoveryActionLabel(action) }}</span>
                </li>
              </ul>
            </div>
            <p v-if="workspaceCleanupSummary" class="runtime-cleanup-summary">{{ workspaceCleanupSummary }}</p>
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
            <li>专家能力绑定的是 publication 授权，不是把另一个普通 agent 直接暴露给当前 agent。</li>
            <li>当前 runtime 已按 capability publication 授权解析专家能力，旧 binding 仅保留为治理清点与迁移对象。</li>
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
import { useRoute, useRouter } from 'vue-router'
import AgentPageHeader from '@/components/agent/AgentPageHeader.vue'
import { mcpAPI } from '@/api'
import { useAgentsStore } from '@/store/agents'
import { useKnowledgeStore } from '@/store/knowledge'
import { useToastStore } from '@/store/toast'
import {
  buildMCPBindingWarnings,
  buildMCPManageRoute,
  serverCardTone,
  serverCatalogSummary,
  serverStatusLabel,
  statusLabel,
  statusTone
} from '@/utils/mcpServers'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const knowledgeStore = useKnowledgeStore()
const toastStore = useToastStore()

const saving = ref(false)
const warningActionBusyKey = ref('')
const selectedSkillIds = ref([])
const selectedMCPServerIds = ref([])
const selectedKnowledgeBaseIds = ref([])
const selectedSubagentIds = ref([])
const runtimeStatusLoading = ref(false)
const cleanupLoading = ref(false)

const agent = computed(() => agentsStore.currentAgent)
const skills = computed(() => agentsStore.skills)
const availableTools = computed(() => agentsStore.availableTools)
const executionMode = computed(() => agentsStore.availableToolsExecutionMode || agent.value?.config?.execution_mode || agent.value?.config?.runtime_policy?.execution_mode || null)
const mcpServers = computed(() => agentsStore.mcpServers)
const subagents = computed(() => agentsStore.subagents)
const knowledgeBases = computed(() => knowledgeStore.knowledgeBases)
const errorMessage = computed(() => agentsStore.error || knowledgeStore.error || '')
const runtimeStatus = computed(() => agentsStore.runtimeStatus)
const workspaceInspection = computed(() => agentsStore.workspaceInspection || runtimeStatus.value?.workspace?.inspection || null)
const workspaceCleanupResult = computed(() => agentsStore.workspaceCleanupResult)
const fixedSkillIds = computed(() => skills.value
  .filter((skill) => isFixedSkill(skill))
  .map((skill) => skill.id)
  .filter(Boolean))
const selectedMCPWarnings = computed(() => buildMCPBindingWarnings(mcpServers.value, selectedMCPServerIds.value))
const focusedMCPServerId = computed(() => String(route.query.server || '').trim())
const focusedMCPServerName = computed(() => {
  if (!focusedMCPServerId.value) return ''
  return mcpServers.value.find((server) => server.id === focusedMCPServerId.value)?.name || focusedMCPServerId.value
})
const manageMCPRoute = computed(() => buildMCPManageRoute(focusedMCPServerId.value, {
  agentId: agent.value?.id || '',
  agentName: agent.value?.name || ''
}))
const runtimeStatusSummary = computed(() => {
  if (!runtimeStatus.value) return ''
  const providers = Array.isArray(runtimeStatus.value.configuredProviders) ? runtimeStatus.value.configuredProviders.length : 0
  const browserSessions = runtimeStatus.value?.web?.browserSessions
  const browserSummary = browserSessions
    ? `browser 会话 ${Number(browserSessions.activeSessionCount || 0)}/${Number(browserSessions.sessionCount || 0)}`
    : 'browser 会话未加载'
  const lifecycle = runtimeStatus.value.workspaceLifecycle?.enabled
    ? `生命周期调度${runtimeStatus.value.workspaceLifecycle.running ? '运行中' : '已启用'}`
    : '生命周期调度未启用'
  return `${runtimeStatus.value.started ? 'runtime 已启动' : 'runtime 未启动'} · 已配置 ${providers} 个 provider · ${browserSummary} · ${lifecycle}`
})
const workspaceInspectionSummary = computed(() => {
  const inspection = workspaceInspection.value
  if (!inspection) return ''
  return [
    `共 ${Number(inspection.workspaceCount || inspection.workspace_count || 0)} 个 workspace`,
    `过期 ${Number(inspection.expiredCount || inspection.expired_count || 0)} 个`,
    `超配额 ${Number(inspection.quotaExceededCount || inspection.quota_exceeded_count || 0)} 个`,
    `总大小 ${formatBytes(Number(inspection.totalSizeBytes || inspection.total_size_bytes || 0))}`,
    `锁 ${Number(inspection.lockSummary?.lockCount || inspection.lock_summary?.lock_count || 0)} 个`
  ].join(' · ')
})
const workspaceHealthSummary = computed(() => {
  const health = workspaceInspection.value?.health || runtimeStatus.value?.workspace?.inspection?.health || {}
  if (!health) return ''
  const score = Number(health.score || 0)
  const status = health.status || 'unknown'
  const summary = health.summary || ''
  return `状态 ${status} · 评分 ${score}/100${summary ? ` · ${summary}` : ''}`
})
const workspaceLockSummary = computed(() => {
  const locks = workspaceInspection.value?.lockSummary || runtimeStatus.value?.workspace?.inspection?.lockSummary || {}
  if (!locks) return ''
  const oldest = locks.oldestLockAgeSeconds ? ` · 最老 ${Math.floor(Number(locks.oldestLockAgeSeconds) / 3600)}h` : ''
  return `总计 ${Number(locks.lockCount || 0)} 个，活动 ${Number(locks.activeLockCount || 0)} 个，陈旧 ${Number(locks.staleLockCount || 0)} 个，孤立 ${Number(locks.orphanLockCount || 0)} 个${oldest}`
})
const workspaceCleanupSummary = computed(() => {
  const result = workspaceCleanupResult.value
  if (!result) return ''
  return `${result.dry_run ? '试运行' : '正式清理'}：候选 ${Number(result.candidate_count || result.candidateCount || 0)} 个，删除 ${Number(result.deleted_count || result.deletedCount || 0)} 个，失败 ${Number(result.failed_count || result.failedCount || 0)} 个。`
})
const workspaceRecoveryActions = computed(() => {
  const health = workspaceInspection.value?.health || runtimeStatus.value?.workspace?.inspection?.health || {}
  const actions = Array.isArray(health.recoveryActions) && health.recoveryActions.length > 0
    ? health.recoveryActions
    : Array.isArray(health.recovery_actions) && health.recovery_actions.length > 0
      ? health.recovery_actions
      : Array.isArray(runtimeStatus.value?.workspaceLifecycle?.recoveryActions)
      ? runtimeStatus.value.workspaceLifecycle.recoveryActions
      : []
  return actions
})
const workspaceLifecycleLastRunSummary = computed(() => {
  const lifecycle = runtimeStatus.value?.workspaceLifecycle
  const lastRun = lifecycle?.lastRun
  if (!lastRun) return ''
  const inspection = lastRun.inspection || {}
  const cleanup = lastRun.cleanup || null
  const generatedAt = formatDateTime(lastRun.generatedAt || lifecycle.lastCompletedAt)
  const base = [
    `时间 ${generatedAt || '未知'}`,
    `workspace ${Number(inspection.workspace_count || inspection.workspaceCount || 0)} 个`,
    `过期 ${Number(inspection.expired_count || inspection.expiredCount || 0)} 个`,
    `超配额 ${Number(inspection.quota_exceeded_count || inspection.quotaExceededCount || 0)} 个`
  ]
  if (cleanup) {
    base.push(`${cleanup.dry_run ? '试运行' : '清理'}候选 ${Number(cleanup.candidate_count || cleanup.candidateCount || 0)} 个，失败 ${Number(cleanup.failed_count || cleanup.failedCount || 0)} 个`)
  }
  return base.join(' · ')
})
const workspaceLifecycleHistory = computed(() => {
  const lifecycle = runtimeStatus.value?.workspaceLifecycle || {}
  const history = Array.isArray(lifecycle.history) ? lifecycle.history : []
  return history.slice(-5).reverse().map((item, index) => ({
    ...item,
    index
  }))
})
const workspaceLifecycleTrendSummary = computed(() => {
  const trend = runtimeStatus.value?.workspaceLifecycle?.trend || null
  if (!trend) return ''
  const windowSize = Number(trend.windowSize || trend.window_size || 0)
  const delta = trend.delta || {}
  const parts = [
    `窗口 ${windowSize} 次`,
    trend.status || 'unknown',
    trend.summary || ''
  ]
  const changeParts = []
  if (Number(delta.health_score || 0) !== 0) {
    changeParts.push(`健康评分 ${formatSignedNumber(Number(delta.health_score || 0))}`)
  }
  if (Number(delta.expired_count || 0) !== 0) {
    changeParts.push(`过期 ${formatSignedNumber(Number(delta.expired_count || 0))}`)
  }
  if (Number(delta.stale_lock_count || 0) !== 0) {
    changeParts.push(`陈旧锁 ${formatSignedNumber(Number(delta.stale_lock_count || 0))}`)
  }
  if (changeParts.length > 0) {
    parts.push(changeParts.join(' · '))
  }
  return parts.filter(Boolean).join(' · ')
})
const workspaceLifecycleAlerts = computed(() => {
  const lifecycle = runtimeStatus.value?.workspaceLifecycle || {}
  const alerts = Array.isArray(lifecycle.recentAlerts) && lifecycle.recentAlerts.length > 0
    ? lifecycle.recentAlerts
    : (Array.isArray(lifecycle.lastRun?.alerts) ? lifecycle.lastRun.alerts : [])
  return alerts.slice(-5).reverse()
})
const browserSessionSummary = computed(() => {
  const sessions = runtimeStatus.value?.web?.browserSessions || null
  if (!sessions) return ''
  const active = Number(sessions.activeSessionCount || 0)
  const total = Number(sessions.sessionCount || 0)
  const expired = Number(sessions.expiredSessionCount || 0)
  const ttl = Number(sessions.sessionTtlSeconds || 0)
  const networkErrors = Number(sessions.networkErrorCount || 0)
  const consoleMessages = Number(sessions.consoleMessageCount || 0)
  const oldest = sessions.oldestSessionAgeSeconds != null
    ? `${Math.floor(Number(sessions.oldestSessionAgeSeconds) / 60)}m`
    : '未知'
  return `活跃 ${active}/${total}，过期 ${expired}，网络错误 ${networkErrors}，Console ${consoleMessages}，TTL ${ttl}s，最老 ${oldest}`
})
const browserSessionHealthSummary = computed(() => {
  const health = runtimeStatus.value?.web?.browserSessions?.health || null
  if (!health) return ''
  const score = Number(health.score || 0)
  const status = health.status || 'unknown'
  const summary = health.summary || ''
  return `状态 ${status} · 评分 ${score}/100${summary ? ` · ${summary}` : ''}`
})
const browserSessionTrendSummary = computed(() => {
  const trend = runtimeStatus.value?.web?.browserSessions?.trend || null
  if (!trend) return ''
  const windowSize = Number(trend.windowSize || trend.window_size || 0)
  const delta = trend.delta || {}
  const parts = [
    `窗口 ${windowSize} 次`,
    trend.status || 'unknown',
    trend.summary || ''
  ]
  const changeParts = []
  if (Number(delta.health_score || 0) !== 0) {
    changeParts.push(`健康评分 ${formatSignedNumber(Number(delta.health_score || 0))}`)
  }
  if (Number(delta.expired_session_count || 0) !== 0) {
    changeParts.push(`过期会话 ${formatSignedNumber(Number(delta.expired_session_count || 0))}`)
  }
  if (Number(delta.network_error_count || 0) !== 0) {
    changeParts.push(`网络错误 ${formatSignedNumber(Number(delta.network_error_count || 0))}`)
  }
  if (changeParts.length > 0) {
    parts.push(changeParts.join(' · '))
  }
  return parts.filter(Boolean).join(' · ')
})
const browserSessionAlerts = computed(() => {
  const sessions = runtimeStatus.value?.web?.browserSessions || {}
  return Array.isArray(sessions.alerts) ? sessions.alerts.slice(-5).reverse() : []
})

const normalizeIds = (value = []) => [...new Set((Array.isArray(value) ? value : []).filter(Boolean))].sort()

const isDirty = computed(() => {
  const skillIds = normalizeIds(selectedSkillIds.value)
  const agentSkillIds = normalizeIds(agent.value?.skillIds)
  const knowledgeIds = normalizeIds(selectedKnowledgeBaseIds.value)
  const agentKnowledgeIds = normalizeIds(agent.value?.knowledgeBaseIds)
  const serverIds = normalizeIds(selectedMCPServerIds.value)
  const agentServerIds = normalizeIds(agent.value?.mcpServerIds)
  const subagentIds = normalizeIds(selectedSubagentIds.value)
  const agentSubagentIds = normalizeIds(agent.value?.subagentIds)

  return JSON.stringify(skillIds) !== JSON.stringify(agentSkillIds) ||
    JSON.stringify(knowledgeIds) !== JSON.stringify(agentKnowledgeIds) ||
    JSON.stringify(serverIds) !== JSON.stringify(agentServerIds) ||
    JSON.stringify(subagentIds) !== JSON.stringify(agentSubagentIds)
})

const isFixedSkill = (skill) => skill?.contract?.bindingMode === 'fixed' || Boolean(skill?.metadata?.fixed_binding) || skill?.slug === 'implementation-planner'

const mergeFixedSkillIds = (skillIds = []) => {
  const merged = new Set(Array.isArray(skillIds) ? skillIds.filter(Boolean) : [])
  fixedSkillIds.value.forEach((skillId) => merged.add(skillId))
  return [...merged]
}

const syncSelections = () => {
  selectedSkillIds.value = mergeFixedSkillIds(agent.value?.skillIds)
  selectedMCPServerIds.value = Array.isArray(agent.value?.mcpServerIds) ? [...agent.value.mcpServerIds] : []
  selectedKnowledgeBaseIds.value = Array.isArray(agent.value?.knowledgeBaseIds) ? [...agent.value.knowledgeBaseIds] : []
  selectedSubagentIds.value = Array.isArray(agent.value?.subagentIds) ? [...agent.value.subagentIds] : []
}

const loadPage = async () => {
  const agentId = String(route.params.id || '')
  if (!agentId) return

  await Promise.all([
    agentsStore.fetchAgent(agentId),
    agentsStore.fetchSkills().catch(() => []),
    agentsStore.fetchMCPServers().catch(() => []),
    agentsStore.fetchSubagents().catch(() => []),
    knowledgeStore.fetchKnowledgeBases(1, 100).catch(() => []),
    agentsStore.fetchTools(agentId).catch(() => []),
    agentsStore.fetchRuntimeStatus().catch(() => [])
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
    await agentsStore.updateAgentSubagents(agent.value.id, selectedSubagentIds.value)
    await agentsStore.fetchTools(agent.value.id)
    toastStore.showToast({ type: 'success', message: '扩展绑定已保存' })
  } catch (error) {
    console.error('Failed to save extensions:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '保存失败' })
  } finally {
    saving.value = false
  }
}

const refreshRuntimeStatus = async () => {
  runtimeStatusLoading.value = true
  try {
    await agentsStore.fetchRuntimeStatus()
    toastStore.showToast({ type: 'success', message: '运行时治理状态已刷新' })
  } catch (error) {
    console.error('Failed to refresh runtime status:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '刷新运行时治理状态失败' })
  } finally {
    runtimeStatusLoading.value = false
  }
}

const runWorkspaceCleanup = async (dryRun = true) => {
  cleanupLoading.value = true
  try {
    await agentsStore.cleanupWorkspaces({
      dry_run: dryRun,
      confirmed: dryRun ? false : true,
      max_delete: 50
    })
    await agentsStore.fetchRuntimeStatus().catch(() => [])
    toastStore.showToast({ type: 'success', message: dryRun ? 'workspace 清理试运行已完成' : 'workspace 清理已完成' })
  } catch (error) {
    console.error('Failed to cleanup workspaces:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || 'workspace 清理失败' })
  } finally {
    cleanupLoading.value = false
  }
}

const runWorkspaceLockCleanup = async (dryRun = true) => {
  cleanupLoading.value = true
  try {
    await agentsStore.cleanupWorkspaceLocks({
      dry_run: dryRun,
      confirmed: dryRun ? false : true,
      max_delete: 50
    })
    await agentsStore.fetchRuntimeStatus().catch(() => [])
    toastStore.showToast({ type: 'success', message: dryRun ? 'workspace 锁回收试运行已完成' : 'workspace 锁回收已完成' })
  } catch (error) {
    console.error('Failed to cleanup workspace locks:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || 'workspace 锁回收失败' })
  } finally {
    cleanupLoading.value = false
  }
}

const handleMCPWarningAction = async (warning) => {
  if (!warning?.action || !warning?.serverId) return
  warningActionBusyKey.value = warning.id
  try {
    if (warning.action.type === 'manage') {
      await router.push(buildMCPManageRoute(warning.serverId, {
        agentId: agent.value?.id || '',
        agentName: agent.value?.name || ''
      }))
      return
    }

    if (warning.action.type === 'test') {
      await mcpAPI.testServer(warning.serverId)
      toastStore.showToast({ type: 'success', message: 'MCP 连接测试已完成' })
    } else if (warning.action.type === 'refresh') {
      const { data } = await mcpAPI.refreshTools(warning.serverId)
      toastStore.showToast({ type: 'success', message: `已刷新 ${data?.total || 0} 个 MCP 工具` })
    } else if (warning.action.type === 'enable') {
      const server = mcpServers.value.find((item) => item.id === warning.serverId)
      if (!server) {
        throw new Error('未找到 MCP server')
      }
      await mcpAPI.updateServer(warning.serverId, {
        name: server.name,
        transport: server.transport,
        endpoint: server.endpoint,
        command: server.command,
        args: server.args || [],
        env: server.env || {},
        metadata: server.metadata || {},
        status: 'active'
      })
      toastStore.showToast({ type: 'success', message: 'MCP server 已重新启用' })
    }

    await agentsStore.fetchMCPServers()
    if (agent.value?.id) {
      await agentsStore.fetchTools(agent.value.id).catch(() => [])
    }
  } catch (error) {
    console.error('Failed to handle MCP warning action:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || error?.response?.data?.error || 'MCP 操作失败' })
  } finally {
    warningActionBusyKey.value = ''
  }
}

const skillContractLabel = (skill) => skill?.contract?.kind === 'role_prompt' ? '角色提示' : '能力包'
const isGovernanceBlockedSkill = (skill) => skill?.contract?.governanceStatus === 'blocked'
const skillGovernanceStatusLabel = (skill) => {
  if (skill?.contract?.governanceStatus === 'blocked') return '治理阻断'
  if (skill?.contract?.governanceStatus === 'warning') return '治理告警'
  return ''
}

const skillBindingSummary = (skill) => {
  if (skill?.contract?.bindingMode === 'fixed') return '绑定: 固定'
  return skill?.contract?.systemSkill ? '绑定: 系统可选' : ''
}

const skillCapabilitySummary = (skill) => {
  const capabilityType = String(skill?.contract?.capabilityType || '').trim()
  const labelMap = {
    planning: '规划',
    review: '评审',
    knowledge_research: '知识研究',
    project_context: '项目上下文'
  }
  if (capabilityType) return `类型: ${labelMap[capabilityType] || capabilityType}`
  return ''
}

const toolsByProvider = computed(() => {
  const groups = {}
  availableTools.value.forEach((tool) => {
    const provider = String(tool.metadata?.provider || tool.kind || 'unknown')
    groups[provider] = groups[provider] || []
    groups[provider].push(tool)
  })
  return groups
})

const capabilityToolCount = (predicate) => availableTools.value.filter(predicate).length

const executionModeLabelMap = {
  context_only: '只读上下文',
  read_only_workspace: 'Workspace 只读',
  patch_proposal: 'Patch 提案',
  sandbox_verified: 'Sandbox 验证',
  network_research: '联网研究'
}

const executionModeName = computed(() => {
  const raw = typeof executionMode.value === 'string'
    ? executionMode.value
    : executionMode.value?.name
  return String(raw || 'context_only').trim().replaceAll('-', '_')
})

const executionModeLabel = computed(() => {
  if (typeof executionMode.value === 'object' && executionMode.value?.label) {
    return executionMode.value.label
  }
  return executionModeLabelMap[executionModeName.value] || executionModeName.value
})

const executionModeSummary = computed(() => {
  if (typeof executionMode.value === 'object' && executionMode.value?.summary) {
    return executionMode.value.summary
  }
  const fallback = {
    context_only: '只能使用会话、上传文件、知识库上下文和已授权外部工具。',
    read_only_workspace: '允许读取绑定 workspace 和 git 只读信息。',
    patch_proposal: '允许生成可审查 patch artifact，但不直接合并。',
    sandbox_verified: '允许在受控 sandbox 内运行测试、构建或验证任务。',
    network_research: '允许按策略联网检索和提取网页来源。'
  }
  return fallback[executionModeName.value] || '当前 agent 未声明执行模式，按只读上下文处理。'
})

const effectiveCapabilities = computed(() => {
  const projectContextCount = capabilityToolCount((tool) => tool.kind === 'project-context' || tool.kind === 'engineering' || tool.metadata?.provider === 'project-context')
  const workspaceCount = capabilityToolCount((tool) => tool.kind === 'workspace' || tool.metadata?.capability === 'workspace')
  const gitCount = capabilityToolCount((tool) => tool.kind === 'workspace' && tool.metadata?.capability === 'git')
  const sandboxCount = capabilityToolCount((tool) => tool.metadata?.requires_sandbox || tool.metadata?.capability === 'sandbox')
  const webCount = capabilityToolCount((tool) => tool.metadata?.capability === 'web' || tool.metadata?.access_level === 'network')
  const mcpCount = toolsByProvider.value.mcp?.length || 0

  const item = (key, label, count, enabledSummary, disabledSummary) => ({
    key,
    label,
    status: count > 0 ? 'ready' : 'missing',
    statusLabel: count > 0 ? `${count} 个工具` : '未配置',
    summary: count > 0 ? enabledSummary(count) : disabledSummary
  })

  return [
    item('project-context', '项目上下文', projectContextCount, () => '可读取会话历史、上传文件和已挂载文档。', '未启用 project-context provider。'),
    item('workspace', 'Workspace 只读', workspaceCount, () => '可在绑定 workspace 内列目录、读文件和搜索文本。', '未绑定或未启用 workspace，不能读取项目副本。'),
    item('git', 'Git 只读', gitCount, () => '可查看 status、diff、log、show 和 branch。', '缺少 workspace git 工具或当前未配置 workspace。'),
    item('sandbox', 'Sandbox 执行', sandboxCount, () => '可在受控执行面运行命令或验证任务。', '当前未开放 sandbox/test/build 执行能力。'),
    item('web', '联网研究', webCount, () => '可按策略访问网络或网页来源。', '当前未开放 web/browser 网络能力。'),
    item('mcp', 'MCP 外部工具', mcpCount, () => '已绑定 MCP 工具，可按 server 治理状态调用。', '未绑定可用 MCP server。')
  ]
})

const toolKindLabel = (kind) => {
  const mapping = {
    builtin: '内置',
    knowledge: '知识库',
    mcp: 'MCP',
    engineering: '项目上下文',
    'project-context': '项目上下文',
    'sandbox-exec': 'Sandbox',
    workspace: 'Workspace',
    observability: '观测'
  }
  return mapping[kind] || kind || '未知'
}

const accessLevelLabel = (value) => {
  const mapping = {
    read: '只读',
    write: '写入',
    execute: '执行',
    network: '网络'
  }
  return mapping[value] || value || '未知权限'
}

const sideEffectLabel = (value) => {
  const mapping = {
    none: '无',
    workspace_write: '写 workspace',
    process: '进程',
    network: '网络',
    external_system: '外部系统'
  }
  return mapping[value] || value
}

const riskLevelLabel = (value) => {
  const mapping = {
    low: '低',
    medium: '中',
    high: '高'
  }
  return mapping[value] || value
}

const skillIntentSummary = (skill) => {
  const intents = Array.isArray(skill?.contract?.activationIntents) ? skill.contract.activationIntents.filter(Boolean) : []
  return intents.length > 0 ? `意图: ${intents.join(' / ')}` : '意图: 全部'
}

const skillPhaseSummary = (skill) => {
  const phases = Array.isArray(skill?.contract?.activationPhases) ? skill.contract.activationPhases.filter(Boolean) : []
  return phases.length > 0 ? `阶段: ${phases.join(' / ')}` : '阶段: 全部'
}

const skillSurfaceSummary = (skill) => {
  const surfaces = Array.isArray(skill?.contract?.surfaces) ? skill.contract.surfaces.filter(Boolean) : []
  const labelMap = {
    prompt: '提示词',
    tools: '工具',
    output: '输出'
  }
  return surfaces.length > 0 ? `能力面: ${surfaces.map((surface) => labelMap[surface] || surface).join(' / ')}` : ''
}

const skillToolPolicySummary = (skill) => {
  if (skill?.contract?.toolPolicyMode === 'provider_managed') {
    const managedKinds = Array.isArray(skill?.contract?.managedToolKinds) ? skill.contract.managedToolKinds : []
    const labelMap = {
      engineering: '项目上下文'
    }
    return managedKinds.length > 0
      ? `工具策略: provider-managed (${managedKinds.map((kind) => labelMap[kind] || kind).join(' / ')})`
      : '工具策略: provider-managed'
  }
  if (skill?.contract?.toolPolicyMode === 'allowlist') {
    return `工具策略: 白名单 ${Array.isArray(skill?.toolAllowlist) ? skill.toolAllowlist.length : 0} 项`
  }
  return '工具策略: 继承运行时'
}

const skillOutputSummary = (skill) => {
  const keys = Array.isArray(skill?.contract?.outputFieldNames) ? skill.contract.outputFieldNames : []
  return keys.length > 0 ? `输出字段: ${keys.join(', ')}` : ''
}

const skillGovernanceWarnings = (skill) => Array.isArray(skill?.contract?.governanceWarnings)
  ? skill.contract.governanceWarnings.filter(Boolean)
  : []
const skillGovernanceErrors = (skill) => Array.isArray(skill?.contract?.governanceErrors)
  ? skill.contract.governanceErrors.filter(Boolean)
  : []
const skillGovernanceRequirements = (skill) => Array.isArray(skill?.contract?.governanceRequirements)
  ? skill.contract.governanceRequirements.filter(Boolean)
  : []

const knowledgeAccessLabel = (accessLevel) => {
  if (accessLevel === 'user') {
    return '个人知识库'
  }
  return '共享知识库'
}

const toolSchemaKeys = (tool) => Object.keys(tool?.inputSchema?.properties || {})
const subagentStatusLabel = (subagent) => {
  if (subagent?.status === 'active') return '已发布'
  if (subagent?.status === 'deprecated') return '已弃用'
  if (subagent?.status === 'archived') return '已归档'
  return subagent?.status || '状态未知'
}

const subagentScopeLabel = (subagent) => subagent?.publicationScope === 'system_global' ? '系统发布' : '租户发布'

const subagentVersionLabel = (subagent) => {
  if (subagent?.versionNumber) {
    return `版本 v${subagent.versionNumber}`
  }
  return subagent?.versionId ? '已版本化' : '未标注版本'
}

const subagentRiskSummary = (subagent) => {
  const risk = subagent?.metadata?.risk_level || subagent?.publicationMetadata?.risk_level
  const cost = subagent?.metadata?.cost_tier || subagent?.publicationMetadata?.cost_tier
  const compatibility = subagent?.hostAgentDefinitionId ? '兼容桥接' : ''
  if (risk && cost) return `风险 ${risk} · 成本 ${cost}`
  if (risk) return `风险 ${risk}`
  if (cost) return `成本 ${cost}`
  return compatibility
}

const subagentReviewSummary = (subagent) => {
  const requiresReview = Boolean(
    subagent?.metadata?.requires_reviewer ||
    subagent?.reviewPolicy?.requires_reviewer ||
    subagent?.reviewPolicy?.required
  )
  return requiresReview ? '要求 reviewer/judge' : ''
}

const countToolsByKind = (kind) => availableTools.value.filter((tool) => tool.kind === kind || tool.metadata?.legacy_provider === kind).length

const isServerSelected = (serverId) => selectedMCPServerIds.value.includes(serverId)

const isServerSelectionLocked = (server) => Boolean(server?.availability) && !isServerSelected(server?.id) && !server.availability.bindable

const formatBytes = (value) => {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

const formatSignedNumber = (value) => {
  const number = Number(value || 0)
  if (!Number.isFinite(number) || number === 0) return '0'
  return number > 0 ? `+${number}` : `${number}`
}

const formatDateTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

const lifecycleAlertLabel = (alert = {}) => {
  const typeMap = {
    expired_workspaces: '过期 workspace 数量超过阈值',
    quota_exceeded_workspaces: '超配额 workspace 数量超过阈值',
    quota_bytes: 'workspace 总存储超过阈值',
    stale_cleanup_locks: '陈旧清理锁数量超过阈值',
    orphan_cleanup_locks: '孤立清理锁需要清理'
  }
  const label = typeMap[alert.type] || alert.message || alert.type || '生命周期告警'
  const hasBytes = Object.prototype.hasOwnProperty.call(alert, 'bytes') || alert.type === 'quota_bytes'
  if (hasBytes) {
    const value = formatBytes(Number(alert.bytes || 0))
    const threshold = formatBytes(Number(alert.threshold || 0))
    return `${label}：${value} / ${threshold}`
  }
  return `${label}：${Number(alert.count || 0)} / ${Number(alert.threshold || 0)}`
}

const browserSessionAlertLabel = (alert = {}) => {
  const typeMap = {
    expired_browser_sessions: 'Browser 会话已超过 TTL',
    browser_network_errors: 'Browser 会话存在网络错误'
  }
  const label = typeMap[alert.type] || alert.message || alert.type || 'Browser 告警'
  return `${label}：${Number(alert.count || 0)} / ${Number(alert.threshold || 0)}`
}

const recoveryActionLabel = (action = {}) => {
  const details = []
  if (action.category) details.push(action.category)
  if (action.priority) details.push(`优先级 ${action.priority}`)
  if (action.requires_confirmation) details.push('需要确认')
  if (action.tenant_scoped) details.push('租户级')
  return details.join(' · ')
}

const workspaceLifecycleHistoryItemSummary = (item = {}) => {
  const inspection = item.inspection || {}
  const cleanup = item.cleanup || null
  const parts = [
    `workspace ${Number(inspection.workspace_count || inspection.workspaceCount || 0)} 个`,
    `过期 ${Number(inspection.expired_count || inspection.expiredCount || 0)} 个`,
    `超配额 ${Number(inspection.quota_exceeded_count || inspection.quotaExceededCount || 0)} 个`
  ]
  if (cleanup) {
    parts.push(`${cleanup.dry_run ? '试运行' : '清理'}候选 ${Number(cleanup.candidate_count || cleanup.candidateCount || 0)} 个`)
  }
  return parts.join(' · ')
}

const runtimeGovernanceCards = computed(() => {
  const status = runtimeStatus.value
  if (!status) return []
  const cards = []
  const add = (key, label, ok, summary, detail = '') => {
    cards.push({
      key,
      label,
      tone: ok ? 'ready' : 'warning',
      statusLabel: ok ? '可用' : '需处理',
      summary,
      detail
    })
  }
  add(
    'workspace',
    'Workspace',
    Boolean(status.workspace?.enabled),
    status.workspace?.enabled
      ? `base root 已配置，当前 ${status.workspace?.inspection?.workspaceCount || 0} 个 run workspace。`
      : 'workspace manager 未启用。',
    status.workspace?.baseRoot || ''
  )
  add(
    'sandbox',
    'Sandbox',
    Boolean(status.sandbox?.enabled && status.sandbox?.runnerConfigured),
    status.sandbox?.enabled && status.sandbox?.runnerConfigured
      ? `runner=${status.sandbox?.runnerBackend || 'unknown'}，网络=${status.sandbox?.networkMode || 'unknown'}，隔离=${status.sandbox?.isolation?.status || 'unknown'}。`
      : 'sandbox provider 或 runner 尚未完成配置。',
    [
      status.sandbox?.dockerImage || '',
      status.sandbox?.isolation?.productionReady ? 'production-ready' : '',
      status.sandbox?.isolation?.recoveryActions?.length ? `${status.sandbox.isolation.recoveryActions.length} recovery actions` : ''
    ].filter(Boolean).join(' · ')
  )
  add(
    'web',
    'Web',
    Boolean(status.web?.enabled && status.web?.networkConfigured),
    status.web?.enabled && status.web?.networkConfigured
      ? `允许域名 ${status.web?.allowedDomains?.length || 0} 个，搜索端点 ${status.web?.searchEndpoint || '未配置'}。`
      : 'web provider 或网络策略尚未完成配置。',
    [
      status.web?.deniedDomains?.length ? `deny ${status.web.deniedDomains.join(', ')}` : '',
      status.web?.searchQuality
        ? `search rules: url=${status.web.searchQuality.requireUrl ? 'on' : 'off'}, title=${status.web.searchQuality.requireTitle ? 'on' : 'off'}, snippet=${status.web.searchQuality.requireSnippet ? 'on' : 'off'}, schemes=${status.web.searchQuality.allowedSchemes?.join(', ') || 'none'}`
        : '',
      status.web?.browserSessions
        ? `${status.web.browserSessions.activeSessionCount || 0}/${status.web.browserSessions.sessionCount || 0} browser sessions, health=${status.web.browserSessions.health?.status || 'unknown'}`
        : ''
    ].filter(Boolean).join(' · ')
  )
  add(
    'browser',
    'Browser',
    Boolean(status.browser?.enabled && status.browser?.configured && status.browser?.runtimeAvailable),
    status.browser?.enabled && status.browser?.configured && status.browser?.runtimeAvailable
      ? `${status.browser?.backend || 'browser'} / ${status.browser?.name || 'default'} 已就绪。`
      : 'browser 开关、配置或运行时依赖尚未满足。',
    [
      status.browser?.runtimeReason || '',
      status.browser?.sessionTtlSeconds ? `session ttl ${status.browser.sessionTtlSeconds}s` : ''
    ].filter(Boolean).join(' · ')
  )
  add(
    'lifecycle',
    'Lifecycle',
    Boolean(status.workspaceLifecycle?.enabled),
    status.workspaceLifecycle?.enabled
      ? `周期 ${status.workspaceLifecycle?.intervalSeconds || 0}s，${status.workspaceLifecycle?.dryRun ? 'dry-run' : '执行删除'}，最近告警 ${workspaceLifecycleAlerts.value.length} 条。`
      : 'workspace 生命周期调度未启用。',
    [
      status.workspaceLifecycle?.running ? `调度器运行中${status.workspaceLifecycle?.lastCompletedAt ? `，最近完成 ${formatDateTime(status.workspaceLifecycle.lastCompletedAt)}` : ''}` : '调度器未运行',
      status.workspaceLifecycle?.recoveryActions?.length ? `${status.workspaceLifecycle.recoveryActions.length} 个恢复动作` : ''
    ].filter(Boolean).join(' · ')
  )
  return cards
})

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
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
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

.scroll-card .catalog-list,
.scroll-card .tool-list {
  max-height: min(58vh, 680px);
  overflow-y: auto;
  padding-right: 6px;
}

.scroll-card .panel-empty {
  max-height: min(36vh, 280px);
  overflow-y: auto;
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
.info-banner,
.warning-banner {
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

.warning-banner {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.22);
  color: #92400e;
}

.section-banner {
  margin-top: 12px;
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

.mcp-server-item {
  align-items: flex-start;
}

.mcp-server-item.selected {
  border-color: rgba(13, 148, 136, 0.32);
}

.mcp-server-item.focused {
  border-color: rgba(245, 158, 11, 0.38);
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.12);
}

.mcp-server-item.tone-ready {
  background: rgba(16, 185, 129, 0.06);
}

.mcp-server-item.tone-warning {
  background: rgba(245, 158, 11, 0.08);
}

.mcp-server-item.tone-danger {
  background: rgba(239, 68, 68, 0.08);
}

.mcp-server-item.tone-disabled {
  background: rgba(148, 163, 184, 0.14);
}

.catalog-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.skill-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.catalog-main strong {
  color: var(--gray-900);
  word-break: break-word;
}

.catalog-main span,
.catalog-main small {
  color: var(--gray-600);
  word-break: break-word;
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

.status-tag.connection-healthy,
.status-tag.catalog-ready,
.status-tag.availability-available {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.status-tag.connection-degraded,
.status-tag.availability-degraded,
.status-tag.availability-unavailable {
  background: rgba(239, 68, 68, 0.14);
  color: #b91c1c;
}

.status-tag.connection-untested,
.status-tag.catalog-stale,
.status-tag.catalog-empty,
.status-tag.catalog-missing,
.status-tag.availability-warning {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.status-tag.connection-disabled,
.status-tag.catalog-disabled,
.status-tag.availability-disabled {
  background: rgba(148, 163, 184, 0.2);
  color: #475569;
}

.mcp-server-details {
  display: grid;
  gap: 4px;
  margin-top: 4px;
}

.skill-warning-list {
  display: grid;
  gap: 4px;
  margin-top: 6px;
}

.skill-error-list {
  display: grid;
  gap: 4px;
  margin-top: 6px;
}

.skill-error-list p {
  color: #b91c1c;
  font-size: 12px;
}

.skill-warning-list p {
  color: #92400e;
  font-size: 12px;
}

.catalog-item.blocked {
  border-color: rgba(239, 68, 68, 0.26);
  background: rgba(239, 68, 68, 0.04);
}

.mcp-server-details p {
  color: var(--gray-600);
  font-size: 13px;
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

.execution-mode-panel {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(14, 165, 233, 0.2);
  background: rgba(14, 165, 233, 0.06);
}

.execution-mode-panel span {
  display: block;
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 700;
}

.execution-mode-panel strong {
  display: block;
  margin-top: 4px;
  color: var(--gray-900);
}

.execution-mode-panel p {
  margin-top: 4px;
  color: var(--gray-600);
  font-size: 13px;
}

.capability-grid {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.capability-item {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(248, 250, 252, 0.75);
}

.capability-item strong {
  color: var(--gray-900);
}

.capability-item p {
  margin-top: 4px;
  color: var(--gray-600);
  font-size: 13px;
}

.capability-item > span {
  flex-shrink: 0;
  align-self: flex-start;
  padding: 5px 8px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.capability-item.status-ready {
  border-color: rgba(16, 185, 129, 0.24);
  background: rgba(16, 185, 129, 0.06);
}

.capability-item.status-ready > span {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.capability-item.status-missing > span {
  background: rgba(148, 163, 184, 0.18);
  color: #475569;
}

.runtime-status-grid {
  margin-top: 18px;
  display: grid;
  gap: 12px;
}

.runtime-card {
  padding: 14px 16px;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.72);
}

.runtime-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.runtime-card-head span {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}

.runtime-card p {
  margin-top: 6px;
  color: var(--gray-700);
  font-size: 13px;
}

.runtime-card small {
  display: block;
  margin-top: 6px;
  color: var(--gray-500);
}

.runtime-card.tone-ready {
  border-color: rgba(16, 185, 129, 0.22);
  background: rgba(16, 185, 129, 0.06);
}

.runtime-card.tone-warning {
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(245, 158, 11, 0.06);
}

.runtime-inspection-panel {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(14, 165, 233, 0.2);
  background: rgba(14, 165, 233, 0.05);
}

.runtime-inspection-panel p {
  margin-top: 6px;
  color: var(--gray-700);
}

.runtime-health-summary,
.runtime-lock-summary,
.runtime-lifecycle-last-run,
.runtime-lifecycle-trend,
.runtime-lifecycle-history,
.runtime-alert-list,
.runtime-browser-summary,
.runtime-recovery-list {
  margin-top: 12px;
}

.runtime-health-summary span,
.runtime-lock-summary span,
.runtime-lifecycle-last-run span,
.runtime-lifecycle-trend span,
.runtime-lifecycle-history span,
.runtime-alert-list span,
.runtime-browser-summary span,
.runtime-recovery-list span {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.runtime-lifecycle-history ul,
.runtime-alert-list ul,
.runtime-recovery-list ul {
  display: grid;
  gap: 6px;
  margin-top: 6px;
  padding-left: 18px;
}

.runtime-lifecycle-history li,
.runtime-alert-list li,
.runtime-recovery-list li {
  color: var(--gray-700);
  font-size: 13px;
}

.runtime-lifecycle-history strong,
.runtime-alert-list strong,
.runtime-recovery-list strong {
  color: var(--gray-900);
}

.runtime-action-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.runtime-cleanup-summary {
  margin-top: 10px;
  font-size: 13px;
  color: #0f766e;
}

.runtime-lifecycle-last-run,
.runtime-alert-list {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(14, 165, 233, 0.16);
}

.runtime-lifecycle-last-run span,
.runtime-alert-list span {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #0369a1;
}

.runtime-alert-list ul {
  margin: 6px 0 0;
  padding-left: 18px;
  color: var(--gray-700);
  font-size: 13px;
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
  word-break: break-word;
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

.kind-project-context,
.kind-engineering {
  background: rgba(14, 165, 233, 0.12);
  color: #0369a1;
}

.kind-workspace {
  background: rgba(124, 58, 237, 0.12);
  color: #5b21b6;
}

.kind-sandbox-exec {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
}

.tool-policy-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-policy-tags span {
  display: inline-flex;
  align-items: center;
  padding: 5px 8px;
  border-radius: var(--radius-full);
  background: rgba(15, 23, 42, 0.06);
  color: var(--gray-700);
  font-size: 12px;
  font-weight: 600;
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

.tips-list.compact {
  margin-top: 10px;
  gap: 8px;
}

.warning-action-list {
  display: grid;
  gap: 10px;
}

.warning-action-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.btn-inline {
  flex-shrink: 0;
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

  .warning-action-item {
    flex-direction: column;
  }
}
</style>
