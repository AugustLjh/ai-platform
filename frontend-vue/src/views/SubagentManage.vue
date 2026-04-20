<template>
  <div class="subagent-page">
    <section class="subagent-hero">
      <div>
        <div class="hero-kicker">Managed Capabilities</div>
        <h1>专家能力控制台</h1>
        <p>
          维护 capability
          definition、版本、发布状态和测试运行入口，让管理员直接完成 E3
          控制面闭环。
        </p>
      </div>
      <div class="hero-actions">
        <button type="button" class="btn btn-secondary" @click="reloadAll">
          刷新
        </button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!isAdmin"
          @click="openCreate"
        >
          新增能力
        </button>
      </div>
    </section>

    <div v-if="!isAdmin" class="error-banner">
      当前账号不是管理员。你可以查看入口，但后端会拒绝维护类操作。
    </div>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="subagent-grid">
      <div class="card list-card">
        <div class="section-head">
          <div>
            <h2>Capability 列表</h2>
            <p>选择一个专家能力查看 control plane、发布状态和授权影响面。</p>
          </div>
          <label class="toggle">
            <input
              v-model="includeArchived"
              type="checkbox"
              @change="loadSubagents"
            />
            <span>包含 archived</span>
          </label>
        </div>

        <div v-if="loadingList && subagents.length === 0" class="panel-empty">
          正在加载专家能力...
        </div>

        <div v-else-if="subagents.length === 0" class="panel-empty">
          当前还没有专家能力。
        </div>

        <div v-else class="subagent-list">
          <button
            v-for="item in subagents"
            :key="item.definitionId || item.id"
            type="button"
            :class="[
              'subagent-item',
              { active: selectedDefinitionId === item.definitionId },
            ]"
            @click="selectSubagent(item.definitionId)"
          >
            <div class="subagent-item-top">
              <strong>{{ item.name }}</strong>
              <span
                :class="['status-pill', `status-${toneStatus(item.status)}`]"
                >{{ item.status }}</span
              >
            </div>
            <div class="subagent-item-meta">
              <span>{{ publicationScopeLabel(item.publicationScope) }}</span>
              <span>v{{ item.versionNumber || 0 }}</span>
              <span>{{ item.model || "未显式指定模型" }}</span>
            </div>
            <div class="subagent-item-sub">
              {{ item.description || item.slug || "暂无说明" }}
            </div>
            <div class="subagent-item-tags">
              <span v-if="item.slug" class="mini-badge">{{ item.slug }}</span>
              <span v-if="item.hostAgentDefinitionId" class="mini-badge"
                >host {{ agentNameById(item.hostAgentDefinitionId) }}</span
              >
              <span v-if="item.handoffPrompt" class="mini-badge"
                >含 handoff</span
              >
            </div>
          </button>
        </div>
      </div>

      <div class="card editor-card">
        <div class="section-head">
          <div>
            <h2>
              {{ editingDefinitionId ? "编辑 Definition" : "新增 Definition" }}
            </h2>
            <p>
              Definition 保存 capability 基线；运行时行为由版本与 publication
              决定。
            </p>
          </div>
          <div class="detail-actions">
            <button
              type="button"
              class="btn btn-secondary"
              @click="resetDefinitionForm"
            >
              清空
            </button>
            <button
              v-if="editingDefinitionId"
              type="button"
              class="btn btn-danger"
              :disabled="busyAction === 'delete' || !isAdmin"
              @click="deleteDefinition"
            >
              删除
            </button>
          </div>
        </div>

        <form class="editor-form" @submit.prevent="saveDefinition">
          <div class="field-row">
            <label class="field">
              <span>名称</span>
              <input
                v-model="definitionForm.name"
                class="input"
                maxlength="120"
              />
            </label>
            <label class="field">
              <span>Slug</span>
              <input
                v-model="definitionForm.slug"
                class="input"
                maxlength="120"
                placeholder="例如 code-reviewer"
              />
            </label>
          </div>

          <label class="field">
            <span>描述</span>
            <textarea
              v-model="definitionForm.description"
              class="input textarea"
              rows="3"
            ></textarea>
          </label>

          <div class="field-row">
            <label class="field">
              <span>Publication Scope</span>
              <select v-model="definitionForm.publicationScope" class="input">
                <option value="tenant">tenant</option>
                <option value="system_global">system_global</option>
              </select>
            </label>
            <label class="field">
              <span>Status</span>
              <select v-model="definitionForm.status" class="input">
                <option value="active">active</option>
                <option value="disabled">disabled</option>
                <option value="archived">archived</option>
              </select>
            </label>
          </div>

          <div class="field-row">
            <label class="field">
              <span>Lifecycle</span>
              <select v-model="definitionForm.lifecycleStatus" class="input">
                <option value="active">active</option>
                <option value="draft">draft</option>
                <option value="review">review</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label class="field">
              <span>Model</span>
              <input
                v-model="definitionForm.model"
                class="input"
                placeholder="留空表示沿用 runtime 默认"
              />
            </label>
          </div>

          <div class="field-row">
            <label class="field">
              <span>Host Agent</span>
              <select
                v-model="definitionForm.hostAgentDefinitionId"
                class="input"
              >
                <option value="">未指定</option>
                <option
                  v-for="agent in activeAgents"
                  :key="agent.id"
                  :value="agent.id"
                >
                  {{ agent.name }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>Definition Status</span>
              <select v-model="definitionForm.definitionStatus" class="input">
                <option value="active">active</option>
                <option value="disabled">disabled</option>
                <option value="archived">archived</option>
              </select>
            </label>
          </div>

          <label class="field">
            <span>System Prompt</span>
            <textarea
              v-model="definitionForm.systemPrompt"
              class="input textarea tall-textarea"
              rows="8"
            ></textarea>
          </label>

          <label class="field">
            <span>Handoff Prompt</span>
            <textarea
              v-model="definitionForm.handoffPrompt"
              class="input textarea"
              rows="4"
              placeholder="主 agent 委派给该 capability 时补充的 handoff contract"
            ></textarea>
          </label>

          <details class="advanced-panel">
            <summary>高级 JSON 配置</summary>
            <div class="advanced-grid">
              <label class="field">
                <span>Config JSON</span>
                <textarea
                  v-model="definitionForm.configText"
                  class="input textarea"
                  rows="6"
                ></textarea>
              </label>
              <label class="field">
                <span>Metadata JSON</span>
                <textarea
                  v-model="definitionForm.metadataText"
                  class="input textarea"
                  rows="6"
                ></textarea>
              </label>
              <label class="field">
                <span>Output Schema JSON</span>
                <textarea
                  v-model="definitionForm.outputSchemaText"
                  class="input textarea"
                  rows="6"
                ></textarea>
              </label>
              <label class="field">
                <span>Handoff Input Schema JSON</span>
                <textarea
                  v-model="definitionForm.handoffInputSchemaText"
                  class="input textarea"
                  rows="6"
                ></textarea>
              </label>
              <label class="field">
                <span>Tool Allowlist JSON</span>
                <textarea
                  v-model="definitionForm.toolAllowlistText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>Skill Allowlist JSON</span>
                <textarea
                  v-model="definitionForm.skillAllowlistText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>MCP Allowlist JSON</span>
                <textarea
                  v-model="definitionForm.mcpAllowlistText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>Knowledge Policy JSON</span>
                <textarea
                  v-model="definitionForm.knowledgePolicyText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>Review Policy JSON</span>
                <textarea
                  v-model="definitionForm.reviewPolicyText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>Runtime Policy JSON</span>
                <textarea
                  v-model="definitionForm.runtimePolicyText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
              <label class="field">
                <span>Publication Metadata JSON</span>
                <textarea
                  v-model="definitionForm.publicationMetadataText"
                  class="input textarea"
                  rows="5"
                ></textarea>
              </label>
            </div>
          </details>

          <div class="form-actions">
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="savingDefinition || !isAdmin"
            >
              {{
                savingDefinition
                  ? "保存中..."
                  : editingDefinitionId
                    ? "保存 Definition"
                    : "创建 Definition"
              }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section class="card tenant-governance-card">
      <div class="section-head">
        <div>
          <h2>Tenant 治理视图</h2>
          <p>
            跨 capability 清点 metadata alias、发布治理历史和删桥后的收敛进度，
            用于继续推进后续主线。
          </p>
        </div>
        <div class="detail-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="loadingGovernance"
            @click="loadTenantGovernance"
          >
            {{ loadingGovernance ? "加载中..." : "刷新治理视图" }}
          </button>
        </div>
      </div>

      <div
        class="summary-grid governance-summary-grid"
        v-if="tenantGovernanceSummary"
      >
        <article class="summary-card">
          <span class="summary-label">遗留别名</span>
          <strong
            >{{ tenantGovernanceSummary.compatibilityCapabilities }} /
            {{ tenantGovernanceSummary.totalCapabilities }}</strong
          >
          <p>仍有 metadata alias 的 capability 数</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">宿主绑定</span>
          <strong>{{
            tenantGovernanceSummary.hostOverrideCapabilities
          }}</strong>
          <p>
            metadata alias
            {{ tenantGovernanceSummary.metadataAliasCapabilities }} 个
            capability
          </p>
        </article>
        <article class="summary-card">
          <span class="summary-label">发布收敛</span>
          <strong>{{
            tenantGovernanceSummary.publicationNotLatestCount
          }}</strong>
          <p>未发布 {{ tenantGovernanceSummary.publicationMissingCount }} 个</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">授权活跃度</span>
          <strong
            >{{ tenantGovernanceSummary.enabledAuthorizationCount }} /
            {{ tenantGovernanceSummary.authorizationCount }}</strong
          >
          <p>
            inactive 授权
            {{ tenantGovernanceSummary.inactiveAuthorizationCount }} 个
          </p>
        </article>
        <article class="summary-card">
          <span class="summary-label">收口就绪</span>
          <strong>{{
            tenantGovernanceSummary.bridgeRemovalReadyCapabilities
          }}</strong>
          <p>
            阻塞 {{ tenantGovernanceSummary.bridgeRemovalBlockedCount }} 项 ·
            待收尾 {{ tenantGovernanceSummary.bridgeRemovalPendingCount }} 项
          </p>
        </article>
        <article class="summary-card">
          <span class="summary-label">高风险事件</span>
          <strong>{{ tenantGovernanceSummary.highRiskEventCount }}</strong>
          <p>
            需确认
            {{ tenantGovernanceSummary.confirmationRequiredEventCount }} 条
          </p>
        </article>
        <article class="summary-card">
          <span class="summary-label">最近事件</span>
          <strong>{{ tenantGovernanceTotal }}</strong>
          <p>{{ tenantTopChangeType }}</p>
        </article>
      </div>

      <div class="migration-panel">
        <div class="migration-panel-head">
          <div>
            <strong>Metadata Alias 冻结</strong>
            <p>
              tenant 级批量冻结 `target_agent_definition_id` /
              `agent_definition_id` 历史残量，收口到 canonical
              `host_agent_definition_id`，且不创建新版本。
            </p>
          </div>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="
              busyAction === 'metadata-alias-freeze' ||
              !isAdmin ||
              (metadataAliasFreezeForm.scope === 'selection' &&
                !selectedDefinitionId)
            "
            @click="runMetadataAliasFreeze"
          >
            {{
              busyAction === "metadata-alias-freeze"
                ? "执行中..."
                : "执行冻结"
            }}
          </button>
        </div>
        <div class="field-row">
          <label class="field">
            <span>治理范围</span>
            <select v-model="metadataAliasFreezeForm.scope" class="input">
              <option value="tenant">整个 tenant</option>
              <option value="selection">当前选中 capability</option>
            </select>
          </label>
          <label class="field">
            <span>当前 capability</span>
            <input
              class="input"
              :value="
                selectedDefinitionId
                  ? controlPlane.definition?.name || selectedDefinitionId
                  : '未选择'
              "
              disabled
            />
          </label>
        </div>
        <template v-if="effectiveMetadataAliasFreezePreview">
          <p>{{ effectiveMetadataAliasFreezePreview.summary }}</p>
          <p
            v-if="effectiveMetadataAliasFreezePreview.blockedReason"
            class="preview-confirmation-copy"
          >
            {{ effectiveMetadataAliasFreezePreview.blockedReason }}
          </p>
          <div class="detail-table preview-table">
            <div>
              <span>Capability 数</span
              ><strong>{{
                effectiveMetadataAliasFreezePreview.impactedCapabilityCount
              }}</strong>
            </div>
            <div>
              <span>Enabled 授权</span
              ><strong>{{
                effectiveMetadataAliasFreezePreview.enabledAuthorizationCount
              }}</strong>
            </div>
            <div>
              <span>Inactive 授权</span
              ><strong>{{
                effectiveMetadataAliasFreezePreview.inactiveAuthorizationCount
              }}</strong>
            </div>
            <div>
              <span>可执行</span
              ><strong>{{
                effectiveMetadataAliasFreezePreview.executable ? "是" : "否"
              }}</strong>
            </div>
          </div>
          <p
            v-if="effectiveMetadataAliasFreezePreview.confirmationMessage"
            class="preview-confirmation-copy"
          >
            {{ effectiveMetadataAliasFreezePreview.confirmationMessage }}
          </p>
          <div
            v-if="effectiveMetadataAliasFreezePreview.recommendedActions?.length"
            class="preview-action-list"
          >
            <span
              v-for="(
                item, index
              ) in effectiveMetadataAliasFreezePreview.recommendedActions"
              :key="`metadata-alias-action-${item}-${index}`"
              class="mini-badge"
            >
              {{ item }}
            </span>
          </div>
          <div
            v-if="effectiveMetadataAliasFreezePreview.affectedCapabilities?.length"
            class="compatibility-detail-list"
          >
            <article
              v-for="capability in effectiveMetadataAliasFreezePreview.affectedCapabilities"
              :key="capability.definitionId"
              class="compatibility-detail-card"
            >
              <div class="compatibility-detail-head">
                <strong>{{
                  capability.definitionName || capability.definitionId
                }}</strong>
                <span class="mini-badge"
                  >{{ capability.enabledAuthorizationCount }} /
                  {{ capability.authorizationCount }} enabled</span
                >
              </div>
              <p>
                {{
                  capability.legacyAliasKey || "legacy alias"
                }} -> {{ capability.legacyAliasValue || "空值" }}
              </p>
              <p v-if="capability.hostAgentDefinitionId">
                冻结后宿主:
                {{ agentNameById(capability.hostAgentDefinitionId) }}
              </p>
            </article>
          </div>
        </template>
      </div>

      <div class="tenant-governance-toolbar">
        <label class="field">
          <span>Capability</span>
          <select
            v-model="tenantGovernanceFilters.definitionId"
            class="input compact-select"
            @change="resetTenantGovernancePageAndLoad"
          >
            <option value="">全部 capability</option>
            <option
              v-for="item in subagents"
              :key="item.definitionId"
              :value="item.definitionId"
            >
              {{ item.name }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>动作</span>
          <select
            v-model="tenantGovernanceFilters.actionType"
            class="input compact-select"
            @change="resetTenantGovernancePageAndLoad"
          >
            <option value="">全部动作</option>
            <option value="publish">publish</option>
            <option value="rollout">rollout</option>
            <option value="rollback">rollback</option>
            <option value="status_change">status_change</option>
            <option value="metadata_update">metadata_update</option>
            <option value="metadata_alias_freeze">metadata_alias_freeze</option>
          </select>
        </label>
        <label class="field">
          <span>阶段</span>
          <select
            v-model="tenantGovernanceFilters.eventStage"
            class="input compact-select"
            @change="resetTenantGovernancePageAndLoad"
          >
            <option value="">全部阶段</option>
            <option value="previewed">previewed</option>
            <option value="executed">executed</option>
          </select>
        </label>
        <label class="field">
          <span>风险</span>
          <select
            v-model="tenantGovernanceFilters.riskLevel"
            class="input compact-select"
            @change="resetTenantGovernancePageAndLoad"
          >
            <option value="">全部风险</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>
        <label class="field">
          <span>兼容事件</span>
          <select
            v-model="tenantGovernanceFilters.compatibilityMode"
            class="input compact-select"
            @change="resetTenantGovernancePageAndLoad"
          >
            <option value="">全部</option>
            <option value="true">仅兼容压力</option>
            <option value="false">仅非兼容</option>
          </select>
        </label>
      </div>

      <div
        v-if="tenantGovernanceEvents.length === 0"
        class="panel-empty compact-empty"
      >
        当前筛选条件下没有治理历史。
      </div>

      <div v-else class="event-list tenant-event-list">
        <article
          v-for="event in tenantGovernanceEvents"
          :key="event.id"
          class="event-card"
        >
          <div class="event-card-head">
            <div>
              <strong>{{
                event.definitionName || event.definitionId || "未知 capability"
              }}</strong>
              <span
                >{{ publicationEventStageLabel(event.eventStage) }} ·
                {{ publicationChangeLabel(event.changeType) }}</span
              >
            </div>
            <span
              :class="[
                'status-pill',
                `status-${toneStatus(event.riskLevel === 'high' ? 'disabled' : event.riskLevel === 'medium' ? 'pending' : 'active')}`,
              ]"
            >
              {{ publicationRiskLabel(event.riskLevel) }}
            </span>
          </div>
          <p class="version-copy">{{ event.summary || "无摘要" }}</p>
          <div class="event-meta-grid">
            <span
              >版本
              {{
                event.previousVersionNumber
                  ? `v${event.previousVersionNumber}`
                  : "-"
              }}
              ->
              {{ event.versionNumber ? `v${event.versionNumber}` : "-" }}</span
            >
            <span
              >授权 {{ event.enabledAuthorizationCount }} /
              {{ event.impactedAuthorizationCount }}</span
            >
            <span>{{
              event.actorUserEmail || event.actorUserId || "系统"
            }}</span>
            <span>{{ formatTime(event.createdAt) }}</span>
          </div>
          <div class="card-inline-actions">
            <button
              v-if="event.definitionId"
              type="button"
              class="btn btn-secondary btn-inline"
              @click="selectSubagent(event.definitionId)"
            >
              查看 capability
            </button>
          </div>
        </article>
      </div>

      <div class="tenant-governance-pagination">
        <button
          type="button"
          class="btn btn-secondary btn-inline"
          :disabled="tenantGovernancePage <= 1 || loadingGovernance"
          @click="changeTenantGovernancePage(-1)"
        >
          上一页
        </button>
        <span
          >第 {{ tenantGovernancePage }} / {{ tenantGovernanceTotalPages }} 页 ·
          共 {{ tenantGovernanceTotal }} 条</span
        >
        <button
          type="button"
          class="btn btn-secondary btn-inline"
          :disabled="
            tenantGovernancePage >= tenantGovernanceTotalPages ||
            loadingGovernance
          "
          @click="changeTenantGovernancePage(1)"
        >
          下一页
        </button>
      </div>
    </section>

    <section v-if="controlPlane.definition" class="card detail-card">
      <div class="section-head">
        <div>
          <h2>{{ controlPlane.definition.name }}</h2>
          <p>Control plane 汇总版本、发布和被哪些 host agent 授权使用。</p>
        </div>
        <div class="detail-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="loadingDetail"
            @click="loadControlPlane(selectedDefinitionId)"
          >
            重新载入
          </button>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="!selectedDefinitionId"
            @click="seedVersionFormFromDefinition"
          >
            用当前定义填充新版本
          </button>
        </div>
      </div>

      <section class="summary-grid">
        <article class="summary-card">
          <span class="summary-label">当前发布</span>
          <strong>{{
            controlPlane.publication?.versionNumber
              ? `v${controlPlane.publication.versionNumber}`
              : "未发布"
          }}</strong>
          <p>
            {{
              controlPlane.publication
                ? publicationScopeLabel(
                    controlPlane.publication.publicationScope,
                  )
                : "暂无 publication"
            }}
          </p>
        </article>
        <article class="summary-card">
          <span class="summary-label">版本总数</span>
          <strong>{{ controlPlane.versions.length }}</strong>
          <p>最新版本 {{ latestVersionLabel }}</p>
        </article>
        <article class="summary-card">
          <span class="summary-label">启用授权</span>
          <strong>{{ enabledAuthorizationCount }}</strong>
          <p>共 {{ controlPlane.authorizations.length }} 个 host agent</p>
        </article>
        <article class="summary-card accent">
          <span class="summary-label">Host Agent</span>
          <strong>{{
            agentNameById(controlPlane.definition.hostAgentDefinitionId)
          }}</strong>
          <p>
            {{
              controlPlane.governance?.compatibilityMode
                ? compatibilitySummaryText
                : controlPlane.definition.model || "模型未锁定"
            }}
          </p>
        </article>
      </section>

      <section v-if="controlPlane.governance" class="governance-strip">
        <article class="governance-card">
          <span class="summary-label">发布追平</span>
          <strong>{{
            controlPlane.governance.isPublishedVersionLatest
              ? "已追平最新版本"
              : "当前发布落后最新版本"
          }}</strong>
          <p>
            发布 v{{ controlPlane.governance.publishedVersionNumber || 0 }} ·
            最新 v{{ controlPlane.governance.latestVersionNumber || 0 }}
          </p>
        </article>
        <article class="governance-card">
          <span class="summary-label">授权活跃度</span>
          <strong
            >{{ controlPlane.governance.enabledAuthorizationCount }} /
            {{ controlPlane.governance.authorizationCount }}</strong
          >
          <p>
            active host agent 之外还有
            {{
              controlPlane.governance.inactiveAuthorizationCount
            }}
            个待清理授权
          </p>
        </article>
        <article class="governance-card">
          <span class="summary-label">兼容收口</span>
          <strong>{{
            controlPlane.governance.compatibilityMode
              ? `${compatibilityDetails.length} 类压力`
              : "未启用"
          }}</strong>
          <p>{{ compatibilitySummaryText }}</p>
        </article>
        <article class="governance-card">
          <span class="summary-label">收口就绪</span>
          <strong>{{
            bridgeRemovalReadiness
              ? bridgeRemovalStatusLabel(bridgeRemovalReadiness.status)
              : "待评估"
          }}</strong>
          <p>
            {{
              bridgeRemovalReadiness?.summary ||
              "等待控制面生成最终收口 readiness。"
            }}
          </p>
        </article>
        <article class="governance-card">
          <span class="summary-label">回滚治理</span>
          <strong>{{
            controlPlane.governance.hasRollbackCandidate
              ? `${controlPlane.governance.rollbackCandidateCount} 个候选版本`
              : "暂无回滚候选"
          }}</strong>
          <p>
            {{
              effectivePublicationPreview
                ? publicationChangeLabel(effectivePublicationPreview.changeType)
                : "等待生成预演"
            }}
          </p>
        </article>
      </section>

      <div v-if="governanceWarnings.length > 0" class="governance-warning-list">
        <article
          v-for="warning in governanceWarnings"
          :key="warning.code"
          :class="[
            'governance-warning',
            `severity-${warning.severity || 'info'}`,
          ]"
        >
          <strong>{{ governanceSeverityLabel(warning.severity) }}</strong>
          <span>{{ warning.message }}</span>
        </article>
      </div>

      <div
        v-if="compatibilityDetails.length > 0"
        class="compatibility-detail-list"
      >
        <article
          v-for="detail in compatibilityDetails"
          :key="`${detail.kind}-${detail.referenceKey || detail.hostAgentDefinitionId || 'detail'}`"
          class="compatibility-detail-card"
        >
          <div class="compatibility-detail-head">
            <strong>{{ compatibilityDetailLabel(detail.kind) }}</strong>
            <span class="mini-badge"
              >{{ detail.activeAgentCount }} /
              {{ detail.impactedAgentCount }} active</span
            >
          </div>
          <p>{{ detail.summary }}</p>
          <p v-if="detail.hostAgentDefinitionId">
            宿主: {{ agentNameById(detail.hostAgentDefinitionId) }}
          </p>
          <p v-if="detail.referenceKey">依赖点: {{ detail.referenceKey }}</p>
          <div v-if="detail.agents?.length" class="preview-action-list">
            <span
              v-for="agent in detail.agents"
              :key="`${detail.kind}-${agent.agentDefinitionId}-${agent.authorizationId || 'binding'}`"
              class="mini-badge"
            >
              {{ agent.agentName || agent.agentDefinitionId }} ·
              {{ agent.agentStatus || "unknown" }}
            </span>
          </div>
        </article>
      </div>

      <div v-if="bridgeRemovalReadiness" class="migration-panel">
        <div class="migration-panel-head">
          <div>
            <strong>最终收口 Readiness</strong>
            <p>{{ bridgeRemovalReadiness.summary }}</p>
          </div>
          <span class="mini-badge">
            {{ bridgeRemovalStatusLabel(bridgeRemovalReadiness.status) }}
          </span>
        </div>
        <div class="detail-table preview-table">
          <div>
            <span>阻塞项</span
            ><strong>{{ bridgeRemovalReadiness.blockingIssueCount }}</strong>
          </div>
          <div>
            <span>待收尾</span
            ><strong>{{ bridgeRemovalReadiness.pendingIssueCount }}</strong>
          </div>
          <div>
            <span>已完成删桥</span
            ><strong>{{ bridgeRemovalReadiness.ready ? "是" : "否" }}</strong>
          </div>
          <div>
            <span>检查项</span
            ><strong>{{ bridgeRemovalReadiness.checklist?.length || 0 }}</strong>
          </div>
        </div>
        <div
          v-if="bridgeRemovalReadiness.recommendedActions?.length"
          class="preview-action-list"
        >
          <span
            v-for="(item, index) in bridgeRemovalReadiness.recommendedActions"
            :key="`bridge-removal-${item}-${index}`"
            class="mini-badge"
          >
            {{ item }}
          </span>
        </div>
        <div
          v-if="bridgeRemovalReadiness.checklist?.length"
          class="compatibility-detail-list"
        >
          <article
            v-for="item in bridgeRemovalReadiness.checklist"
            :key="item.key"
            class="compatibility-detail-card"
          >
            <div class="compatibility-detail-head">
              <strong>{{ item.label }}</strong>
              <span class="mini-badge">
                {{ bridgeRemovalStatusLabel(item.status) }}
              </span>
            </div>
            <p>{{ item.summary }}</p>
            <div v-if="item.recommendedActions?.length" class="preview-action-list">
              <span
                v-for="(action, index) in item.recommendedActions"
                :key="`${item.key}-${action}-${index}`"
                class="mini-badge"
              >
                {{ action }}
              </span>
            </div>
          </article>
        </div>
      </div>

      <div class="detail-grid">
        <div class="detail-panel">
          <h3>Publication</h3>
          <div
            v-if="effectivePublicationPreview"
            class="publication-preview-card"
          >
            <div class="publication-preview-head">
              <strong>{{
                publicationChangeLabel(effectivePublicationPreview.changeType)
              }}</strong>
              <span
                :class="[
                  'status-pill',
                  `status-${toneStatus(effectivePublicationPreview.riskLevel === 'high' ? 'disabled' : effectivePublicationPreview.riskLevel === 'medium' ? 'pending' : 'active')}`,
                ]"
              >
                {{
                  publicationRiskLabel(effectivePublicationPreview.riskLevel)
                }}
              </span>
            </div>
            <p>{{ effectivePublicationPreview.summary }}</p>
            <p
              v-if="effectivePublicationPreview.confirmationMessage"
              class="preview-confirmation-copy"
            >
              {{ effectivePublicationPreview.confirmationMessage }}
            </p>
            <div class="detail-table preview-table">
              <div>
                <span>当前版本</span
                ><strong>{{
                  effectivePublicationPreview.current?.versionNumber
                    ? `v${effectivePublicationPreview.current.versionNumber}`
                    : "未发布"
                }}</strong>
              </div>
              <div>
                <span>目标版本</span
                ><strong>{{
                  effectivePublicationPreview.target?.versionNumber
                    ? `v${effectivePublicationPreview.target.versionNumber}`
                    : "-"
                }}</strong>
              </div>
              <div>
                <span>启用授权</span
                ><strong>{{
                  effectivePublicationPreview.enabledAuthorizationCount
                }}</strong>
              </div>
              <div>
                <span>兼容模式</span
                ><strong>{{
                  effectivePublicationPreview.compatibilityMode ? "是" : "否"
                }}</strong>
              </div>
            </div>
            <div
              v-if="effectivePublicationPreview.recommendedActions?.length"
              class="preview-action-list"
            >
              <span
                v-for="(
                  item, index
                ) in effectivePublicationPreview.recommendedActions"
                :key="`${item}-${index}`"
                class="mini-badge"
              >
                {{ item }}
              </span>
            </div>
          </div>
          <div class="detail-table">
            <div>
              <span>Status</span
              ><strong>{{
                controlPlane.publication?.status || "未发布"
              }}</strong>
            </div>
            <div>
              <span>Version</span
              ><strong>{{
                controlPlane.publication?.versionNumber
                  ? `v${controlPlane.publication.versionNumber}`
                  : "-"
              }}</strong>
            </div>
            <div>
              <span>Scope</span
              ><strong>{{
                publicationScopeLabel(
                  controlPlane.publication?.publicationScope ||
                    controlPlane.definition.publicationScope,
                )
              }}</strong>
            </div>
            <div>
              <span>Authorizations</span
              ><strong>{{
                controlPlane.publication?.authorizationCount || 0
              }}</strong>
            </div>
          </div>

          <form class="stack-form" @submit.prevent="savePublication">
            <div class="field-row">
              <label class="field">
                <span>发布版本</span>
                <select v-model="publicationForm.versionId" class="input">
                  <option value="">请选择版本</option>
                  <option
                    v-for="version in controlPlane.versions"
                    :key="version.id"
                    :value="version.id"
                  >
                    v{{ version.versionNumber }} · {{ version.lifecycleStatus }}
                  </option>
                </select>
              </label>
              <label class="field">
                <span>Status</span>
                <select v-model="publicationForm.status" class="input">
                  <option value="active">active</option>
                  <option value="disabled">disabled</option>
                  <option value="archived">archived</option>
                </select>
              </label>
            </div>

            <label class="field">
              <span>Scope</span>
              <select v-model="publicationForm.publicationScope" class="input">
                <option value="tenant">tenant</option>
                <option value="system_global">system_global</option>
              </select>
            </label>

            <label class="field">
              <span>Publication Metadata JSON</span>
              <textarea
                v-model="publicationForm.metadataText"
                class="input textarea"
                rows="5"
              ></textarea>
            </label>

            <div class="governance-form-grid">
              <label class="field">
                <span>变更原因</span>
                <textarea
                  v-model="publicationForm.changeReason"
                  class="input textarea"
                  rows="3"
                  placeholder="高风险或影响现有授权时必填。"
                ></textarea>
              </label>
              <label class="field">
                <span>变更备注</span>
                <textarea
                  v-model="publicationForm.changeNotes"
                  class="input textarea"
                  rows="3"
                  placeholder="记录窗口、确认结论、关联问题单。"
                ></textarea>
              </label>
            </div>

            <label class="field">
              <span>回滚后恢复计划</span>
              <textarea
                v-model="publicationForm.rollbackRecoveryPlan"
                class="input textarea"
                rows="3"
                placeholder="回滚/归档时必填，其他场景建议说明后续补救动作。"
              ></textarea>
            </label>

            <label class="field">
              <span>治理 Metadata JSON</span>
              <textarea
                v-model="publicationForm.governanceMetadataText"
                class="input textarea"
                rows="4"
                placeholder='{"ticket":"OPS-123"}'
              ></textarea>
            </label>

            <div class="form-actions">
              <button
                type="submit"
                class="btn btn-primary"
                :disabled="busyAction === 'publication' || !isAdmin"
              >
                {{
                  busyAction === "publication"
                    ? "发布中..."
                    : "保存 Publication"
                }}
              </button>
            </div>
          </form>
        </div>

        <div class="detail-panel">
          <h3>测试运行台</h3>
          <form class="stack-form" @submit.prevent="createTestRun">
            <div class="field-row">
              <label class="field">
                <span>测试版本</span>
                <select v-model="testRunForm.versionId" class="input">
                  <option value="">默认当前发布或最新版本</option>
                  <option
                    v-for="version in controlPlane.versions"
                    :key="version.id"
                    :value="version.id"
                  >
                    v{{ version.versionNumber }} · {{ version.lifecycleStatus }}
                  </option>
                </select>
              </label>
              <label class="field">
                <span>Host Agent</span>
                <select v-model="testRunForm.agentDefinitionId" class="input">
                  <option value="">优先使用 definition 里的 host agent</option>
                  <option
                    v-for="agent in activeAgents"
                    :key="agent.id"
                    :value="agent.id"
                  >
                    {{ agent.name }}
                  </option>
                </select>
              </label>
            </div>

            <div class="field-row">
              <label class="field">
                <span>Session ID</span>
                <input
                  v-model="testRunForm.sessionId"
                  class="input"
                  placeholder="留空由后端自动处理"
                />
              </label>
              <label class="field checkbox-field">
                <input v-model="testRunForm.autoStart" type="checkbox" />
                <span>创建后立即启动</span>
              </label>
            </div>

            <label class="field">
              <span>Input JSON</span>
              <textarea
                v-model="testRunForm.inputText"
                class="input textarea"
                rows="7"
                placeholder='{"task":"请测试当前 capability 的典型输入"}'
              ></textarea>
            </label>

            <label class="field">
              <span>Metadata JSON</span>
              <textarea
                v-model="testRunForm.metadataText"
                class="input textarea"
                rows="5"
              ></textarea>
            </label>

            <div class="form-actions">
              <button
                type="submit"
                class="btn btn-primary"
                :disabled="busyAction === 'test-run' || !isAdmin"
              >
                {{ busyAction === "test-run" ? "创建中..." : "创建测试运行" }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <div class="detail-grid secondary-grid">
        <div class="detail-panel">
          <h3>新增版本</h3>
          <form class="stack-form" @submit.prevent="createVersion">
            <div class="field-row">
              <label class="field">
                <span>Lifecycle</span>
                <select v-model="versionForm.lifecycleStatus" class="input">
                  <option value="draft">draft</option>
                  <option value="review">review</option>
                  <option value="active">active</option>
                  <option value="disabled">disabled</option>
                </select>
              </label>
              <label class="field">
                <span>Model</span>
                <input
                  v-model="versionForm.model"
                  class="input"
                  placeholder="留空表示沿用默认"
                />
              </label>
            </div>

            <label class="field">
              <span>System Prompt</span>
              <textarea
                v-model="versionForm.systemPrompt"
                class="input textarea tall-textarea"
                rows="8"
              ></textarea>
            </label>

            <div class="field-row">
              <label class="field">
                <span>Publication Scope</span>
                <select v-model="versionForm.publicationScope" class="input">
                  <option value="tenant">tenant</option>
                  <option value="system_global">system_global</option>
                </select>
              </label>
              <label class="field">
                <span>Publication Status</span>
                <select v-model="versionForm.publicationStatus" class="input">
                  <option value="active">active</option>
                  <option value="disabled">disabled</option>
                  <option value="archived">archived</option>
                </select>
              </label>
            </div>

            <label class="field checkbox-field">
              <input v-model="versionForm.publish" type="checkbox" />
              <span>创建后立即发布为当前版本</span>
            </label>

            <details class="advanced-panel">
              <summary>版本 JSON 配置</summary>
              <div class="advanced-grid">
                <label class="field">
                  <span>Config JSON</span>
                  <textarea
                    v-model="versionForm.configText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Metadata JSON</span>
                  <textarea
                    v-model="versionForm.metadataText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Output Schema JSON</span>
                  <textarea
                    v-model="versionForm.outputSchemaText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Handoff Input Schema JSON</span>
                  <textarea
                    v-model="versionForm.handoffInputSchemaText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Tool Allowlist JSON</span>
                  <textarea
                    v-model="versionForm.toolAllowlistText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Skill Allowlist JSON</span>
                  <textarea
                    v-model="versionForm.skillAllowlistText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>MCP Allowlist JSON</span>
                  <textarea
                    v-model="versionForm.mcpAllowlistText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Knowledge Policy JSON</span>
                  <textarea
                    v-model="versionForm.knowledgePolicyText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Review Policy JSON</span>
                  <textarea
                    v-model="versionForm.reviewPolicyText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Runtime Policy JSON</span>
                  <textarea
                    v-model="versionForm.runtimePolicyText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
                <label class="field">
                  <span>Publication Metadata JSON</span>
                  <textarea
                    v-model="versionForm.publicationMetadataText"
                    class="input textarea"
                    rows="5"
                  ></textarea>
                </label>
              </div>
            </details>

            <div class="form-actions">
              <button
                type="submit"
                class="btn btn-primary"
                :disabled="busyAction === 'version' || !isAdmin"
              >
                {{ busyAction === "version" ? "创建中..." : "创建新版本" }}
              </button>
            </div>
          </form>
        </div>

        <div class="detail-panel">
          <h3>版本与授权</h3>

          <div v-if="controlPlane.versions.length === 0" class="mini-empty">
            当前还没有版本。
          </div>
          <div v-else class="version-list">
            <article
              v-for="version in controlPlane.versions"
              :key="version.id"
              class="version-card"
            >
              <div class="version-card-head">
                <div>
                  <strong>v{{ version.versionNumber }}</strong>
                  <span
                    >{{ version.lifecycleStatus }} ·
                    {{ version.model || "default model" }}</span
                  >
                </div>
                <span v-if="version.isPublished" class="mini-badge accent-badge"
                  >当前发布</span
                >
              </div>
              <p class="version-copy">
                {{ truncate(version.systemPrompt, 180) }}
              </p>
              <div class="version-card-meta">
                <span>{{
                  Object.keys(version.outputSchema || {}).length > 0
                    ? "含 output schema"
                    : "无 output schema"
                }}</span>
                <span>{{
                  Array.isArray(version.toolAllowlist)
                    ? `${version.toolAllowlist.length} tools`
                    : "0 tools"
                }}</span>
                <span>{{ formatTime(version.updatedAt) }}</span>
              </div>
              <div class="card-inline-actions">
                <button
                  type="button"
                  class="btn btn-secondary btn-inline"
                  @click="copyVersionIntoForm(version)"
                >
                  复制到新版本表单
                </button>
                <button
                  type="button"
                  class="btn btn-secondary btn-inline"
                  :disabled="busyAction === `publish-${version.id}` || !isAdmin"
                  @click="publishVersion(version)"
                >
                  {{
                    busyAction === `publish-${version.id}`
                      ? "发布中..."
                      : version.isPublished
                        ? "重新发布"
                        : "发布该版本"
                  }}
                </button>
              </div>
            </article>
          </div>

          <div class="authorization-section">
            <h4>Host Agent 授权</h4>
            <div
              v-if="controlPlane.authorizations.length === 0"
              class="mini-empty"
            >
              当前没有 agent 授权这个 capability。
            </div>
            <div v-else class="authorization-list">
              <router-link
                v-for="item in controlPlane.authorizations"
                :key="item.authorizationId"
                :to="{
                  name: 'AgentExtensions',
                  params: { id: item.agentDefinitionId },
                }"
                class="authorization-card"
              >
                <strong>{{ item.agentName || item.agentDefinitionId }}</strong>
                <span>{{ item.status }} · priority {{ item.priority }}</span>
                <small>{{ formatJSONCompact(item.budgetPolicy) }}</small>
              </router-link>
            </div>
          </div>

          <div class="authorization-section">
            <h4>发布治理历史</h4>
            <div v-if="controlPlane.events.length === 0" class="mini-empty">
              当前还没有 publication 治理历史。
            </div>
            <div v-else class="event-list">
              <article
                v-for="event in controlPlane.events"
                :key="event.id"
                class="event-card"
              >
                <div class="event-card-head">
                  <div>
                    <strong
                      >{{ publicationEventStageLabel(event.eventStage) }} ·
                      {{ publicationChangeLabel(event.changeType) }}</strong
                    >
                    <span>{{ formatTime(event.createdAt) }}</span>
                  </div>
                  <span
                    :class="[
                      'status-pill',
                      `status-${toneStatus(event.riskLevel === 'high' ? 'disabled' : event.riskLevel === 'medium' ? 'pending' : 'active')}`,
                    ]"
                  >
                    {{ publicationRiskLabel(event.riskLevel) }}
                  </span>
                </div>
                <p class="version-copy">{{ event.summary || "无摘要" }}</p>
                <div class="event-meta-grid">
                  <span
                    >版本
                    {{
                      event.previousVersionNumber
                        ? `v${event.previousVersionNumber}`
                        : "-"
                    }}
                    ->
                    {{
                      event.versionNumber ? `v${event.versionNumber}` : "-"
                    }}</span
                  >
                  <span
                    >授权 {{ event.enabledAuthorizationCount }} /
                    {{ event.impactedAuthorizationCount }}</span
                  >
                  <span>{{
                    event.actorUserEmail || event.actorUserId || "系统"
                  }}</span>
                  <span>{{ event.confirmed ? "已确认" : "未确认" }}</span>
                </div>
                <p v-if="event.changeReason" class="event-copy">
                  <strong>原因：</strong>{{ event.changeReason }}
                </p>
                <p v-if="event.changeNotes" class="event-copy">
                  <strong>备注：</strong>{{ event.changeNotes }}
                </p>
                <p v-if="event.rollbackRecoveryPlan" class="event-copy">
                  <strong>恢复计划：</strong>{{ event.rollbackRecoveryPlan }}
                </p>
                <div
                  v-if="event.recommendedActions?.length"
                  class="preview-action-list"
                >
                  <span
                    v-for="(item, index) in event.recommendedActions"
                    :key="`${event.id}-${item}-${index}`"
                    class="mini-badge"
                  >
                    {{ item }}
                  </span>
                </div>
              </article>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { agentsAPI, subagentsAPI } from "@/api";
