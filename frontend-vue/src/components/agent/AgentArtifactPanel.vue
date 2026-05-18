<template>
  <section class="artifact-panel">
    <div class="panel-head">
      <div>
        <h3>结构化结果</h3>
        <p>优先展示运行产物，而不是把所有结果压平成一段 markdown。</p>
        <p v-if="surfaceSummary" class="surface-summary">{{ surfaceSummary }}</p>
      </div>
      <span class="panel-count">{{ artifactCount }}</span>
    </div>

    <div v-if="artifactCount > 0" class="artifact-toolbar">
      <div class="artifact-toolbar-grid">
        <label class="artifact-filter">
          <span>产物类型</span>
          <select v-model="selectedArtifactType">
            <option value="all">全部类型</option>
            <option v-for="option in artifactTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label class="artifact-filter">
          <span>来源 Run</span>
          <select v-model="selectedChildRunId">
            <option value="all">全部来源</option>
            <option value="current_run">当前 run</option>
            <option v-for="option in childRunOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label class="artifact-filter">
          <span>Review 状态</span>
          <select v-model="selectedReviewStatus">
            <option value="all">全部状态</option>
            <option v-for="option in reviewStatusOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
      </div>

      <div class="artifact-summary-chips">
        <span class="summary-chip">显示 {{ filteredArtifactCount }} / {{ artifactCount }}</span>
        <span v-if="artifactSummary.reviewCounts.blocked > 0" class="summary-chip danger">
          阻断 {{ artifactSummary.reviewCounts.blocked }}
        </span>
        <span v-if="artifactSummary.reviewCounts.needs_review > 0" class="summary-chip warning">
          待审 {{ artifactSummary.reviewCounts.needs_review }}
        </span>
        <span v-if="artifactSummary.childRunCounts.current_run" class="summary-chip">
          当前 run {{ artifactSummary.childRunCounts.current_run }}
        </span>
      </div>
    </div>

    <div v-if="artifactCount === 0 && !hasStructuredJson" class="empty-state">
      当前 run 还没有可展示的结构化结果。
    </div>

    <div v-else-if="filteredArtifactCount === 0 && artifactCount > 0" class="empty-state">
      当前筛选条件下没有匹配的结构化结果。
    </div>

    <div v-else class="artifact-list">
      <article v-for="artifact in visibleAnswerArtifacts" :key="artifact.clientKey" class="artifact-card answer-card">
        <div class="artifact-origin-row">
          <span class="artifact-origin">{{ artifactDescriptor(artifact).sourceLabel }}</span>
          <span :class="['artifact-review-status', artifactDescriptor(artifact).reviewStatus]">{{ reviewStatusLabel(artifactDescriptor(artifact).reviewStatus) }}</span>
        </div>
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">回答</div>
            <h4>{{ artifact.name || 'Final Answer' }}</h4>
          </div>
        </div>
        <div class="markdown agent-markdown" v-html="renderMarkdown(answerText(artifact))"></div>
      </article>

      <AgentFindingsCard
        v-for="artifact in visibleFindingArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentCitationsCard
        v-for="artifact in visibleCitationArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <article v-for="artifact in visibleWorkspaceArtifacts" :key="artifact.clientKey" class="artifact-card workspace-card">
        <div class="artifact-origin-row">
          <span class="artifact-origin">{{ artifactDescriptor(artifact).sourceLabel }}</span>
          <span :class="['artifact-review-status', artifactDescriptor(artifact).reviewStatus]">{{ reviewStatusLabel(artifactDescriptor(artifact).reviewStatus) }}</span>
        </div>
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">Workspace</div>
            <h4>{{ artifact.name || 'Workspace Binding' }}</h4>
          </div>
          <span class="artifact-meta">{{ workspaceStatusLabel(artifact.payload?.status) }}</span>
        </div>
        <dl class="workspace-facts">
          <div>
            <dt>来源</dt>
            <dd>{{ workspaceSourceLabel(artifact.payload?.source) }}</dd>
          </div>
          <div>
            <dt>快照</dt>
            <dd>{{ formatWorkspaceSnapshot(artifact.payload?.snapshot) }}</dd>
          </div>
          <div>
            <dt>文件数</dt>
            <dd>{{ artifact.payload?.snapshot?.file_count ?? 0 }}</dd>
          </div>
          <div>
            <dt>大小</dt>
            <dd>{{ formatBytes(artifact.payload?.snapshot?.total_size_bytes) }}</dd>
          </div>
        </dl>
      </article>

      <AgentCodeFilesCard
        v-for="artifact in visibleCodeFileArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentPatchCard
        v-for="artifact in visiblePatchArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentVerificationCard
        v-for="artifact in visibleVerificationArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in visibleDirectoryTreeArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in visiblePagedArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <article v-for="artifact in visiblePlanArtifacts" :key="artifact.clientKey" class="artifact-card">
        <div class="artifact-origin-row">
          <span class="artifact-origin">{{ artifactDescriptor(artifact).sourceLabel }}</span>
          <span :class="['artifact-review-status', artifactDescriptor(artifact).reviewStatus]">{{ reviewStatusLabel(artifactDescriptor(artifact).reviewStatus) }}</span>
        </div>
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">任务计划</div>
            <h4>{{ artifact.name }}</h4>
          </div>
        </div>
        <pre>{{ formatJSON(artifact.payload) }}</pre>
      </article>

      <article v-for="artifact in visibleTableArtifacts" :key="artifact.clientKey" class="artifact-card">
        <div class="artifact-origin-row">
          <span class="artifact-origin">{{ artifactDescriptor(artifact).sourceLabel }}</span>
          <span :class="['artifact-review-status', artifactDescriptor(artifact).reviewStatus]">{{ reviewStatusLabel(artifactDescriptor(artifact).reviewStatus) }}</span>
        </div>
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">表格</div>
            <h4>{{ artifact.name }}</h4>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in tableRows(artifact)" :key="index">
                <td v-for="column in tableColumns(artifact)" :key="column">{{ displayCell(row?.[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article v-for="artifact in visibleExcerptArtifacts" :key="artifact.clientKey" class="artifact-card">
        <div class="artifact-origin-row">
          <span class="artifact-origin">{{ artifactDescriptor(artifact).sourceLabel }}</span>
          <span :class="['artifact-review-status', artifactDescriptor(artifact).reviewStatus]">{{ reviewStatusLabel(artifactDescriptor(artifact).reviewStatus) }}</span>
        </div>
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">文档摘录</div>
            <h4>{{ artifact.name }}</h4>
          </div>
        </div>
        <div class="excerpt-list">
          <section v-for="(item, index) in excerptItems(artifact)" :key="index" class="excerpt-card">
            <strong v-if="item.title">{{ item.title }}</strong>
            <p>{{ item.text }}</p>
            <span v-if="item.source" class="excerpt-source">{{ item.source }}</span>
          </section>
        </div>
      </article>

      <AgentRichArtifactCard
        v-for="artifact in visibleDocumentPageArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in visibleMediaArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in visibleFileBundleArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in visibleArchiveArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <article v-if="hasStructuredJson" class="artifact-card">
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">原始结构化结果</div>
            <h4>Final Output JSON</h4>
          </div>
        </div>
        <pre>{{ formatJSON(finalOutputJson) }}</pre>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import {
  artifactTypeLabel,
  describeArtifact,
  filterArtifacts,
  summarizeArtifactFilters
} from '@/utils/agentArtifacts'
import AgentCitationsCard from './AgentCitationsCard.vue'
import AgentCodeFilesCard from './AgentCodeFilesCard.vue'
import AgentFindingsCard from './AgentFindingsCard.vue'
import AgentPatchCard from './AgentPatchCard.vue'
import AgentRichArtifactCard from './AgentRichArtifactCard.vue'
import AgentVerificationCard from './AgentVerificationCard.vue'

const props = defineProps({
  artifacts: {
    type: Array,
    default: () => []
  },
  finalOutputJson: {
    type: [Object, Array, String, Number, Boolean],
    default: null
  },
  surfaceMeta: {
    type: Object,
    default: null
  },
  runTreeInvocations: {
    type: Array,
    default: () => []
  },
  resolvedInvocations: {
    type: Array,
    default: () => []
  }
})

const selectedArtifactType = ref('all')
const selectedChildRunId = ref('all')
const selectedReviewStatus = ref('all')
const artifactCount = computed(() => props.artifacts.length)
const hasStructuredJson = computed(() => props.finalOutputJson !== null && props.finalOutputJson !== undefined)
const artifactSummary = computed(() => summarizeArtifactFilters({
  artifacts: props.artifacts,
  runTreeInvocations: props.runTreeInvocations,
  resolvedInvocations: props.resolvedInvocations
}))
const filteredArtifacts = computed(() => filterArtifacts({
  artifacts: props.artifacts,
  artifactType: selectedArtifactType.value,
  childRunId: selectedChildRunId.value,
  reviewStatus: selectedReviewStatus.value,
  runTreeInvocations: props.runTreeInvocations,
  resolvedInvocations: props.resolvedInvocations
}))
const filteredArtifactCount = computed(() => filteredArtifacts.value.length)
const artifactTypeOptions = computed(() => (
  Object.entries(artifactSummary.value.typeCounts || {})
    .map(([value, count]) => ({
      value,
      label: `${artifactTypeLabel(value)} ${count}`
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
))
const childRunOptions = computed(() => (
  Object.entries(artifactSummary.value.childRunCounts || {})
    .filter(([value]) => value !== 'current_run')
    .map(([value, count]) => ({
      value,
      label: `${value.slice(0, 8)} · ${count}`
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
))
const reviewStatusOptions = computed(() => {
  const labels = {
    blocked: '阻断',
    needs_review: '待审',
    reviewed: '已审',
    unreviewed: '未审'
  }
  return Object.entries(labels)
    .filter(([key]) => Number(artifactSummary.value.reviewCounts?.[key] || 0) > 0)
    .map(([value, label]) => ({ value, label: `${label} ${artifactSummary.value.reviewCounts[value]}` }))
})
const surfaceSummary = computed(() => {
  const meta = props.surfaceMeta
  if (!meta || typeof meta !== 'object') return ''
  if (meta.hasEmptyEventHistory) {
    return '当前结果面直接由持久化 run 快照恢复；事件历史为空时也会保持相同展示。'
  }
  if (meta.resumed) {
    return `当前展示第 ${meta.attemptIndex || 1} 轮执行结果，已从最近一次恢复边界重新回放。`
  }
  if (meta.source === 'event_replay') {
    return '当前结果面由 run events 回放恢复，并与实时流式 patch 共用同一套语义。'
  }
  return ''
})
const filterByType = (type) => computed(() => filteredArtifacts.value.filter((artifact) => artifact.artifactType === type))
const visibleAnswerArtifacts = filterByType('answer')
const visibleFindingArtifacts = filterByType('review_findings')
const visibleCitationArtifacts = filterByType('citations')
const visibleWorkspaceArtifacts = filterByType('workspace_summary')
const visibleCodeFileArtifacts = filterByType('code_files')
const visiblePatchArtifacts = filterByType('code_patch')
const visibleVerificationArtifacts = filterByType('verification_report')
const visibleDirectoryTreeArtifacts = filterByType('directory_tree')
const visiblePagedArtifacts = filterByType('paged_collection')
const visiblePlanArtifacts = filterByType('task_plan')
const visibleTableArtifacts = filterByType('table')
const visibleDocumentPageArtifacts = filterByType('document_pages')
const visibleExcerptArtifacts = filterByType('document_excerpt')
const visibleMediaArtifacts = filterByType('media_gallery')
const visibleArchiveArtifacts = filterByType('archive_bundle')
const visibleFileBundleArtifacts = filterByType('file_bundle')

const answerText = (artifact) => String(artifact?.payload?.text || '').trim()
const artifactDescriptor = (artifact) => describeArtifact(artifact, artifactSummary.value.collaborationIndex)
const formatJSON = (value) => JSON.stringify(value || {}, null, 2)
const tableColumns = (artifact) => Array.isArray(artifact?.payload?.columns) ? artifact.payload.columns : []
const tableRows = (artifact) => Array.isArray(artifact?.payload?.rows) ? artifact.payload.rows : []
const excerptItems = (artifact) => Array.isArray(artifact?.payload?.items) ? artifact.payload.items : []
const displayCell = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
const workspaceStatusLabel = (value) => value === 'ready' ? '已绑定' : (value || '未知')
const workspaceSourceLabel = (source = {}) => {
  const type = String(source?.type || '').trim()
  if (type === 'upload_bundle') return '上传文件包'
  if (type === 'local_path') return '项目副本'
  if (type === 'existing') return '已登记项目目录'
  return type || '未记录'
}
const formatWorkspaceSnapshot = (snapshot = {}) => {
  if (!snapshot?.snapshot_at) return '未生成'
  return new Date(snapshot.snapshot_at).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
const formatBytes = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return '0 B'
  if (parsed < 1024) return `${parsed} B`
  if (parsed < 1024 * 1024) return `${(parsed / 1024).toFixed(1)} KB`
  return `${(parsed / (1024 * 1024)).toFixed(1)} MB`
}
const reviewStatusLabel = (value) => ({
  blocked: '阻断',
  needs_review: '待审',
  reviewed: '已审',
  unreviewed: '未审'
}[value] || '未审')
</script>

<style scoped>
.artifact-panel {
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.14);
  border-radius: 16px;
  padding: 14px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  max-height: min(68vh, 760px);
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.panel-head h3 {
  font-size: 16px;
  margin: 0 0 4px;
}

.panel-head p {
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.45;
}

.surface-summary {
  margin-top: 6px;
  color: var(--primary-700);
}

.panel-count {
  min-width: 30px;
  height: 30px;
  border-radius: 10px;
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.artifact-toolbar {
  display: grid;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  background: #fcfdfd;
}

.artifact-toolbar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.artifact-filter {
  display: grid;
  gap: 6px;
}

.artifact-filter span {
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 700;
}

.artifact-filter select {
  width: 100%;
  min-height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: white;
  padding: 0 10px;
  color: #0f172a;
}

.artifact-summary-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border-radius: 999px;
  padding: 0 10px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.summary-chip.warning {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.summary-chip.danger {
  background: rgba(239, 68, 68, 0.14);
  color: #b91c1c;
}

.empty-state {
  padding: 14px;
  border-radius: var(--radius-lg);
  background: var(--gray-50);
  color: var(--gray-500);
  text-align: center;
}

.artifact-list {
  display: grid;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 14px;
  padding: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
  max-height: min(48vh, 460px);
  overflow: auto;
}

.artifact-origin-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.artifact-origin,
.artifact-review-status {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 0 9px;
  font-size: 11px;
  font-weight: 700;
}

.artifact-origin {
  background: rgba(15, 23, 42, 0.06);
  color: var(--gray-600);
}

.artifact-review-status {
  background: rgba(15, 23, 42, 0.06);
  color: var(--gray-600);
}

.artifact-review-status.reviewed {
  background: rgba(16, 163, 127, 0.14);
  color: var(--primary-700);
}

.artifact-review-status.needs_review {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.artifact-review-status.blocked {
  background: rgba(239, 68, 68, 0.14);
  color: #b91c1c;
}

.artifact-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.artifact-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--primary-700);
}

.artifact-head h4 {
  margin-top: 4px;
  font-size: 15px;
}

.answer-card :deep(p) {
  line-height: 1.7;
}

.table-wrap {
  margin-top: 10px;
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
}

th,
td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  text-align: left;
  font-size: 13px;
}

th {
  color: var(--gray-600);
  font-weight: 700;
}

.excerpt-list {
  display: grid;
  gap: 10px;
  margin-top: 10px;
  max-height: 280px;
  overflow-y: auto;
  padding-right: 4px;
}

.excerpt-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  padding: 10px;
  background: #fcfdfd;
}

.excerpt-card p {
  margin-top: 8px;
  line-height: 1.7;
  color: var(--gray-700);
}

.file-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.excerpt-source {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.workspace-facts {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.workspace-facts div {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  padding: 9px;
  background: #fcfdfd;
}

.workspace-facts dt {
  color: var(--gray-500);
  font-size: 12px;
}

.workspace-facts dd {
  margin-top: 4px;
  color: #0f172a;
  font-weight: 700;
}

.artifact-meta {
  color: var(--gray-500);
  font-size: 12px;
}

.media-grid {
  margin-top: 10px;
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.media-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  overflow: hidden;
  background: #fcfdfd;
}

.media-preview,
.media-fallback {
  width: 100%;
  aspect-ratio: 16 / 10;
  object-fit: cover;
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.1), rgba(15, 23, 42, 0.08));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-700);
  font-weight: 700;
}

.media-copy {
  display: grid;
  gap: 5px;
  padding: 10px;
}

.media-copy span {
  color: var(--gray-500);
  font-size: 12px;
}

pre {
  margin-top: 10px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.04);
  overflow: auto;
  max-height: 280px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
</style>
