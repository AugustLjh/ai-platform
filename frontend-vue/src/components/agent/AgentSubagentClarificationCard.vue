<template>
  <section v-if="entry" class="clarification-card">
    <div class="card-head">
      <div>
        <div class="card-kicker">Subagent Clarification</div>
        <h3>{{ entry.question || '子能力正在等待补充信息' }}</h3>
        <p class="card-summary">
          <span v-if="entry.targetName">{{ entry.targetName }}</span>
          <span v-if="entry.targetName && entry.childRunId"> · </span>
          <span v-if="entry.childRunId" class="mono">child {{ entry.childRunId.slice(0, 8) }}</span>
        </p>
      </div>
      <span class="status-pill">等待补充</span>
    </div>

    <div class="card-body">
      <div v-if="entry.reason" class="info-block muted-block">
        <span class="block-label">原因</span>
        <p>{{ entry.reason }}</p>
      </div>

      <div v-if="entry.requiredFields.length > 0" class="info-block">
        <span class="block-label">需要补充</span>
        <ul>
          <li v-for="field in entry.requiredFields" :key="field">{{ field }}</li>
        </ul>
      </div>

      <div v-if="entry.responseHint" class="info-block">
        <span class="block-label">回答建议</span>
        <p>{{ entry.responseHint }}</p>
      </div>

      <div v-if="entry.progress.hasData" class="info-block progress-block">
        <div class="inline-head">
          <span class="block-label">当前进度</span>
          <span :class="['mini-pill', `state-${entry.progress.state}`]">
            {{ progressStateLabel(entry.progress.state) }}
          </span>
        </div>
        <p v-if="entry.progress.summary">{{ entry.progress.summary }}</p>
        <ul v-if="entry.progress.completedItems.length > 0">
          <li v-for="item in entry.progress.completedItems" :key="`done-${item}`">已完成：{{ item }}</li>
        </ul>
        <ul v-if="entry.progress.pendingItems.length > 0">
          <li v-for="item in entry.progress.pendingItems" :key="`pending-${item}`">待处理：{{ item }}</li>
        </ul>
        <p v-if="entry.progress.nextAction" class="next-action">Next: {{ entry.progress.nextAction }}</p>
      </div>

      <div v-if="entry.governance.hasData" class="info-block governance-block">
        <div class="inline-head">
          <span class="block-label">治理约束</span>
          <span v-if="entry.governance.protocolVersion" class="mini-pill governance-pill">
            {{ entry.governance.protocolVersion }}
          </span>
        </div>
        <p v-if="entry.governanceSummary">{{ entry.governanceSummary }}</p>
        <ul v-if="entry.governance.enforcement.hardLimits.length > 0">
          <li v-for="limit in entry.governance.enforcement.hardLimits" :key="limit">硬限制：{{ limit }}</li>
        </ul>
        <ul v-if="entry.governance.enforcement.advisoryLimits.length > 0">
          <li v-for="limit in entry.governance.enforcement.advisoryLimits" :key="limit">建议限制：{{ limit }}</li>
        </ul>
        <ul v-if="entry.governanceBudgetLines.length > 0">
          <li v-for="line in entry.governanceBudgetLines" :key="line">预算：{{ line }}</li>
        </ul>
        <p v-if="entry.waitingUserPathSummary" class="secondary-copy">
          waiting-user 链路：{{ entry.waitingUserPathSummary }}
        </p>
        <p v-if="entry.governance.waitingUserPropagation" class="secondary-copy">
          waiting-user 策略：{{ entry.governance.waitingUserPropagation }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import {
  buildPendingSubagentClarificationEntry,
  progressStateLabel
} from '@/utils/agentRunTree'

const props = defineProps({
  run: {
    type: Object,
    default: null
  }
})

const entry = computed(() => buildPendingSubagentClarificationEntry(props.run))
</script>

<style scoped>
.clarification-card {
  width: min(820px, 100%);
  max-width: 100%;
  border-radius: 26px;
  padding: 20px 22px;
  border: 1px solid rgba(245, 158, 11, 0.22);
  background:
    radial-gradient(circle at top right, rgba(251, 191, 36, 0.14), transparent 32%),
    linear-gradient(180deg, #fffdf7 0%, #ffffff 100%);
  box-shadow: 0 20px 40px rgba(245, 158, 11, 0.08);
}

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.card-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #b45309;
  margin-bottom: 8px;
}

.card-head h3 {
  margin: 0;
  font-size: 24px;
  line-height: 1.3;
  color: #1f2937;
}

.card-summary {
  margin-top: 8px;
  color: #92400e;
  font-size: 13px;
}

.mono {
  font-family: var(--font-mono);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.card-body {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.info-block {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(245, 158, 11, 0.12);
}

.muted-block {
  background: rgba(255, 251, 235, 0.72);
}

.progress-block {
  background: rgba(236, 253, 245, 0.72);
  border-color: rgba(16, 185, 129, 0.16);
}

.governance-block {
  background: rgba(248, 250, 252, 0.92);
  border-color: rgba(15, 23, 42, 0.08);
}

.inline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.block-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.info-block p {
  margin: 0;
  color: #334155;
  line-height: 1.7;
}

.info-block ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #334155;
  line-height: 1.7;
}

.mini-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
}

.mini-pill.state-blocked {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.mini-pill.state-completed {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.mini-pill.state-in_progress,
.mini-pill.state-requested {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.mini-pill.state-failed {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.governance-pill {
  background: rgba(14, 116, 144, 0.1);
  color: #0f766e;
}

.secondary-copy,
.next-action {
  margin-top: 8px !important;
  color: #475569 !important;
  font-size: 13px;
}

@media (max-width: 768px) {
  .clarification-card {
    padding: 18px;
  }

  .card-head {
    flex-direction: column;
  }

  .card-head h3 {
    font-size: 20px;
  }
}
</style>