import { useAuthStore } from "@/store/auth";
import { useToastStore } from "@/store/toast";
import { parseJSON } from "@/utils/agentArtifacts";
import {
  bridgeRemovalStatusLabel,
  compatibilityDetailLabel,
  normalizeMetadataAliasFreezePreview,
  normalizeSubagentPublicationEvent,
  normalizeSubagentGovernance,
  normalizeSubagentTenantGovernanceSummary,
  normalizeSubagentPublicationPreview,
  publicationEventStageLabel,
  publicationChangeLabel,
  publicationRiskLabel,
} from "@/utils/subagentGovernance";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const toastStore = useToastStore();

const loadingList = ref(false);
const loadingDetail = ref(false);
const loadingGovernance = ref(false);
const savingDefinition = ref(false);
const busyAction = ref("");
const errorMessage = ref("");
const includeArchived = ref(false);
const subagents = ref([]);
const agents = ref([]);
const selectedDefinitionId = ref("");
const editingDefinitionId = ref("");
const publicationPreview = ref(null);
const tenantGovernanceSummary = ref(null);
const tenantGovernanceEvents = ref([]);
const tenantGovernanceTotal = ref(0);
const metadataAliasFreezePreview = ref(null);

const tenantGovernanceFilters = reactive({
  definitionId: "",
  actionType: "",
  eventStage: "",
  riskLevel: "",
  compatibilityMode: "",
  limit: 10,
  offset: 0,
});

