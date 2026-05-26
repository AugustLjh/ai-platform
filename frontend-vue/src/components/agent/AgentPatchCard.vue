<template>
  <article class="artifact-card patch-card">
    <div class="artifact-head">
      <div>
        <div class="artifact-kicker">代码补丁</div>
        <h4>{{ artifact.name || 'Workspace Patch' }}</h4>
      </div>
      <span :class="['patch-status', statusClass]">{{ statusLabel }}</span>
    </div>

    <div class="patch-facts">
      <span>{{ operationLabel }}</span>
      <span>{{ dryRunLabel }}</span>
      <span>{{ files.length }} 个文件</span>
      <span v-if="patch.truncated">Diff 已截断</span>
      <span>{{ mergePolicyLabel }}</span>
    </div>

    <div v-if="writebackInfo" class="writeback-summary">
      <strong>仓库回写</strong>
      <span>{{ writebackSummary }}</span>
    </div>

    <div v-if="files.length > 0" class="patch-files">
      <section v-for="file in files" :key="`${file.path}-${file.operation}`" class="patch-file">
        <strong>{{ file.path }}</strong>
        <span>{{ fileOperationLabel(file.operation) }}</span>
      </section>
    </div>

    <div v-if="reviewNotes.length > 0 || hasDelete" class="patch-review">
      <strong>审查提示</strong>
      <ul>
        <li v-for="note in reviewNotes" :key="note">{{ note }}</li>
        <li v-if="hasDelete">包含删除动作，合并前应确认文件不再被引用。</li>
      </ul>
    </div>

    <div class="patch-actions">
      <button type="button" class="patch-action" @click="downloadPatch" :disabled="!patch.diff">
        下载 patch
      </button>
      <button type="button" class="patch-action" :class="{ active: reviewDecision === 'accepted' }" @click="reviewDecision = 'accepted'">
        标记接受
      </button>
      <button type="button" class="patch-action" :class="{ active: reviewDecision === 'rejected' }" @click="reviewDecision = 'rejected'">
        标记拒绝
      </button>
      <button type="button" class="patch-action" :disabled="!canSubmitReview || submitting" @click="submitReview">
        {{ submitting ? '提交中' : '提交审查' }}
      </button>
      <button type="button" class="patch-action" :disabled="writebackSubmitting" @click="previewWriteback">
        {{ writebackSubmitting && writebackMode === 'preview' ? '预览中' : '预览回写' }}
      </button>
      <button type="button" class="patch-action danger" :disabled="!canWriteback || writebackSubmitting" @click="confirmWriteback">
        {{ writebackSubmitting && writebackMode === 'apply' ? '回写中' : '确认回写' }}
      </button>
      <span v-if="reviewDecision" class="decision-label">{{ decisionLabel }}</span>
    </div>

    <p v-if="reviewMessage" :class="['review-message', reviewMessageTone]">{{ reviewMessage }}</p>
    <p v-if="writebackMessage" :class="['review-message', writebackMessageTone]">{{ writebackMessage }}</p>
    <p v-if="reviewMeta" class="review-meta">{{ reviewMeta }}</p>

    <pre v-if="patch.diff">{{ patch.diff }}</pre>
    <div v-else class="artifact-empty">当前补丁没有可展示的 diff。</div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useAgentsStore } from '@/store/agents'

const props = defineProps({
  artifact: {
    type: Object,
    required: true
  }
})

