<template>
  <div v-if="artifactCount > 0" class="tool-preview">
    <article v-for="artifact in answerArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">文本结果</span>
        <strong>{{ artifact.name }}</strong>
      </div>
      <div class="markdown agent-markdown" v-html="renderMarkdown(answerText(artifact))"></div>
    </article>

    <article v-for="artifact in planArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">任务计划</span>
        <strong>{{ artifact.name }}</strong>
      </div>
      <pre>{{ formatJSON(artifact.payload) }}</pre>
    </article>

    <AgentFindingsCard
      v-for="artifact in findingArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
    />

    <AgentRichArtifactCard
      v-for="artifact in directoryTreeArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />

    <article v-for="artifact in tableArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">表格结果</span>
        <strong>{{ artifact.name }}</strong>
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

    <AgentRichArtifactCard
      v-for="artifact in pagedArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />

    <article v-for="artifact in citationArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">引用</span>
        <strong>{{ artifact.name }}</strong>
      </div>
      <div class="preview-list">
        <section v-for="(item, index) in citationItems(artifact)" :key="index" class="preview-item">
          <strong>{{ item.title }}</strong>
          <p v-if="item.snippet">{{ item.snippet }}</p>
          <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">{{ item.url }}</a>
        </section>
      </div>
    </article>

    <AgentRichArtifactCard
      v-for="artifact in documentPageArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />

    <article v-for="artifact in excerptArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">内容预览</span>
        <strong>{{ artifact.name }}</strong>
      </div>
      <div class="preview-list">
        <section v-for="(item, index) in excerptItems(artifact)" :key="index" class="preview-item">
          <strong v-if="item.title">{{ item.title }}</strong>
          <p>{{ item.text }}</p>
          <span v-if="item.source" class="preview-source">{{ item.source }}</span>
        </section>
      </div>
    </article>

    <article v-for="artifact in codeFileArtifacts" :key="artifact.clientKey" class="preview-card">
      <div class="preview-head">
        <span class="preview-kicker">代码结果</span>
        <strong>{{ artifact.name }}</strong>
      </div>
      <div class="preview-list">
        <section v-for="(file, index) in codeFiles(artifact)" :key="`${file.path}-${index}`" class="preview-item">
          <strong>{{ file.path }}</strong>
          <pre>{{ file.content }}</pre>
        </section>
      </div>
    </article>

    <AgentPatchCard
      v-for="artifact in patchArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
    />

    <AgentVerificationCard
      v-for="artifact in verificationArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
    />

    <AgentRichArtifactCard
      v-for="artifact in mediaArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />

    <AgentRichArtifactCard
      v-for="artifact in fileBundleArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />

    <AgentRichArtifactCard
      v-for="artifact in archiveArtifacts"
      :key="artifact.clientKey"
      :artifact="artifact"
      compact
    />
  </div>

  <pre v-else>{{ formattedResult }}</pre>
</template>

<script setup>
import { computed } from 'vue'
import { buildArtifactsFromToolResult } from '@/utils/agentArtifacts'
import { renderMarkdown } from '@/utils/markdown'
import AgentFindingsCard from './AgentFindingsCard.vue'
import AgentPatchCard from './AgentPatchCard.vue'
import AgentRichArtifactCard from './AgentRichArtifactCard.vue'
import AgentVerificationCard from './AgentVerificationCard.vue'

const props = defineProps({
  result: {
    type: Object,
    default: () => ({})
  },
  toolCall: {
    type: Object,
    default: () => ({})
  }
})

const artifacts = computed(() => buildArtifactsFromToolResult(props.result, props.toolCall))
const artifactCount = computed(() => artifacts.value.length)
const answerArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'answer'))
const planArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'task_plan'))
const findingArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'review_findings'))
const directoryTreeArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'directory_tree'))
const tableArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'table'))
const pagedArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'paged_collection'))
const citationArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'citations'))
const documentPageArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'document_pages'))
const excerptArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'document_excerpt'))
const codeFileArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'code_files'))
const patchArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'code_patch'))
const verificationArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'verification_report'))
const mediaArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'media_gallery'))
const archiveArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'archive_bundle'))
const fileBundleArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.artifactType === 'file_bundle'))
const formattedResult = computed(() => JSON.stringify(props.result || {}, null, 2))

const answerText = (artifact) => String(artifact?.payload?.text || '').trim()
const formatJSON = (value) => JSON.stringify(value || {}, null, 2)
const tableColumns = (artifact) => Array.isArray(artifact?.payload?.columns) ? artifact.payload.columns : []
const tableRows = (artifact) => Array.isArray(artifact?.payload?.rows) ? artifact.payload.rows : []
const citationItems = (artifact) => Array.isArray(artifact?.payload?.items) ? artifact.payload.items : []
const excerptItems = (artifact) => Array.isArray(artifact?.payload?.items) ? artifact.payload.items : []
const codeFiles = (artifact) => Array.isArray(artifact?.payload?.files) ? artifact.payload.files : []

const displayCell = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.tool-preview {
  display: grid;
  gap: 12px;
}

.preview-card {
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.preview-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.preview-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: #0f766e;
}

.preview-list {
  display: grid;
  gap: 10px;
}

.preview-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.04);
}

.preview-item p,
.preview-item pre {
  margin: 8px 0 0;
}

.preview-item pre {
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: 12px;
}

pre {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  background: rgba(13, 13, 13, 0.04);
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
}

.preview-source {
  display: inline-block;
  margin-top: 8px;
  color: var(--gray-500);
  font-size: 12px;
}

.preview-meta {
  color: var(--gray-500);
  font-size: 12px;
}

.preview-media-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.media-item {
  display: grid;
  gap: 8px;
}

.media-preview,
.media-fallback {
  width: 100%;
  aspect-ratio: 16 / 10;
  object-fit: cover;
  border-radius: 10px;
  background: rgba(15, 118, 110, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0f766e;
  font-weight: 700;
}

.table-wrap {
  overflow: auto;
}

table {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
}

th,
td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  font-size: 12px;
}
</style>