const metadataAliasFreezeForm = reactive({
  scope: "tenant",
});

const controlPlane = reactive({
  definition: null,
  versions: [],
  publication: null,
  authorizations: [],
  events: [],
  governance: null,
});

const definitionForm = reactive({
  name: "",
  slug: "",
  description: "",
  systemPrompt: "",
  model: "",
  status: "active",
  definitionStatus: "active",
  lifecycleStatus: "active",
  publicationScope: "tenant",
  hostAgentDefinitionId: "",
  handoffPrompt: "",
  configText: "{}",
  metadataText: "{}",
  outputSchemaText: "{}",
  handoffInputSchemaText: "{}",
  toolAllowlistText: "[]",
  skillAllowlistText: "[]",
  mcpAllowlistText: "[]",
  knowledgePolicyText: "{}",
  reviewPolicyText: "{}",
  runtimePolicyText: "{}",
  publicationMetadataText: "{}",
});

const versionForm = reactive({
  lifecycleStatus: "draft",
  systemPrompt: "",
  model: "",
  publish: true,
  publicationScope: "tenant",
  publicationStatus: "active",
  configText: "{}",
  metadataText: "{}",
  outputSchemaText: "{}",
  handoffInputSchemaText: "{}",
  toolAllowlistText: "[]",
  skillAllowlistText: "[]",
  mcpAllowlistText: "[]",
  knowledgePolicyText: "{}",
  reviewPolicyText: "{}",
  runtimePolicyText: "{}",
  publicationMetadataText: "{}",
});