const agentsStore = useAgentsStore()
const patch = computed(() => props.artifact?.payload || {})
const files = computed(() => Array.isArray(patch.value.files) ? patch.value.files : [])
const reviewNotes = computed(() => Array.isArray(patch.value.reviewNotes) ? patch.value.reviewNotes : [])
const hasDelete = computed(() => files.value.some((file) => file.operation === 'delete'))
const reviewDecision = ref(String(props.artifact?.metadata?.review_decision || '').trim())
const submitting = ref(false)
const reviewMessage = ref('')
const writebackSubmitting = ref(false)
const writebackMode = ref('')
const writebackMessage = ref('')
watch(
  () => props.artifact,
  (artifact) => {
    reviewDecision.value = String(artifact?.metadata?.review_decision || artifact?.metadata?.reviewDecision || '').trim()
  },
  { deep: true, immediate: true }
)
const statusLabel = computed(() => {
  if (patch.value.dryRun) return '预览'
  if (patch.value.status === 'applied') return '已应用'
  return patch.value.status || '待审查'
})
const statusClass = computed(() => patch.value.dryRun ? 'is-preview' : patch.value.status === 'applied' ? 'is-applied' : 'is-pending')
const operationLabel = computed(() => fileOperationLabel(patch.value.operation))
const dryRunLabel = computed(() => patch.value.dryRun ? '未写入 workspace' : '已写入 workspace')
const mergePolicyLabel = computed(() => patch.value.mergePolicy === 'manual_review_required' ? '需人工审查' : (patch.value.mergePolicy || '需人工审查'))
const writebackInfo = computed(() => patch.value.writeback && typeof patch.value.writeback === 'object' ? patch.value.writeback : null)
const writebackSummary = computed(() => {
  const info = writebackInfo.value
  if (!info) return ''
  const status = String(info.status || patch.value.status || '').trim()
  const changeCount = Number(info.change_count ?? info.changeCount ?? patch.value.files?.length ?? 0)
  const appliedCount = Number(info.applied_count ?? info.appliedCount ?? 0)
  const failedCount = Number(info.failed_count ?? info.failedCount ?? 0)
  const sourcePath = String(info.source_path || info.sourcePath || '').trim()
  return `${status || '已生成'} · 变更 ${changeCount} 个 · 已回写 ${appliedCount} 个 · 失败 ${failedCount} 个${sourcePath ? ` · ${sourcePath}` : ''}`
})
const decisionLabel = computed(() => {
  const metadata = props.artifact?.metadata || {}
  const persisted = String(metadata.review_decision || metadata.reviewDecision || '').trim()
  if (persisted === 'accepted') return '已提交接受'
  if (persisted === 'rejected') return '已提交拒绝'
  return reviewDecision.value === 'accepted' ? '待提交接受' : '待提交拒绝'
})
const canSubmitReview = computed(() => Boolean(reviewDecision.value))
const reviewMeta = computed(() => {
  const metadata = props.artifact?.metadata || {}
  const reviewedBy = String(metadata.reviewed_by || metadata.reviewedBy || '').trim()
  const reviewedAt = String(metadata.reviewed_at || metadata.reviewedAt || '').trim()
  if (!reviewedBy && !reviewedAt) return ''
  const parts = []
  if (reviewedBy) parts.push(`reviewed by ${reviewedBy}`)
  if (reviewedAt) parts.push(reviewedAt)
  return parts.join(' · ')
})
const reviewMessageTone = computed(() => reviewMessage.value.startsWith('已') ? 'success' : 'warning')
const writebackMessageTone = computed(() => writebackMessage.value.startsWith('已') || writebackMessage.value.startsWith('预览') ? 'success' : 'warning')
const canWriteback = computed(() => Boolean(props.artifact?.runId || props.artifact?.run_id))

const fileOperationLabel = (operation) => {
  const normalized = String(operation || '').trim()
  if (normalized === 'create') return '新增'
  if (normalized === 'delete') return '删除'
  if (normalized === 'modify') return '修改'
  if (normalized === 'rename') return '重命名'
  return normalized || '变更'
}

const safeFileName = computed(() => {
  const firstPath = files.value[0]?.path || 'workspace'
  return `${String(firstPath).replace(/[^a-zA-Z0-9._-]+/g, '-') || 'workspace'}.patch`
})

