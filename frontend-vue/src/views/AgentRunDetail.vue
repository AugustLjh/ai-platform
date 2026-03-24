<template>
  <div class="run-detail-page">
    <AgentRunHeader
      :run="run"
      :agent-name="agent?.name || ''"
      @refresh="refreshRun"
      @cancel="cancelRun"
      @resume="resumeRun"
    />

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="run-summary-grid">
      <article class="summary-card">
        <div class="summary-label">Run ID</div>
        <div class="summary-value mono">{{ run?.id || '-' }}</div>
      </article>
      <article class="summary-card">
        <div class="summary-label">事件数量</div>
        <div class="summary-value">{{ runEvents.length }}</div>
      </article>
      <article class="summary-card">
        <div class="summary-label">步骤数量</div>
        <div class="summary-value">{{ steps.length }}</div>
      </article>
      <article class="summary-card">
        <div class="summary-label">工具调用</div>
        <div class="summary-value">{{ toolCalls.length }}</div>
      </article>
    </section>

    <section v-if="run?.finalOutput" class="final-output card">
      <div class="section-head">
        <div>
          <h2>Final Output</h2>
          <p>当前 runtime 写入到 `agent_runs.final_output` 的内容。</p>
        </div>
      </div>
      <pre>{{ run.finalOutput }}</pre>
    </section>

    <section v-if="run?.status === 'waiting_user' || run?.status === 'failed' || run?.status === 'cancelled'" class="resume-panel card">
      <div class="section-head">
        <div>
          <h2>继续执行</h2>
          <p>如果 run 处于等待、失败或取消状态，可以补充输入后继续。</p>
        </div>
      </div>
      <div class="resume-form">
        <textarea
          v-model="resumeMessage"
          class="input resume-textarea"
          rows="4"
          placeholder="可选：覆盖 message 字段后继续执行"
        ></textarea>
        <button type="button" class="btn btn-primary" @click="resumeRun" :disabled="resumeLoading">
          {{ resumeLoading ? '继续中...' : '继续运行' }}
        </button>
      </div>
    </section>

    <section class="detail-grid">
      <div class="detail-main">
        <AgentTimeline :events="runEvents" />
      </div>

      <aside class="detail-side">
        <AgentPlanPanel :plan="plan" />
      </aside>
    </section>

    <AgentStepList :steps="steps" :tool-calls="toolCalls" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentPlanPanel from '@/components/agent/AgentPlanPanel.vue'
import AgentRunHeader from '@/components/agent/AgentRunHeader.vue'
import AgentStepList from '@/components/agent/AgentStepList.vue'
import AgentTimeline from '@/components/agent/AgentTimeline.vue'
import { useAgentsStore } from '@/store/agents'
import { useToastStore } from '@/store/toast'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const toastStore = useToastStore()

const resumeMessage = ref('')
const resumeLoading = ref(false)

const run = computed(() => agentsStore.currentRun)
const agent = computed(() => agentsStore.currentAgent)
const runEvents = computed(() => agentsStore.runEvents)
const steps = computed(() => agentsStore.steps)
const toolCalls = computed(() => agentsStore.toolCalls)
const plan = computed(() => agentsStore.plan)
const errorMessage = computed(() => agentsStore.error || '')

const loadRun = async () => {
  const runId = String(route.params.run_id || '')
  if (!runId) {
    router.push('/agents')
    return
  }

  const currentRun = await agentsStore.openRun(runId, { stream: true })
  if (currentRun?.agentDefinitionId) {
    await agentsStore.fetchAgent(currentRun.agentDefinitionId)
  }
}

const refreshRun = async () => {
  try {
    await loadRun()
    toastStore.showToast({ type: 'success', message: 'Run 已刷新' })
  } catch (error) {
    console.error('Failed to refresh run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '刷新 run 失败' })
  }
}

const cancelRun = async () => {
  if (!run.value?.id) return
  try {
    await agentsStore.cancelRun(run.value.id)
    toastStore.showToast({ type: 'success', message: 'Run 已取消' })
  } catch (error) {
    console.error('Failed to cancel run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '取消失败' })
  }
}

const resumeRun = async () => {
  if (!run.value?.id) return
  resumeLoading.value = true
  try {
    const patch = resumeMessage.value.trim()
      ? { message: resumeMessage.value.trim() }
      : {}
    await agentsStore.resumeRun(run.value.id, patch)
    toastStore.showToast({ type: 'success', message: 'Run 已继续执行' })
    resumeMessage.value = ''
  } catch (error) {
    console.error('Failed to resume run:', error)
    toastStore.showToast({ type: 'error', message: agentsStore.error || '继续运行失败' })
  } finally {
    resumeLoading.value = false
  }
}

watch(() => route.params.run_id, async () => {
  try {
    await loadRun()
  } catch (error) {
    console.error('Failed to load run detail:', error)
  }
})

onMounted(async () => {
  try {
    await loadRun()
  } catch (error) {
    console.error('Failed to initialize run detail:', error)
  }
})

onUnmounted(() => {
  agentsStore.stopRunStream()
})
</script>

<style scoped>
.run-detail-page {
  padding: 28px;
  display: grid;
  gap: 24px;
}

.error-banner {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.run-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  padding: 18px 20px;
  border-radius: 22px;
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.12);
  box-shadow: var(--shadow-sm);
}

.summary-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
}

.summary-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: var(--gray-900);
}

.summary-value.mono {
  font-size: 14px;
  font-family: var(--font-mono);
  word-break: break-all;
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

.final-output pre {
  margin-top: 16px;
  padding: 16px;
  border-radius: 18px;
  background: rgba(13, 13, 13, 0.04);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-size: 14px;
}

.resume-form {
  margin-top: 16px;
  display: grid;
  gap: 12px;
}

.resume-textarea {
  resize: vertical;
  min-height: 120px;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.85fr);
  gap: 24px;
}

.detail-main,
.detail-side {
  min-width: 0;
}

@media (max-width: 1180px) {
  .run-summary-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .run-detail-page {
    padding: 18px;
  }

  .card {
    padding: 20px;
    border-radius: 24px;
  }

  .summary-value {
    font-size: 24px;
  }
}
</style>