const publicationForm = reactive({
  versionId: "",
  publicationScope: "tenant",
  status: "active",
  metadataText: "{}",
  changeReason: "",
  changeNotes: "",
  rollbackRecoveryPlan: "",
  governanceMetadataText: "{}",
});

const testRunForm = reactive({
  versionId: "",
  agentDefinitionId: "",
  sessionId: "",
  inputText: '{\n  "task": "请测试当前 capability 的典型输入"\n}',
  metadataText: "{}",
  autoStart: true,
});

const isAdmin = computed(
  () =>
    String(authStore.user?.role || "")
      .trim()
      .toLowerCase() === "admin",
);
const activeAgents = computed(() =>
  agents.value.filter((item) => item.status === "active"),
);
const enabledAuthorizationCount = computed(
  () =>
    controlPlane.authorizations.filter((item) => item.status === "enabled")
      .length,
);
const latestVersionLabel = computed(() =>
  controlPlane.versions[0]?.versionNumber
    ? `v${controlPlane.versions[0].versionNumber}`
    : "暂无版本",
);
const governanceWarnings = computed(() =>
  Array.isArray(controlPlane.governance?.warnings)
    ? controlPlane.governance.warnings
    : [],
);
const effectivePublicationPreview = computed(
  () =>
    publicationPreview.value ||
    controlPlane.governance?.nextPublicationPreview ||
    null,
);
const compatibilityDetails = computed(() =>
  Array.isArray(controlPlane.governance?.compatibilityDetails)
    ? controlPlane.governance.compatibilityDetails
    : [],
);
const bridgeRemovalReadiness = computed(
  () => controlPlane.governance?.bridgeRemovalReadiness || null,
);
const effectiveMetadataAliasFreezePreview = computed(() => {
  if (metadataAliasFreezeForm.scope === "selection") {
    return (
      controlPlane.governance?.metadataAliasFreezePreview ||
      metadataAliasFreezePreview.value ||
      null
    );
  }
  return metadataAliasFreezePreview.value;
});
const tenantGovernancePage = computed(
  () =>
    Math.floor(tenantGovernanceFilters.offset / tenantGovernanceFilters.limit) +
    1,
);
const tenantGovernanceTotalPages = computed(() =>
  Math.max(
    1,
    Math.ceil(tenantGovernanceTotal.value / tenantGovernanceFilters.limit),
  ),
);
const tenantTopChangeType = computed(() => {
  const entries = Object.entries(
    tenantGovernanceSummary.value?.changeTypeCounts || {},
  );
  if (entries.length === 0) return "暂无事件趋势";
  const [name, count] = entries.sort((left, right) => right[1] - left[1])[0];
  return `${publicationChangeLabel(name)} ${count} 条`;
});
const compatibilitySummaryText = computed(() => {
  if (bridgeRemovalReadiness.value?.ready) {
    return "metadata alias、发布与授权状态已收口，可进入最终验证";
  }
  if (!controlPlane.governance?.compatibilityMode) return "未发现兼容依赖";
  return "仍有遗留 metadata alias 需要冻结";
});