const downloadPatch = () => {
  if (!patch.value.diff) return
  const blob = new Blob([patch.value.diff], { type: 'text/x-patch;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = safeFileName.value
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const submitReview = async () => {
  if (!canSubmitReview.value || submitting.value) return
  const runId = props.artifact?.runId || props.artifact?.run_id || ''
  const artifactId = props.artifact?.id || ''
  if (!runId || !artifactId) {
    reviewMessage.value = '缺少 run 或 artifact 标识，无法提交审查。'
    return
  }
  submitting.value = true
  reviewMessage.value = ''
  try {
    const { data } = await agentsStore.reviewRunArtifact(runId, artifactId, {
      decision: reviewDecision.value,
      note: reviewDecision.value === 'rejected' ? 'Patch review rejected from artifact card.' : 'Patch review accepted from artifact card.'
    })
    const refreshedArtifact = (data?.run?.artifacts || []).find((item) => item.id === artifactId)
    reviewDecision.value = String(refreshedArtifact?.metadata?.review_decision || refreshedArtifact?.metadata?.reviewDecision || reviewDecision.value || '').trim()
    reviewMessage.value = '已提交审查结果。'
  } catch (error) {
    reviewMessage.value = error?.response?.data?.detail || error?.message || '提交审查失败。'
  } finally {
    submitting.value = false
  }
}

const runWriteback = async ({ dryRun }) => {
  const runId = props.artifact?.runId || props.artifact?.run_id || ''
  if (!runId) {
    writebackMessage.value = '缺少 run 标识，无法执行仓库回写。'
    return
  }
  writebackSubmitting.value = true
  writebackMode.value = dryRun ? 'preview' : 'apply'
  writebackMessage.value = ''
  try {
    const { data } = await agentsStore.writebackRunWorkspace(runId, {
      dry_run: dryRun,
      confirmed: !dryRun,
      max_diff_chars: 60000
    })
    const writebackArtifact = (data?.run?.artifacts || [])
      .filter((item) => item?.metadata?.source === 'workspace_writeback')
      .at(-1)
    const payload = writebackArtifact?.payload || {}
    const count = Number(payload?.writeback?.change_count ?? payload?.files?.length ?? 0)
    const applied = Number(payload?.writeback?.applied_count ?? 0)
    const failed = Number(payload?.writeback?.failed_count ?? 0)
    writebackMessage.value = dryRun
      ? `预览完成：检测到 ${count} 个可回写变更。`
      : `已执行回写：成功 ${applied} 个，失败 ${failed} 个。`
  } catch (error) {
    writebackMessage.value = error?.response?.data?.detail || error?.message || '仓库回写失败。'
  } finally {
    writebackSubmitting.value = false
    writebackMode.value = ''
  }
}

const previewWriteback = () => runWriteback({ dryRun: true })
const confirmWriteback = () => runWriteback({ dryRun: false })
</script>

<style scoped>
.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  max-height: min(56vh, 560px);
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
  color: #475569;
}

.artifact-head h4 {
  margin-top: 6px;
  font-size: 16px;
}

.patch-status {
  min-width: 58px;
  height: 30px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  background: #f1f5f9;
  color: #334155;
}

.patch-status.is-applied {
  background: rgba(16, 163, 127, 0.1);
  color: #047857;
}

.patch-status.is-preview {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.patch-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.patch-facts span,
.patch-file span {
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #475569;
  padding: 5px 8px;
  font-size: 12px;
}

.patch-files {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.patch-file {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fbfdff;
}

.patch-file strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.patch-review {
  margin-top: 12px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  border-radius: 8px;
  padding: 10px 12px;
  color: #92400e;
  font-size: 13px;
}

.patch-review ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.writeback-summary {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  border: 1px solid rgba(13, 148, 136, 0.22);
  background: rgba(240, 253, 250, 0.75);
  border-radius: 8px;
  padding: 10px 12px;
  color: #115e59;
  font-size: 13px;
}

.patch-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.patch-action {
  height: 32px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.patch-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.patch-action.active {
  border-color: #10a37f;
  color: #047857;
  background: rgba(16, 163, 127, 0.08);
}

.patch-action.danger {
  border-color: rgba(220, 38, 38, 0.28);
  color: #991b1b;
}

.decision-label {
  color: #475569;
  font-size: 12px;
}

.review-message {
  margin-top: 10px;
  font-size: 12px;
}

.review-message.success {
  color: #047857;
}

.review-message.warning {
  color: #92400e;
}

.review-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

pre {
  margin: 12px 0 0;
  padding: 12px;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
  max-height: 360px;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
}

.artifact-empty {
  margin-top: 12px;
  color: var(--gray-500);
  font-size: 14px;
}
</style>
