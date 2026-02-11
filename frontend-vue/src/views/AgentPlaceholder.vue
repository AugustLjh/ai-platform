<template>
  <div class="agent-container">
    <div class="agent-content">
      <div class="agent-card">
        <div class="agent-icon">🤖</div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
        <div class="agent-status">该智能体正在建设中，敬请期待。</div>
        <router-link to="/chat" class="btn-back">返回聊天</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const agentMap = {
  writing: {
    title: '写作助手',
    description: '提供文章、报告、营销文案等多类型写作能力。'
  },
  knowledge: {
    title: '知识问答',
    description: '针对具体问题进行检索与解释，提供可靠答案。'
  },
  code: {
    title: '代码分析',
    description: '帮助你分析代码、定位问题并给出优化建议。'
  },
  creative: {
    title: '创意灵感',
    description: '提供灵感碰撞与创意延展，激发更多想法。'
  }
}

const agentInfo = computed(() => agentMap[route.params.agent] || {
  title: '智能体',
  description: '该智能体正在规划中。'
})

const title = computed(() => agentInfo.value.title)
const description = computed(() => agentInfo.value.description)
</script>

<style scoped>
.agent-container {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gray-50);
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.agent-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.agent-card {
  background: white;
  padding: 40px;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  text-align: center;
  max-width: 520px;
  width: 100%;
}

.agent-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.agent-card h1 {
  font-size: 28px;
  margin: 0 0 12px 0;
  color: var(--gray-900);
}

.agent-card p {
  color: var(--gray-600);
  margin-bottom: 20px;
}

.agent-status {
  font-size: 14px;
  color: var(--gray-500);
  margin-bottom: 24px;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 18px;
  border-radius: var(--radius-md);
  background: var(--gradient-primary);
  color: white;
  text-decoration: none;
  font-weight: 600;
}
</style>
