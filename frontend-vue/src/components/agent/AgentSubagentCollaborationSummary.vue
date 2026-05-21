<template>
  <section class="collaboration-panel">
    <div class="panel-head">
      <div>
        <h3>协作概览</h3>
        <p>压缩展示 subagent 时间线、提升产物和 reviewer 阻断状态。</p>
      </div>
      <span class="panel-count">{{ summary.totalInvocations }}</span>
    </div>

    <div v-if="!summary.hasData" class="empty-state">
      当前没有可汇总的 subagent 协作数据。
    </div>

    <template v-else>
      <div class="metric-grid">
        <div class="metric-item">
          <span>已完成</span>
          <strong>{{ summary.completedCount }}</strong>
        </div>
        <div class="metric-item">
          <span>进行中</span>
          <strong>{{ summary.activeCount }}</strong>
        </div>
        <div class="metric-item">
          <span>失败/取消</span>
          <strong>{{ summary.failedCount }}</strong>
        </div>
        <div :class="['metric-item', { danger: summary.reviewBlockCount > 0 }]">
          <span>Reviewer 阻断</span>
          <strong>{{ summary.reviewBlockCount }}</strong>
        </div>
      </div>

      <div v-if="summary.reviewBlocks.length > 0" class="block-list">
        <article v-for="block in summary.reviewBlocks" :key="block.id" class="block-item">
          <div class="block-head">
            <strong>{{ block.target }}</strong>
            <span>{{ block.blockingFindingCount }} 阻塞 / {{ block.findingCount }} findings</span>
          </div>
          <p v-if="block.summary">{{ block.summary }}</p>
          <div v-if="block.recoveryActions.length > 0" class="chip-list">
            <span v-for="action in block.recoveryActions.slice(0, 3)" :key="action" class="chip danger">
              {{ action }}
            </span>
          </div>
        </article>
      </div>

      <div v-if="artifactTypeRows.length > 0" class="artifact-summary">
        <div class="section-label">产物汇总</div>
        <div class="chip-list">
          <span v-for="row in artifactTypeRows" :key="row.label" class="chip">
            {{ row.label }} {{ row.count }}
          </span>
        </div>
      </div>

      <ol v-if="summary.timeline.length > 0" class="compact-timeline">
        <li v-for="item in summary.timeline" :key="item.id" class="timeline-row">
          <span :class="['timeline-dot', item.tone]"></span>
          <div>
            <div class="timeline-title">
              <strong>{{ item.target }}</strong>
              <span>{{ item.statusLabel }}</span>
              <span v-if="item.artifactCount > 0">{{ item.artifactCount }} 产物</span>
            </div>
            <p v-if="item.summary">{{ item.summary }}</p>
          </div>
        </li>
      </ol>

      <details v-if="summary.eventTimeline.length > 0" class="event-details">
        <summary>最近 subagent 事件 {{ summary.eventTimeline.length }} 条</summary>
        <ol class="event-list">
          <li v-for="event in summary.eventTimeline" :key="event.id">
            <span :class="['event-tone', event.tone]">{{ event.eventType }}</span>
            <p>{{ event.summary }}</p>
          </li>
        </ol>
      </details>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { buildSubagentCollaborationSummary } from '@/utils/agentRunTree'

const props = defineProps({
  runTreeInvocations: {
    type: Array,
    default: () => []
  },
  resolvedInvocations: {
    type: Array,
    default: () => []
  },
  artifacts: {
    type: Array,
    default: () => []
  },
  events: {
    type: Array,
    default: () => []
  }
})

const summary = computed(() => buildSubagentCollaborationSummary({
  runTreeInvocations: props.runTreeInvocations,
  resolvedInvocations: props.resolvedInvocations,
  artifacts: props.artifacts,
  events: props.events
}))

const artifactTypeRows = computed(() => (
  Object.entries(summary.value.artifactTypeCounts || {})
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
))
</script>

<style scoped>
.collaboration-panel {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 16px;
  box-shadow: var(--shadow-sm);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.panel-head h3 {
  margin: 0 0 4px;
  font-size: 17px;
}

.panel-head p {
  color: var(--gray-600);
  font-size: 13px;
  line-height: 1.45;
}

.panel-count {
  min-width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.empty-state {
  padding: 16px;
  border-radius: 12px;
  background: var(--gray-50);
  color: var(--gray-500);
  text-align: center;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
}

.metric-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  padding: 10px;
  background: #fbfcfc;
}

.metric-item span {
  display: block;
  color: var(--gray-500);
  font-size: 12px;
  margin-bottom: 4px;
}

.metric-item strong {
  color: #0f172a;
  font-size: 18px;
}

.metric-item.danger {
  border-color: rgba(239, 68, 68, 0.24);
  background: #fffafa;
}

.metric-item.danger strong {
  color: #b91c1c;
}

.block-list,
.artifact-summary,
.compact-timeline,
.event-details {
  margin-top: 12px;
}

.block-list {
  display: grid;
  gap: 8px;
}

.block-item {
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 12px;
  padding: 10px;
  background: #fffafa;
}

.block-head,
.timeline-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.block-head span,
.timeline-title span {
  color: var(--gray-500);
  font-size: 12px;
}

.block-item p,
.timeline-row p,
.event-list p {
  margin-top: 6px;
  color: var(--gray-700);
  line-height: 1.55;
  word-break: break-word;
}

.section-label {
  color: var(--gray-500);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.chip {
  border-radius: 999px;
  padding: 5px 9px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.chip.danger {
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
}

.compact-timeline,
.event-list {
  list-style: none;
  display: grid;
  gap: 10px;
}

.timeline-row {
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: 10px;
}

.timeline-dot {
  width: 9px;
  height: 9px;
  margin-top: 6px;
  border-radius: 50%;
  background: #64748b;
}

.timeline-dot.success {
  background: #10b981;
}

.timeline-dot.warning {
  background: #f59e0b;
}

.timeline-dot.danger {
  background: #ef4444;
}

.event-details {
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  padding-top: 10px;
}

.event-details summary {
  cursor: pointer;
  color: var(--gray-700);
  font-weight: 700;
}

.event-list {
  margin-top: 10px;
}

.event-tone {
  display: inline-flex;
  margin-bottom: 2px;
  color: var(--gray-500);
  font-size: 12px;
  font-family: var(--font-mono);
}

.event-tone.success {
  color: #047857;
}

.event-tone.warning {
  color: #92400e;
}

.event-tone.danger {
  color: #b91c1c;
}
</style>
