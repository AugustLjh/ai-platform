<template>
  <section class="timeline-panel">
    <div class="panel-head">
      <div>
        <h3>运行时间线</h3>
        <p>基于 run events 的顺序回放，可实时更新。</p>
      </div>
      <span class="panel-count">{{ events.length }}</span>
    </div>

    <div v-if="events.length === 0" class="empty-state">
      当前没有可展示的事件。
    </div>

    <ol v-else class="timeline-list">
      <li v-for="event in events" :key="event.id" class="timeline-item">
        <div :class="['timeline-dot', toneClass(event)]"></div>
        <div :class="['timeline-card', toneClass(event)]">
          <div class="timeline-card-head">
            <div class="timeline-title">{{ event.eventType }}</div>
            <div class="timeline-seq">#{{ event.sequence }}</div>
          </div>
          <div class="timeline-summary">{{ summariseEvent(event) }}</div>
          <div class="timeline-time">{{ formatTime(event.createdAt) }}</div>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup>
import { summarizeTimelineEvent } from '@/utils/agentRunTree'

const props = defineProps({
  events: {
    type: Array,
    default: () => []
  }
})

const formatTime = (value) => {
  if (!value) return '未知时间'
  return new Date(value).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const summariseEvent = (event) => summarizeTimelineEvent(event)

const toneClass = (event) => {
  const type = String(event?.eventType || '')
  if (type.includes('failed') || type.includes('cancelled')) return 'danger'
  if (type.includes('waiting_user')) return 'warning'
  if (type.includes('completed')) return 'success'
  return 'neutral'
}
</script>

<style scoped>
.timeline-panel {
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

.timeline-list {
  list-style: none;
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  margin-top: 18px;
  border-radius: 50%;
  box-shadow: 0 0 0 5px rgba(16, 163, 127, 0.08);
}

.timeline-dot.neutral {
  background: linear-gradient(135deg, var(--primary-500) 0%, #6ee7b7 100%);
}

.timeline-dot.warning {
  background: linear-gradient(135deg, #f59e0b 0%, #fcd34d 100%);
  box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.1);
}

.timeline-dot.danger {
  background: linear-gradient(135deg, #ef4444 0%, #fca5a5 100%);
  box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.1);
}

.timeline-dot.success {
  background: linear-gradient(135deg, #10b981 0%, #86efac 100%);
}

.timeline-card {
  border: 1px solid var(--gray-200);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcfb 100%);
  max-height: 240px;
  overflow: auto;
}

.timeline-card.warning {
  border-color: rgba(245, 158, 11, 0.22);
  background: linear-gradient(180deg, #fffdf7 0%, #ffffff 100%);
}

.timeline-card.danger {
  border-color: rgba(239, 68, 68, 0.22);
  background: linear-gradient(180deg, #fffafa 0%, #ffffff 100%);
}

.timeline-card.success {
  border-color: rgba(16, 185, 129, 0.18);
}

.timeline-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.timeline-title {
  font-weight: 700;
  color: var(--gray-900);
}

.timeline-seq {
  font-size: 12px;
  color: var(--gray-500);
}

.timeline-summary {
  margin-top: 8px;
  color: var(--gray-700);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.timeline-time {
  margin-top: 10px;
  color: var(--gray-500);
  font-size: 12px;
}
</style>
