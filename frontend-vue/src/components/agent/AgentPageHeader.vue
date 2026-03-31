<template>
  <section class="agent-header">
    <div class="agent-header-main">
      <router-link to="/agents" class="back-link">返回智能体列表</router-link>
      <div class="header-kicker">{{ kicker }}</div>
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
    </div>

    <div class="agent-header-actions">
      <slot name="actions" />
    </div>
  </section>

  <nav class="agent-tabs" aria-label="智能体页面导航">
    <router-link :to="chatLink" class="agent-tab">聊天</router-link>
    <router-link :to="basicLink" class="agent-tab">基础设置</router-link>
    <router-link :to="extensionsLink" class="agent-tab">扩展绑定</router-link>
    <router-link :to="runsLink" class="agent-tab">运行记录</router-link>
  </nav>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  agentId: {
    type: String,
    default: ''
  },
  kicker: {
    type: String,
    default: 'Agent Workspace'
  },
  title: {
    type: String,
    default: '智能体'
  },
  description: {
    type: String,
    default: ''
  }
})

const chatLink = computed(() => props.agentId ? `/agents/${props.agentId}` : '/agents')
const basicLink = computed(() => props.agentId ? `/agents/${props.agentId}/settings/basic` : '/agents')
const extensionsLink = computed(() => props.agentId ? `/agents/${props.agentId}/settings/extensions` : '/agents')
const runsLink = computed(() => props.agentId ? `/agents/${props.agentId}/runs` : '/agents')
</script>

<style scoped>
.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(245, 158, 11, 0.18) 0%, rgba(245, 158, 11, 0) 30%),
    linear-gradient(135deg, #0f172a 0%, #114b5f 55%, #166534 100%);
  color: white;
}

.back-link {
  display: inline-flex;
  margin-bottom: 12px;
  color: rgba(255, 255, 255, 0.82);
}

.header-kicker {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
}

.agent-header h1 {
  margin-top: 10px;
  font-size: 34px;
}

.agent-header p {
  margin-top: 10px;
  max-width: 760px;
  color: rgba(255, 255, 255, 0.82);
}

.agent-header-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-tabs {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 0 18px;
  border-radius: var(--radius-full);
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: white;
  color: var(--gray-700);
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-base), border-color var(--transition-base), color var(--transition-base);
}

.agent-tab:hover {
  transform: translateY(-1px);
  border-color: rgba(13, 148, 136, 0.35);
  color: #0f766e;
}

.agent-tab.router-link-exact-active {
  border-color: rgba(13, 148, 136, 0.45);
  background: rgba(13, 148, 136, 0.08);
  color: #0f766e;
  font-weight: 700;
}

@media (max-width: 900px) {
  .agent-header {
    flex-direction: column;
  }
}
</style>