const normalizeAgent = (raw = {}) => ({
  id: raw.id,
  name: raw.name || raw.id || "未命名 agent",
  status: raw.status || "active",
});

const normalizeSubagent = (raw = {}) => ({
  id: raw.publication_id || raw.publicationId || raw.id || "",
  definitionId: raw.id || raw.definition_id || raw.definitionId || "",
  publicationId: raw.publication_id || raw.publicationId || "",
  versionId: raw.version_id || raw.versionId || "",
  versionNumber: Number(raw.version_number || raw.versionNumber || 0),
  name: raw.name || "未命名专家能力",
  slug: raw.slug || "",
  description: raw.description || "",
  systemPrompt: raw.system_prompt || raw.systemPrompt || "",
  model: raw.model || "",
  status: raw.status || "active",
  definitionStatus: raw.definition_status || raw.definitionStatus || "active",
  lifecycleStatus: raw.lifecycle_status || raw.lifecycleStatus || "active",
  publicationScope: raw.publication_scope || raw.publicationScope || "tenant",
  publicationTenantId:
    raw.publication_tenant_id || raw.publicationTenantId || "",
  config: parseJSON(raw.config, {}),
  metadata: parseJSON(raw.metadata, {}),
  outputSchema: parseJSON(raw.output_schema || raw.outputSchema, {}),
  handoffInputSchema: parseJSON(
    raw.handoff_input_schema || raw.handoffInputSchema,
    {},
  ),
  toolAllowlist: parseJSON(raw.tool_allowlist || raw.toolAllowlist, []),
  skillAllowlist: parseJSON(raw.skill_allowlist || raw.skillAllowlist, []),
  mcpAllowlist: parseJSON(raw.mcp_allowlist || raw.mcpAllowlist, []),
  knowledgePolicy: parseJSON(raw.knowledge_policy || raw.knowledgePolicy, {}),
  reviewPolicy: parseJSON(raw.review_policy || raw.reviewPolicy, {}),
  runtimePolicy: parseJSON(raw.runtime_policy || raw.runtimePolicy, {}),
  publicationMetadata: parseJSON(
    raw.publication_metadata || raw.publicationMetadata,
    {},
  ),
  hostAgentDefinitionId:
    raw.host_agent_definition_id || raw.hostAgentDefinitionId || "",
  handoffPrompt: raw.handoff_prompt || raw.handoffPrompt || "",
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
});

const normalizeVersion = (raw = {}) => ({
  id: raw.id,
  definitionId: raw.subagent_definition_id || raw.definitionId || "",
  versionNumber: Number(raw.version_number || raw.versionNumber || 0),
  lifecycleStatus: raw.lifecycle_status || raw.lifecycleStatus || "draft",
  systemPrompt: raw.system_prompt || raw.systemPrompt || "",
  model: raw.model || "",
  config: parseJSON(raw.config, {}),
  metadata: parseJSON(raw.metadata, {}),
  outputSchema: parseJSON(raw.output_schema || raw.outputSchema, {}),
  handoffInputSchema: parseJSON(
    raw.handoff_input_schema || raw.handoffInputSchema,
    {},
  ),
  toolAllowlist: parseJSON(raw.tool_allowlist || raw.toolAllowlist, []),
  skillAllowlist: parseJSON(raw.skill_allowlist || raw.skillAllowlist, []),
  mcpAllowlist: parseJSON(raw.mcp_allowlist || raw.mcpAllowlist, []),
  knowledgePolicy: parseJSON(raw.knowledge_policy || raw.knowledgePolicy, {}),
  reviewPolicy: parseJSON(raw.review_policy || raw.reviewPolicy, {}),
  runtimePolicy: parseJSON(raw.runtime_policy || raw.runtimePolicy, {}),
  publicationId: raw.publication_id || raw.publicationId || "",
  publicationStatus: raw.publication_status || raw.publicationStatus || "",
  publicationScope: raw.publication_scope || raw.publicationScope || "",
  isPublished: Boolean(raw.is_published || raw.isPublished),
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
});

const normalizePublication = (raw = {}) => ({
  id: raw.id || "",
  definitionId: raw.subagent_definition_id || raw.definitionId || "",
  versionId: raw.version_id || raw.versionId || "",
  versionNumber: Number(raw.version_number || raw.versionNumber || 0),
  tenantId: raw.tenant_id || raw.tenantId || "",
  publicationScope: raw.publication_scope || raw.publicationScope || "tenant",
  status: raw.status || "active",
  metadata: parseJSON(raw.metadata, {}),
  authorizationCount: Number(
    raw.authorization_count || raw.authorizationCount || 0,
  ),
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
});

const normalizeAuthorization = (raw = {}) => ({
  authorizationId: raw.authorization_id || raw.authorizationId || "",
  publicationId: raw.publication_id || raw.publicationId || "",
  status: raw.status || "disabled",
  priority: Number(raw.priority || 0),
  agentDefinitionId: raw.agent_definition_id || raw.agentDefinitionId || "",
  agentName: raw.agent_name || raw.agentName || "",
  agentStatus: raw.agent_status || raw.agentStatus || "",
  budgetPolicy: parseJSON(raw.budget_policy || raw.budgetPolicy, {}),
  metadata: parseJSON(raw.metadata, {}),
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null,
});

const applyControlPlane = (raw = {}) => {
  controlPlane.definition = raw.definition
    ? normalizeSubagent(raw.definition)
    : null;
  controlPlane.versions = Array.isArray(raw.versions)
    ? raw.versions.map(normalizeVersion)
    : [];
  controlPlane.publication = raw.publication
    ? normalizePublication(raw.publication)
    : null;
  controlPlane.authorizations = Array.isArray(raw.authorizations)
    ? raw.authorizations.map(normalizeAuthorization)
    : [];
  controlPlane.events = Array.isArray(raw.events)
    ? raw.events.map(normalizeSubagentPublicationEvent).filter(Boolean)
    : [];
  controlPlane.governance = normalizeSubagentGovernance(raw.governance);
};

const buildTenantGovernanceParams = () => ({
  definition_id: tenantGovernanceFilters.definitionId || undefined,
  action_type: tenantGovernanceFilters.actionType || undefined,
  event_stage: tenantGovernanceFilters.eventStage || undefined,
  risk_level: tenantGovernanceFilters.riskLevel || undefined,
  compatibility_mode: tenantGovernanceFilters.compatibilityMode || undefined,
  limit: tenantGovernanceFilters.limit,
  offset: tenantGovernanceFilters.offset,
});

const buildMetadataAliasFreezePayload = (previewOnly = false) => ({
  scope: metadataAliasFreezeForm.scope,
  definition_ids:
    metadataAliasFreezeForm.scope === "selection" && selectedDefinitionId.value
      ? [selectedDefinitionId.value]
      : undefined,
  preview_only: previewOnly,
});

