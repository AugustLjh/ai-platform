<template>
  <section class="tree-panel">
    <div class="panel-head">
      <div>
        <h3>Run Tree</h3>
        <p>展示主 run 与 child run 的层级关系，而不是把所有委派事件平铺进时间线。</p>
      </div>
      <span class="panel-count">{{ invocationCount }}</span>
    </div>

    <div v-if="!root" class="empty-state">
      当前没有可展示的 child run。
    </div>

    <ol v-else class="tree-list">
      <AgentRunTreeNode :node="root" :is-root="true" />
    </ol>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { collectRunTreeInvocations } from '@/utils/agentRunTree'
import AgentRunTreeNode from './AgentRunTreeNode.vue'

const props = defineProps({
  root: {
    type: Object,
    default: null
  }
})

const invocationCount = computed(() => collectRunTreeInvocations(props.root).length)
</script>

<style scoped>
.tree-panel {
  background: white;
  border: 1px solid rgba(16, 163, 127, 0.14);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow-sm);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.panel-head h3 {
  margin: 0 0 6px;
  font-size: 18px;
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

.tree-list {
  list-style: none;
  display: grid;
  gap: 14px;
}
</style>
