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

    <div v-if="artifactCount === 0 && !hasStructuredJson" class="empty-state">
      当前 run 还没有可展示的结构化结果。
    </div>

    <div v-else class="artifact-list">
      <article v-for="artifact in answerArtifacts" :key="artifact.clientKey" class="artifact-card answer-card">
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">回答</div>
            <h4>{{ artifact.name || 'Final Answer' }}</h4>
          </div>
        </div>
        <div class="markdown agent-markdown" v-html="renderMarkdown(answerText(artifact))"></div>
      </article>

      <AgentFindingsCard
        v-for="artifact in findingArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentCitationsCard
        v-for="artifact in citationArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentCodeFilesCard
        v-for="artifact in codeFileArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in directoryTreeArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in pagedArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <article v-for="artifact in planArtifacts" :key="artifact.clientKey" class="artifact-card">
        <div class="artifact-head">
          <div>
            <div class="artifact-kicker">任务计划</div>
            <h4>{{ artifact.name }}</h4>
          </div>
        </div>
        <pre>{{ formatJSON(artifact.payload) }}</pre>
      </article>

      <article v-for="artifact in tableArtifacts" :key="artifact.clientKey" class="artifact-card">
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

      <article v-for="artifact in excerptArtifacts" :key="artifact.clientKey" class="artifact-card">
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
        v-for="artifact in documentPageArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in mediaArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in fileBundleArtifacts"
        :key="artifact.clientKey"
        :artifact="artifact"
      />

      <AgentRichArtifactCard
        v-for="artifact in archiveArtifacts"
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
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import AgentCitationsCard from './AgentCitationsCard.vue'
import AgentCodeFilesCard from './AgentCodeFilesCard.vue'
import AgentFindingsCard from './AgentFindingsCard.vue'
import AgentRichArtifactCard from './AgentRichArtifactCard.vue'

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
  }
})

const answerArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'answer'))
const findingArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'review_findings'))
const citationArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'citations'))
const codeFileArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'code_files'))
const directoryTreeArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'directory_tree'))
const pagedArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'paged_collection'))
const planArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'task_plan'))
const tableArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'table'))
const documentPageArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'document_pages'))
const excerptArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'document_excerpt'))
const mediaArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'media_gallery'))
const archiveArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'archive_bundle'))
const fileBundleArtifacts = computed(() => props.artifacts.filter((artifact) => artifact.artifactType === 'file_bundle'))
const artifactCount = computed(() => props.artifacts.length)
const hasStructuredJson = computed(() => props.finalOutputJson !== null && props.finalOutputJson !== undefined)
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

const answerText = (artifact) => String(artifact?.payload?.text || '').trim()
const formatJSON = (value) => JSON.stringify(value || {}, null, 2)
const tableColumns = (artifact) => Array.isArray(artifact?.payload?.columns) ? artifact.payload.columns : []
const tableRows = (artifact) => Array.isArray(artifact?.payload?.rows) ? artifact.payload.rows : []
const excerptItems = (artifact) => Array.isArray(artifact?.payload?.items) ? artifact.payload.items : []
const displayCell = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.artifact-panel {
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.14);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  max-height: min(72vh, 840px);
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.panel-head h3 {
  font-size: 18px;
  margin: 0 0 6px;
}

.panel-head p {
  color: var(--gray-600);
  font-size: 14px;
}

.surface-summary {
  margin-top: 8px;
  color: var(--primary-700);
}

.panel-count {
  min-width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.empty-state {
  padding: 20px;
  border-radius: var(--radius-lg);
  background: var(--gray-50);
  color: var(--gray-500);
  text-align: center;
}

.artifact-list {
  display: grid;
  gap: 16px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
  max-height: min(52vh, 520px);
  overflow: auto;
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
  margin-top: 6px;
  font-size: 17px;
}

.answer-card :deep(p) {
  line-height: 1.7;
}

.table-wrap {
  margin-top: 14px;
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
}

th,
td {
  padding: 10px 12px;
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
  gap: 12px;
  margin-top: 14px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.excerpt-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  padding: 14px;
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

.artifact-meta {
  color: var(--gray-500);
  font-size: 12px;
}

.media-grid {
  margin-top: 14px;
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.media-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
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
  gap: 6px;
  padding: 14px;
}

.media-copy span {
  color: var(--gray-500);
  font-size: 12px;
}

pre {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
  overflow: auto;
  max-height: 320px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
</style>