const parseJSONField = (raw, fallback, fieldLabel) => {
  const text = String(raw || "").trim();
  if (!text) {
    return fallback;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${fieldLabel} 不是合法 JSON`);
  }
};

const formatJSON = (value) => JSON.stringify(value ?? {}, null, 2);
const formatJSONCompact = (value) => JSON.stringify(value ?? {});

const truncate = (value, length = 120) => {
  const text = String(value || "").trim();
  if (!text) return "暂无 system prompt";
  return text.length > length ? `${text.slice(0, length)}...` : text;
};

const formatTime = (value) => {
  if (!value) return "未更新";
  return new Date(value).toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const toneStatus = (status) => {
  const value = String(status || "")
    .trim()
    .toLowerCase();
  if (value === "active" || value === "enabled") return "good";
  if (value === "archived") return "muted";
  return "warn";
};

const publicationScopeLabel = (scope) =>
  String(scope || "").trim() === "system_global" ? "系统发布" : "租户发布";
const governanceSeverityLabel = (severity) =>
  ({
    warning: "警告",
    error: "风险",
    info: "提示",
  })[
    String(severity || "")
      .trim()
      .toLowerCase()
  ] || "提示";

const agentNameById = (agentId) => {
  if (!agentId) return "未指定";
  return agents.value.find((item) => item.id === agentId)?.name || agentId;
};

const syncRouteSubagent = async (definitionId = "") => {
  const nextQuery = { ...route.query };
  if (definitionId) {
    nextQuery.subagent = definitionId;
  } else {
    delete nextQuery.subagent;
  }
  if (nextQuery.subagent === route.query.subagent) return;
  await router.replace({ name: "SubagentManage", query: nextQuery });
};

const mergeDefinitionMetadata = () => {
  const metadata = parseJSONField(
    definitionForm.metadataText,
    {},
    "Metadata JSON",
  );
  if (definitionForm.slug.trim()) {
    metadata.slug = definitionForm.slug.trim();
  } else {
    delete metadata.slug;
  }
  delete metadata.host_agent_definition_id;
  delete metadata.target_agent_definition_id;
  delete metadata.agent_definition_id;
  delete metadata.handoff_prompt;
  return metadata;
};

const buildDefinitionPayload = () => ({
  name: definitionForm.name.trim(),
  slug: definitionForm.slug.trim(),
  description: definitionForm.description.trim(),
  system_prompt: definitionForm.systemPrompt,
  model: definitionForm.model.trim(),
  host_agent_definition_id: definitionForm.hostAgentDefinitionId.trim(),
  handoff_prompt: definitionForm.handoffPrompt.trim(),
  status: definitionForm.status,
  definition_status: definitionForm.definitionStatus,
  lifecycle_status: definitionForm.lifecycleStatus,
  publication_scope: definitionForm.publicationScope,
  config: parseJSONField(definitionForm.configText, {}, "Config JSON"),
  metadata: mergeDefinitionMetadata(),
  output_schema: parseJSONField(
    definitionForm.outputSchemaText,
    {},
    "Output Schema JSON",
  ),
  handoff_input_schema: parseJSONField(
    definitionForm.handoffInputSchemaText,
    {},
    "Handoff Input Schema JSON",
  ),
  tool_allowlist: parseJSONField(
    definitionForm.toolAllowlistText,
    [],
    "Tool Allowlist JSON",
  ),
  skill_allowlist: parseJSONField(
    definitionForm.skillAllowlistText,
    [],
    "Skill Allowlist JSON",
  ),
  mcp_allowlist: parseJSONField(
    definitionForm.mcpAllowlistText,
    [],
    "MCP Allowlist JSON",
  ),
  knowledge_policy: parseJSONField(
    definitionForm.knowledgePolicyText,
    {},
    "Knowledge Policy JSON",
  ),
  review_policy: parseJSONField(
    definitionForm.reviewPolicyText,
    {},
    "Review Policy JSON",
  ),
  runtime_policy: parseJSONField(
    definitionForm.runtimePolicyText,
    {},
    "Runtime Policy JSON",
  ),
  publication_metadata: parseJSONField(
    definitionForm.publicationMetadataText,
    {},
    "Publication Metadata JSON",
  ),
});

const buildVersionPayload = () => ({
  lifecycle_status: versionForm.lifecycleStatus,
  system_prompt: versionForm.systemPrompt,
  model: versionForm.model.trim(),
  config: parseJSONField(versionForm.configText, {}, "Version Config JSON"),
  metadata: parseJSONField(
    versionForm.metadataText,
    {},
    "Version Metadata JSON",
  ),
  output_schema: parseJSONField(
    versionForm.outputSchemaText,
    {},
    "Version Output Schema JSON",
  ),
  handoff_input_schema: parseJSONField(
    versionForm.handoffInputSchemaText,
    {},
    "Version Handoff Input Schema JSON",
  ),
  tool_allowlist: parseJSONField(
    versionForm.toolAllowlistText,
    [],
    "Version Tool Allowlist JSON",
  ),
  skill_allowlist: parseJSONField(
    versionForm.skillAllowlistText,
    [],
    "Version Skill Allowlist JSON",
  ),
  mcp_allowlist: parseJSONField(
    versionForm.mcpAllowlistText,
    [],
    "Version MCP Allowlist JSON",
  ),
  knowledge_policy: parseJSONField(
    versionForm.knowledgePolicyText,
    {},
    "Version Knowledge Policy JSON",
  ),
  review_policy: parseJSONField(
    versionForm.reviewPolicyText,
    {},
    "Version Review Policy JSON",
  ),
  runtime_policy: parseJSONField(
    versionForm.runtimePolicyText,
    {},
    "Version Runtime Policy JSON",
  ),
  publish: Boolean(versionForm.publish),
  publication_scope: versionForm.publicationScope,
  publication_status: versionForm.publicationStatus,
  publication_metadata: parseJSONField(
    versionForm.publicationMetadataText,
    {},
    "Version Publication Metadata JSON",
  ),
});

const resetDefinitionForm = () => {
  editingDefinitionId.value = "";
  definitionForm.name = "";
  definitionForm.slug = "";
  definitionForm.description = "";
  definitionForm.systemPrompt = "";
  definitionForm.model = "";
  definitionForm.status = "active";
  definitionForm.definitionStatus = "active";
  definitionForm.lifecycleStatus = "active";
  definitionForm.publicationScope = "tenant";
  definitionForm.hostAgentDefinitionId = "";
  definitionForm.handoffPrompt = "";
  definitionForm.configText = "{}";
  definitionForm.metadataText = "{}";
  definitionForm.outputSchemaText = "{}";
  definitionForm.handoffInputSchemaText = "{}";
  definitionForm.toolAllowlistText = "[]";
  definitionForm.skillAllowlistText = "[]";
  definitionForm.mcpAllowlistText = "[]";
  definitionForm.knowledgePolicyText = "{}";
  definitionForm.reviewPolicyText = "{}";
  definitionForm.runtimePolicyText = "{}";
  definitionForm.publicationMetadataText = "{}";
};

const resetVersionForm = () => {
  versionForm.lifecycleStatus = "draft";
  versionForm.systemPrompt = "";
  versionForm.model = "";
  versionForm.publish = true;
  versionForm.publicationScope = "tenant";
  versionForm.publicationStatus = "active";
  versionForm.configText = "{}";
  versionForm.metadataText = "{}";
  versionForm.outputSchemaText = "{}";
  versionForm.handoffInputSchemaText = "{}";
  versionForm.toolAllowlistText = "[]";
  versionForm.skillAllowlistText = "[]";
  versionForm.mcpAllowlistText = "[]";
  versionForm.knowledgePolicyText = "{}";
  versionForm.reviewPolicyText = "{}";
  versionForm.runtimePolicyText = "{}";
  versionForm.publicationMetadataText = "{}";
};

const fillDefinitionForm = (definition) => {
  if (!definition) {
    resetDefinitionForm();
    return;
  }
  editingDefinitionId.value = definition.definitionId;
  definitionForm.name = definition.name || "";
  definitionForm.slug = definition.slug || "";
  definitionForm.description = definition.description || "";
  definitionForm.systemPrompt = definition.systemPrompt || "";
  definitionForm.model = definition.model || "";
  definitionForm.status = definition.status || "active";
  definitionForm.definitionStatus = definition.definitionStatus || "active";
  definitionForm.lifecycleStatus = definition.lifecycleStatus || "active";
  definitionForm.publicationScope = definition.publicationScope || "tenant";
  definitionForm.hostAgentDefinitionId = definition.hostAgentDefinitionId || "";
  definitionForm.handoffPrompt = definition.handoffPrompt || "";
  definitionForm.configText = formatJSON(definition.config || {});
  const metadata = { ...(definition.metadata || {}) };
  delete metadata.slug;
  delete metadata.host_agent_definition_id;
  delete metadata.target_agent_definition_id;
  delete metadata.agent_definition_id;
  delete metadata.handoff_prompt;
  definitionForm.metadataText = formatJSON(metadata);
  definitionForm.outputSchemaText = formatJSON(definition.outputSchema || {});
  definitionForm.handoffInputSchemaText = formatJSON(
    definition.handoffInputSchema || {},
  );
  definitionForm.toolAllowlistText = formatJSON(definition.toolAllowlist || []);
  definitionForm.skillAllowlistText = formatJSON(
    definition.skillAllowlist || [],
  );
  definitionForm.mcpAllowlistText = formatJSON(definition.mcpAllowlist || []);
  definitionForm.knowledgePolicyText = formatJSON(
    definition.knowledgePolicy || {},
  );
  definitionForm.reviewPolicyText = formatJSON(definition.reviewPolicy || {});
  definitionForm.runtimePolicyText = formatJSON(definition.runtimePolicy || {});
  definitionForm.publicationMetadataText = formatJSON(
    definition.publicationMetadata || {},
  );
};

const fillPublicationForm = () => {
  publicationForm.versionId =
    controlPlane.publication?.versionId || controlPlane.versions[0]?.id || "";
  publicationForm.publicationScope =
    controlPlane.publication?.publicationScope ||
    controlPlane.definition?.publicationScope ||
    "tenant";
  publicationForm.status =
    controlPlane.publication?.status ||
    controlPlane.definition?.status ||
    "active";
  publicationForm.metadataText = formatJSON(
    controlPlane.publication?.metadata ||
      controlPlane.definition?.publicationMetadata ||
      {},
  );
  publicationForm.changeReason = "";
  publicationForm.changeNotes = "";
  publicationForm.rollbackRecoveryPlan = "";
  publicationForm.governanceMetadataText = "{}";
  publicationPreview.value = null;
};

const seedVersionFormFromDefinition = () => {
  const definition = controlPlane.definition;
  if (!definition) {
    resetVersionForm();
    return;
  }
  versionForm.lifecycleStatus = definition.lifecycleStatus || "draft";
  versionForm.systemPrompt = definition.systemPrompt || "";
  versionForm.model = definition.model || "";
  versionForm.publish = true;
  versionForm.publicationScope =
    controlPlane.publication?.publicationScope ||
    definition.publicationScope ||
    "tenant";
  versionForm.publicationStatus =
    controlPlane.publication?.status || definition.status || "active";
  versionForm.configText = formatJSON(definition.config || {});
  versionForm.metadataText = formatJSON(definition.metadata || {});
  versionForm.outputSchemaText = formatJSON(definition.outputSchema || {});
  versionForm.handoffInputSchemaText = formatJSON(
    definition.handoffInputSchema || {},
  );
  versionForm.toolAllowlistText = formatJSON(definition.toolAllowlist || []);
  versionForm.skillAllowlistText = formatJSON(definition.skillAllowlist || []);
  versionForm.mcpAllowlistText = formatJSON(definition.mcpAllowlist || []);
  versionForm.knowledgePolicyText = formatJSON(
    definition.knowledgePolicy || {},
  );
  versionForm.reviewPolicyText = formatJSON(definition.reviewPolicy || {});
  versionForm.runtimePolicyText = formatJSON(definition.runtimePolicy || {});
  versionForm.publicationMetadataText = formatJSON(
    controlPlane.publication?.metadata || definition.publicationMetadata || {},
  );
};

const copyVersionIntoForm = (version) => {
  if (!version) return;
  versionForm.lifecycleStatus = version.lifecycleStatus || "draft";
  versionForm.systemPrompt = version.systemPrompt || "";
  versionForm.model = version.model || "";
  versionForm.publish = false;
  versionForm.publicationScope =
    version.publicationScope ||
    controlPlane.publication?.publicationScope ||
    "tenant";
  versionForm.publicationStatus =
    version.publicationStatus || controlPlane.publication?.status || "active";
  versionForm.configText = formatJSON(version.config || {});
  versionForm.metadataText = formatJSON(version.metadata || {});
  versionForm.outputSchemaText = formatJSON(version.outputSchema || {});
  versionForm.handoffInputSchemaText = formatJSON(
    version.handoffInputSchema || {},
  );
  versionForm.toolAllowlistText = formatJSON(version.toolAllowlist || []);
  versionForm.skillAllowlistText = formatJSON(version.skillAllowlist || []);
  versionForm.mcpAllowlistText = formatJSON(version.mcpAllowlist || []);
  versionForm.knowledgePolicyText = formatJSON(version.knowledgePolicy || {});
  versionForm.reviewPolicyText = formatJSON(version.reviewPolicy || {});
  versionForm.runtimePolicyText = formatJSON(version.runtimePolicy || {});
  versionForm.publicationMetadataText = formatJSON(
    controlPlane.publication?.metadata || {},
  );
};

const fillTestRunForm = () => {
  testRunForm.versionId =
    controlPlane.publication?.versionId || controlPlane.versions[0]?.id || "";
  testRunForm.agentDefinitionId =
    controlPlane.definition?.hostAgentDefinitionId || "";
  testRunForm.sessionId = "";
  testRunForm.metadataText = "{}";
  testRunForm.autoStart = true;
};

const openCreate = () => {
  selectedDefinitionId.value = "";
  applyControlPlane({});
  resetDefinitionForm();
  resetVersionForm();
  seedVersionFormFromDefinition();
  fillPublicationForm();
  fillTestRunForm();
  void syncRouteSubagent("");
};

const loadAgents = async () => {
  try {
    const { data } = await agentsAPI.listAgents(true);
    agents.value = (data.agents || []).map(normalizeAgent);
  } catch (error) {
    console.error("Failed to load agents:", error);
  }
};

const loadSubagents = async () => {
  loadingList.value = true;
  errorMessage.value = "";
  try {
    const { data } = await subagentsAPI.listSubagents(includeArchived.value);
    subagents.value = (data.subagents || []).map(normalizeSubagent);
    if (!subagents.value.length) {
      if (!editingDefinitionId.value) {
        openCreate();
      }
      return;
    }

    const routeDefinitionId = String(route.query.subagent || "").trim();
    const nextDefinitionId =
      routeDefinitionId ||
      selectedDefinitionId.value ||
      editingDefinitionId.value ||
      subagents.value[0]?.definitionId ||
      "";

    if (nextDefinitionId) {
      await selectSubagent(nextDefinitionId);
    }
  } catch (error) {
    console.error("Failed to load subagents:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "加载专家能力失败";
  } finally {
    loadingList.value = false;
  }
};

const loadTenantGovernance = async () => {
  loadingGovernance.value = true;
  try {
    if (tenantGovernanceFilters.offset < 0) {
      tenantGovernanceFilters.offset = 0;
    }
    const { data } = await subagentsAPI.getGovernance(
      buildTenantGovernanceParams(),
    );
    tenantGovernanceSummary.value = normalizeSubagentTenantGovernanceSummary(
      data.summary,
    );
    tenantGovernanceEvents.value = Array.isArray(data.events)
      ? data.events.map(normalizeSubagentPublicationEvent).filter(Boolean)
      : [];
    tenantGovernanceTotal.value = Number(data.total || 0);
    if (
      tenantGovernanceFilters.offset >= tenantGovernanceTotal.value &&
      tenantGovernanceTotal.value > 0
    ) {
      tenantGovernanceFilters.offset = Math.max(
        0,
        (tenantGovernanceTotalPages.value - 1) * tenantGovernanceFilters.limit,
      );
      await loadTenantGovernance();
    }
  } catch (error) {
    console.error("Failed to load tenant subagent governance:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "加载 tenant 治理视图失败";
  } finally {
    loadingGovernance.value = false;
  }
};

const loadMetadataAliasFreezePreview = async () => {
  try {
    const { data } = await subagentsAPI.previewMetadataAliasFreeze(
      buildMetadataAliasFreezePayload(true),
    );
    metadataAliasFreezePreview.value = normalizeMetadataAliasFreezePreview(
      data?.metadata_alias_freeze_preview || data?.metadataAliasFreezePreview,
    );
  } catch (error) {
    console.error("Failed to preview metadata alias freeze:", error);
    metadataAliasFreezePreview.value = null;
  }
};

const resetTenantGovernancePageAndLoad = async () => {
  tenantGovernanceFilters.offset = 0;
  await loadTenantGovernance();
};

const changeTenantGovernancePage = async (delta) => {
  const nextPage = tenantGovernancePage.value + delta;
  if (nextPage < 1) return;
  tenantGovernanceFilters.offset =
    (nextPage - 1) * tenantGovernanceFilters.limit;
  await loadTenantGovernance();
};

const loadControlPlane = async (definitionId) => {
  if (!definitionId) return;
  loadingDetail.value = true;
  errorMessage.value = "";
  try {
    const { data } = await subagentsAPI.getControlPlane(definitionId);
    applyControlPlane(data);
    fillDefinitionForm(controlPlane.definition);
    fillPublicationForm();
    publicationPreview.value = normalizeSubagentPublicationPreview(
      data?.governance?.next_publication_preview ||
        data?.governance?.nextPublicationPreview,
    );
    seedVersionFormFromDefinition();
    fillTestRunForm();
  } catch (error) {
    console.error("Failed to load control plane:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "加载 control plane 失败";
  } finally {
    loadingDetail.value = false;
  }
};

const selectSubagent = async (definitionId) => {
  if (!definitionId) return;
  selectedDefinitionId.value = definitionId;
  editingDefinitionId.value = definitionId;
  await syncRouteSubagent(definitionId);
  await loadControlPlane(definitionId);
};

const saveDefinition = async () => {
  if (!definitionForm.name.trim()) {
    toastStore.showToast({
      type: "error",
      message: "请先填写 capability 名称",
    });
    return;
  }

  savingDefinition.value = true;
  errorMessage.value = "";
  try {
    const isUpdate = Boolean(editingDefinitionId.value);
    const payload = buildDefinitionPayload();
    const response = editingDefinitionId.value
      ? await subagentsAPI.updateSubagent(editingDefinitionId.value, payload)
      : await subagentsAPI.createSubagent(payload);
    const saved = normalizeSubagent(response.data);
    selectedDefinitionId.value = saved.definitionId;
    editingDefinitionId.value = saved.definitionId;
    toastStore.showToast({
      type: "success",
      message: isUpdate ? "Definition 已保存" : "Definition 已创建",
    });
    await loadSubagents();
    await selectSubagent(saved.definitionId);
  } catch (error) {
    console.error("Failed to save subagent definition:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "保存 definition 失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    savingDefinition.value = false;
  }
};

const deleteDefinition = async () => {
  if (!editingDefinitionId.value) return;
  const confirmed = window.confirm(
    `确认删除专家能力“${definitionForm.name || editingDefinitionId.value}”吗？`,
  );
  if (!confirmed) return;

  busyAction.value = "delete";
  errorMessage.value = "";
  try {
    await subagentsAPI.deleteSubagent(editingDefinitionId.value);
    toastStore.showToast({ type: "success", message: "专家能力已删除" });
    selectedDefinitionId.value = "";
    resetDefinitionForm();
    applyControlPlane({});
    await loadSubagents();
  } catch (error) {
    console.error("Failed to delete subagent definition:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "删除专家能力失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const createVersion = async () => {
  if (!selectedDefinitionId.value) {
    toastStore.showToast({ type: "error", message: "请先选择一个专家能力" });
    return;
  }
  busyAction.value = "version";
  errorMessage.value = "";
  try {
    await subagentsAPI.createSubagentVersion(
      selectedDefinitionId.value,
      buildVersionPayload(),
    );
    toastStore.showToast({ type: "success", message: "新版本已创建" });
    await loadControlPlane(selectedDefinitionId.value);
  } catch (error) {
    console.error("Failed to create subagent version:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "创建版本失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const updatePublicationWithPreview = async (payload, cancelMessage) => {
  const previewResponse = await subagentsAPI.previewSubagentPublication(
    selectedDefinitionId.value,
    payload,
  );
  const preview = normalizeSubagentPublicationPreview(
    previewResponse.data?.governance?.next_publication_preview ||
      previewResponse.data?.governance?.nextPublicationPreview,
  );
  publicationPreview.value = preview;
  if (preview?.requiresConfirmation) {
    const confirmed = window.confirm(
      preview.confirmationMessage || `${preview.summary}\n\n确认继续执行吗？`,
    );
    if (!confirmed) {
      toastStore.showToast({ type: "info", message: cancelMessage });
      return false;
    }
  }
  await subagentsAPI.updateSubagentPublication(selectedDefinitionId.value, {
    ...payload,
    confirmed: Boolean(preview?.requiresConfirmation),
  });
  return true;
};

const savePublication = async () => {
  if (!selectedDefinitionId.value) return;
  if (!publicationForm.versionId) {
    toastStore.showToast({ type: "error", message: "请选择要发布的版本" });
    return;
  }

  busyAction.value = "publication";
  errorMessage.value = "";
  try {
    const updated = await updatePublicationWithPreview(
      {
        version_id: publicationForm.versionId,
        publication_scope: publicationForm.publicationScope,
        status: publicationForm.status,
        publication_metadata: parseJSONField(
          publicationForm.metadataText,
          {},
          "Publication Metadata JSON",
        ),
        change_reason: publicationForm.changeReason.trim(),
        change_notes: publicationForm.changeNotes.trim(),
        rollback_recovery_plan: publicationForm.rollbackRecoveryPlan.trim(),
        governance_metadata: parseJSONField(
          publicationForm.governanceMetadataText,
          {},
          "Governance Metadata JSON",
        ),
      },
      "已取消 publication 变更",
    );
    if (!updated) return;
    toastStore.showToast({ type: "success", message: "Publication 已更新" });
    await loadControlPlane(selectedDefinitionId.value);
  } catch (error) {
    console.error("Failed to update publication:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "更新 publication 失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const runMetadataAliasFreeze = async () => {
  busyAction.value = "metadata-alias-freeze";
  errorMessage.value = "";
  try {
    const previewResponse = await subagentsAPI.previewMetadataAliasFreeze(
      buildMetadataAliasFreezePayload(true),
    );
    const preview = normalizeMetadataAliasFreezePreview(
      previewResponse.data?.metadata_alias_freeze_preview ||
        previewResponse.data?.metadataAliasFreezePreview,
    );
    metadataAliasFreezePreview.value = preview;
    if (!preview) {
      throw new Error("未能生成 metadata alias 冻结预演");
    }
    if (!preview.executable) {
      throw new Error(
        preview.blockedReason || preview.summary || "当前无法执行 metadata alias 冻结",
      );
    }
    if (preview.requiresConfirmation) {
      const confirmed = window.confirm(
        preview.confirmationMessage || `${preview.summary}\n\n确认继续执行吗？`,
      );
      if (!confirmed) {
        toastStore.showToast({
          type: "info",
          message: "已取消 metadata alias 冻结",
        });
        return;
      }
    }
    const { data } = await subagentsAPI.freezeMetadataAliases({
      ...buildMetadataAliasFreezePayload(false),
      confirmed: Boolean(preview.requiresConfirmation),
    });
    metadataAliasFreezePreview.value = normalizeMetadataAliasFreezePreview(
      data?.metadata_alias_freeze_preview || data?.metadataAliasFreezePreview,
    );
    tenantGovernanceSummary.value = normalizeSubagentTenantGovernanceSummary(
      data.summary,
    );
    tenantGovernanceEvents.value = Array.isArray(data.events)
      ? data.events.map(normalizeSubagentPublicationEvent).filter(Boolean)
      : [];
    tenantGovernanceTotal.value = Number(data.total || 0);
    toastStore.showToast({
      type: "success",
      message: "Metadata alias 已完成冻结",
    });
    if (selectedDefinitionId.value) {
      await loadControlPlane(selectedDefinitionId.value);
    }
  } catch (error) {
    console.error("Failed to freeze metadata aliases:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "冻结 metadata alias 失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const publishVersion = async (version) => {
  if (!selectedDefinitionId.value || !version?.id) return;
  busyAction.value = `publish-${version.id}`;
  errorMessage.value = "";
  try {
    const updated = await updatePublicationWithPreview(
      {
        version_id: version.id,
        publication_scope:
          controlPlane.publication?.publicationScope ||
          controlPlane.definition?.publicationScope ||
          "tenant",
        status: "active",
        publication_metadata:
          controlPlane.publication?.metadata ||
          controlPlane.definition?.publicationMetadata ||
          {},
        change_reason: publicationForm.changeReason.trim(),
        change_notes: publicationForm.changeNotes.trim(),
        rollback_recovery_plan: publicationForm.rollbackRecoveryPlan.trim(),
        governance_metadata: parseJSONField(
          publicationForm.governanceMetadataText,
          {},
          "Governance Metadata JSON",
        ),
      },
      "已取消发布切换",
    );
    if (!updated) return;
    toastStore.showToast({
      type: "success",
      message: `v${version.versionNumber} 已发布`,
    });
    await loadControlPlane(selectedDefinitionId.value);
  } catch (error) {
    console.error("Failed to publish version:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "发布版本失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const createTestRun = async () => {
  if (!selectedDefinitionId.value) return;
  busyAction.value = "test-run";
  errorMessage.value = "";
  try {
    const { data } = await subagentsAPI.createSubagentTestRun(
      selectedDefinitionId.value,
      {
        version_id: testRunForm.versionId,
        agent_definition_id: testRunForm.agentDefinitionId,
        session_id: testRunForm.sessionId.trim(),
        input: parseJSONField(testRunForm.inputText, {}, "Input JSON"),
        metadata: parseJSONField(testRunForm.metadataText, {}, "Metadata JSON"),
        auto_start: Boolean(testRunForm.autoStart),
      },
    );
    toastStore.showToast({ type: "success", message: "测试运行已创建" });
    if (data?.id) {
      await router.push({
        name: "AgentRunDetail",
        params: { run_id: data.id },
      });
    }
  } catch (error) {
    console.error("Failed to create test run:", error);
    errorMessage.value =
      error?.response?.data?.error ||
      error?.response?.data?.detail ||
      error?.message ||
      "创建测试运行失败";
    toastStore.showToast({ type: "error", message: errorMessage.value });
  } finally {
    busyAction.value = "";
  }
};

const reloadAll = async () => {
  await loadAgents();
  await loadSubagents();
  await loadTenantGovernance();
  await loadMetadataAliasFreezePreview();
  if (selectedDefinitionId.value) {
    await loadControlPlane(selectedDefinitionId.value);
  }
};

onMounted(async () => {
  await loadAgents();
  await loadSubagents();
  await loadTenantGovernance();
  await loadMetadataAliasFreezePreview();
  if (
    !selectedDefinitionId.value &&
    String(route.query.subagent || "").trim()
  ) {
    await selectSubagent(String(route.query.subagent || "").trim());
  }
});

watch(
  () => metadataAliasFreezeForm.scope,
  async () => {
    await loadMetadataAliasFreezePreview();
  },
);

watch(
  () => route.query.subagent,
  async (value, previousValue) => {
    const next = String(value || "").trim();
    const previous = String(previousValue || "").trim();
    if (!next || next === previous || next === selectedDefinitionId.value)
      return;
    await selectSubagent(next);
  },
);
</script>

<style scoped>
.subagent-page {
  display: grid;
  gap: 24px;
}

.subagent-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(
      circle at top left,
      rgba(14, 165, 233, 0.18),
      transparent 40%
    ),
    linear-gradient(135deg, #f3fbff 0%, #fff 52%, #eefaf4 100%);
  border: 1px solid rgba(14, 165, 233, 0.15);
}

.hero-kicker {
  margin-bottom: 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #0369a1;
}

.subagent-hero h1 {
  margin: 0;
  font-size: 32px;
}

.subagent-hero p {
  margin: 10px 0 0;
  color: var(--gray-600);
}

.hero-actions,
.detail-actions,
.form-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.subagent-grid,
.detail-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(300px, 400px) minmax(0, 1fr);
}

.secondary-grid {
  grid-template-columns: minmax(0, 1fr) minmax(300px, 420px);
}

.card {
  padding: 24px;
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #fff;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head h2,
.detail-panel h3,
.authorization-section h4 {
  margin: 0;
}

.section-head p,
.detail-panel p,
.authorization-section p {
  margin: 8px 0 0;
  color: var(--gray-600);
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--gray-600);
}

.subagent-list,
.version-list,
.authorization-list {
  display: grid;
  gap: 12px;
}

.subagent-item,
.authorization-card {
  display: grid;
  gap: 10px;
  width: 100%;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: #fff;
  text-align: left;
  color: inherit;
  text-decoration: none;
  transition:
    border-color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.subagent-item:hover,
.authorization-card:hover {
  border-color: rgba(14, 165, 233, 0.4);
  transform: translateY(-1px);
  box-shadow: 0 14px 30px rgba(14, 165, 233, 0.08);
}

.subagent-item.active {
  border-color: rgba(14, 165, 233, 0.55);
  box-shadow: 0 18px 38px rgba(14, 165, 233, 0.1);
  background: linear-gradient(135deg, #ffffff 0%, #f4fbff 100%);
}

.subagent-item-top,
.version-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.subagent-item-meta,
.subagent-item-tags,
.version-card-meta,
.card-inline-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--gray-600);
  font-size: 13px;
}

.subagent-item-sub,
.version-copy {
  color: var(--gray-600);
  line-height: 1.6;
}

.status-pill,
.mini-badge,
.summary-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.mini-badge {
  background: #f8fafc;
  color: #475569;
}

.accent-badge {
  background: #e0f2fe;
  color: #075985;
}

.status-good {
  background: #ecfdf5;
  color: #047857;
}

.status-warn {
  background: #fff7ed;
  color: #c2410c;
}

.status-muted {
  background: #f1f5f9;
  color: #475569;
}

.editor-form,
.stack-form {
  display: grid;
  gap: 16px;
}

.field-row,
.advanced-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.input {
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: #fff;
  font: inherit;
  color: inherit;
}

.textarea {
  min-height: 120px;
  resize: vertical;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
}

.tall-textarea {
  min-height: 180px;
}

.checkbox-field {
  display: flex;
  align-items: center;
  gap: 10px;
}

.checkbox-field input {
  width: 18px;
  height: 18px;
}

.advanced-panel {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 18px;
  padding: 14px;
  background: #fbfdff;
}

.advanced-panel summary {
  cursor: pointer;
  font-weight: 600;
  color: #0f172a;
}

.advanced-grid {
  margin-top: 14px;
}

.detail-card {
  display: grid;
  gap: 20px;
}

.tenant-governance-card {
  display: grid;
  gap: 18px;
}

.tenant-governance-toolbar {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.governance-summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.compact-select {
  min-height: 42px;
}

.compact-empty {
  padding: 18px;
}

.tenant-event-list {
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.tenant-governance-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--gray-600);
}

.detail-panel {
  padding: 20px;
  border-radius: 20px;
  background: linear-gradient(180deg, #fff 0%, #fbfdff 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.publication-preview-card {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(14, 116, 144, 0.16);
  background: linear-gradient(180deg, #f5fbff 0%, #ffffff 100%);
}

.publication-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.preview-confirmation-copy {
  color: #9a3412;
}

.preview-table {
  margin: 0;
}

.preview-action-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.governance-form-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.detail-table {
  display: grid;
  gap: 10px;
  margin: 14px 0 18px;
}

.detail-table > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
}

.detail-table span {
  color: var(--gray-600);
}

.summary-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.governance-strip {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.governance-card {
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(14, 116, 144, 0.12);
  background: linear-gradient(180deg, #f8fdff 0%, #ffffff 100%);
}

.governance-card strong {
  display: block;
  margin-top: 10px;
  font-size: 20px;
}

.governance-card p {
  margin: 8px 0 0;
  color: var(--gray-600);
}

.governance-warning-list {
  display: grid;
  gap: 10px;
}

.compatibility-detail-list {
  display: grid;
  gap: 10px;
}

.compatibility-detail-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(14, 116, 144, 0.12);
  background: #f8fafc;
}

.compatibility-detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.migration-panel {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(249, 115, 22, 0.22);
  background: linear-gradient(135deg, #fff7ed 0%, #ffffff 100%);
}

.migration-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.migration-panel-head p {
  margin: 8px 0 0;
  color: var(--gray-600);
}

.governance-warning {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(14, 116, 144, 0.12);
  background: #f8fafc;
}

.governance-warning strong {
  min-width: 36px;
}

.governance-warning.severity-warning {
  background: #fff7ed;
  border-color: rgba(249, 115, 22, 0.2);
  color: #9a3412;
}

.governance-warning.severity-error {
  background: #fff1f2;
  border-color: rgba(239, 68, 68, 0.22);
  color: #b91c1c;
}

.governance-warning.severity-info {
  background: #eff6ff;
  border-color: rgba(59, 130, 246, 0.2);
  color: #1d4ed8;
}

.summary-card {
  padding: 18px;
  border-radius: 20px;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.summary-card strong {
  display: block;
  margin-top: 10px;
  font-size: 28px;
}

.summary-card p {
  margin: 8px 0 0;
  color: var(--gray-600);
}

.summary-card.accent {
  background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
}

.summary-label {
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #475569;
}

.version-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #fff;
}

.version-card-head span {
  color: var(--gray-600);
  font-size: 13px;
}

.authorization-section {
  display: grid;
  gap: 12px;
  margin-top: 22px;
}

.event-list {
  display: grid;
  gap: 12px;
}

.event-card {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #fff;
}

.event-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.event-card-head > div {
  display: grid;
  gap: 4px;
}

.event-meta-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  color: var(--gray-600);
  font-size: 13px;
}

.event-copy {
  margin: 0;
  color: #334155;
}

.panel-empty,
.mini-empty {
  padding: 24px;
  border-radius: 18px;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  background: #f8fafc;
  color: var(--gray-600);
  text-align: center;
}

.error-banner {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(239, 68, 68, 0.22);
  background: #fff1f2;
  color: #b91c1c;
}

@media (max-width: 1100px) {
  .subagent-grid,
  .detail-grid,
  .secondary-grid,
  .summary-grid,
  .governance-strip,
  .field-row,
  .advanced-grid {
    grid-template-columns: 1fr;
  }

  .subagent-hero,
  .section-head,
  .migration-panel-head,
  .tenant-governance-pagination,
  .subagent-item-top,
  .version-card-head {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
