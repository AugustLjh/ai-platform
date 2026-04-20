<template>
  <div class="cost-page">
    <header class="cost-header">
      <div>
        <p class="eyebrow">Cost Analytics</p>
        <h1>成本统计</h1>
        <p class="header-copy">
          聚合查看租户累计成本与各模型消耗。低质量样本仍只记录在数据库，前端暂不展示。
        </p>
      </div>
      <div class="header-actions">
        <label class="filter-field">
          <span>知识库范围</span>
          <select v-model="selectedKnowledgeBaseId" :disabled="knowledgeLoading || loading">
            <option value="">全部知识库</option>
            <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
              {{ kb.name }}
            </option>
          </select>
        </label>
        <button class="btn-refresh" type="button" :disabled="loading" @click="fetchUsageStats">
          {{ loading ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
    </header>

    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <section class="summary-grid">
      <article class="summary-card primary">
        <div class="summary-label">租户累计成本</div>
        <div class="summary-value">${{ formatCurrency(tenantSummary.total_cost) }}</div>
        <div class="summary-meta">
          <span>{{ formatTokenCount(tenantSummary.total_tokens) }} tokens</span>
          <span>{{ tenantSummary.request_count || 0 }} 次回答</span>
        </div>
      </article>

      <article class="summary-card">
        <div class="summary-label">当前用户累计成本</div>
        <div class="summary-value">${{ formatCurrency(userSummary.total_cost) }}</div>
        <div class="summary-meta">
          <span>{{ formatTokenCount(userSummary.total_tokens) }} tokens</span>
          <span>{{ userSummary.request_count || 0 }} 次回答</span>
        </div>
      </article>

      <article class="summary-card accent">
        <div class="summary-label">纳入统计模型数</div>
        <div class="summary-value">{{ modelStats.length }}</div>
        <div class="summary-meta">
          <span>按成本降序</span>
          <span v-if="selectedKnowledgeBaseName">{{ selectedKnowledgeBaseName }}</span>
          <span v-else>全部知识库</span>
        </div>
      </article>
    </section>

    <section class="table-panel">
      <div class="panel-head">
        <div>
          <h2>模型成本分布</h2>
          <p>按租户维度聚合模型成本、Tokens 与请求量。</p>
        </div>
      </div>

      <div v-if="loading" class="table-state">正在加载统计数据...</div>
      <div v-else-if="modelStats.length === 0" class="table-state">
        当前范围暂无成本数据
      </div>
      <div v-else class="table-wrap">
        <table class="cost-table">
          <thead>
            <tr>
              <th>模型</th>
              <th>成本</th>
              <th>Tokens</th>
              <th>请求量</th>
              <th>成本占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in modelStats" :key="item.key || item.label">
              <td>
                <div class="model-cell">
                  <strong>{{ item.label || 'unknown' }}</strong>
                  <span>{{ item.key || 'unknown' }}</span>
                </div>
              </td>
              <td>${{ formatCurrency(item.total_cost) }}</td>
              <td>{{ formatTokenCount(item.total_tokens) }}</td>
              <td>{{ item.request_count || 0 }}</td>
              <td>
                <div class="share-cell">
                  <div class="share-bar">
                    <span :style="{ width: `${calcShare(item.total_cost)}%` }"></span>
                  </div>
                  <span>{{ calcShare(item.total_cost).toFixed(1) }}%</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { chatAPI } from '@/api'
import { useKnowledgeStore } from '@/store/knowledge'

const knowledgeStore = useKnowledgeStore()

const loading = ref(false)
const error = ref('')
const usageStats = ref(null)
const selectedKnowledgeBaseId = ref('')

const knowledgeBases = computed(() => knowledgeStore.knowledgeBases)
const knowledgeLoading = computed(() => knowledgeStore.loading)
const tenantSummary = computed(() => usageStats.value?.current_tenant || {})
const userSummary = computed(() => usageStats.value?.current_user || {})
const modelStats = computed(() => usageStats.value?.by_model || [])
const selectedKnowledgeBaseName = computed(() => {
  if (!selectedKnowledgeBaseId.value) return ''
  const target = knowledgeBases.value.find((item) => item.id === selectedKnowledgeBaseId.value)
  return target?.name || ''
})

const fetchUsageStats = async () => {
  loading.value = true
  error.value = ''

  try {
    const { data } = await chatAPI.getUsageStats(selectedKnowledgeBaseId.value)
    usageStats.value = data
  } catch (err) {
    console.error('Failed to load usage stats:', err)
    error.value = err.response?.data?.error || err.response?.data?.detail || '加载成本统计失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await knowledgeStore.fetchKnowledgeBases(1, 100)
  } catch (err) {
    console.error('Failed to load knowledge bases:', err)
  }

  await fetchUsageStats()
})

watch(selectedKnowledgeBaseId, () => {
  fetchUsageStats()
})

const formatCurrency = (value) => {
  const parsed = Number(value || 0)
  return parsed.toFixed(4)
}

const formatTokenCount = (value) => {
  const parsed = Number(value || 0)
  if (parsed >= 1000000) {
    return `${(parsed / 1000000).toFixed(1)}m`
  }
  if (parsed >= 1000) {
    return `${(parsed / 1000).toFixed(1)}k`
  }
  return `${parsed}`
}

const calcShare = (value) => {
  const total = Number(tenantSummary.value?.total_cost || 0)
  if (!total) return 0
  return Math.min(100, (Number(value || 0) / total) * 100)
}
</script>

<style scoped>
.cost-page {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 32px;
  background:
    radial-gradient(circle at top right, rgba(16, 163, 127, 0.08), transparent 24rem),
    linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.cost-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #0f766e;
}

.cost-header h1 {
  margin: 0;
  font-size: 32px;
  color: #0f172a;
}

.header-copy {
  max-width: 720px;
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.7;
}

.header-actions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 220px;
}

.filter-field span {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.filter-field select {
  min-height: 42px;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 0 14px;
  background: rgba(255, 255, 255, 0.92);
  color: #0f172a;
}

.btn-refresh {
  min-height: 42px;
  border: none;
  border-radius: 12px;
  padding: 0 16px;
  background: #0f172a;
  color: #f8fafc;
  font-weight: 600;
  cursor: pointer;
}

.btn-refresh:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.error-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid #fecaca;
  background: #fff1f2;
  color: #9f1239;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card {
  padding: 20px 22px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(203, 213, 225, 0.9);
  box-shadow: 0 20px 45px rgba(15, 23, 42, 0.08);
}

.summary-card.primary {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-color: transparent;
}

.summary-card.accent {
  background: linear-gradient(135deg, #ecfeff 0%, #f0fdfa 100%);
}

.summary-card.primary .summary-label,
.summary-card.primary .summary-value,
.summary-card.primary .summary-meta {
  color: #f8fafc;
}

.summary-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.summary-value {
  margin-top: 10px;
  font-size: 32px;
  font-weight: 700;
  color: #0f172a;
}

.summary-meta {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 13px;
}

.table-panel {
  border-radius: 24px;
  border: 1px solid rgba(203, 213, 225, 0.9);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 20px 45px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.panel-head {
  padding: 22px 24px 16px;
  border-bottom: 1px solid #e2e8f0;
}

.panel-head h2 {
  margin: 0;
  font-size: 20px;
  color: #0f172a;
}

.panel-head p {
  margin: 6px 0 0;
  color: #64748b;
}

.table-state {
  padding: 48px 24px;
  text-align: center;
  color: #64748b;
}

.table-wrap {
  overflow-x: auto;
}

.cost-table {
  width: 100%;
  border-collapse: collapse;
}

.cost-table th,
.cost-table td {
  padding: 16px 24px;
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  vertical-align: middle;
}

.cost-table th {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.cost-table tbody tr:hover {
  background: rgba(248, 250, 252, 0.9);
}

.model-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-cell strong {
  color: #0f172a;
}

.model-cell span {
  font-size: 12px;
  color: #64748b;
}

.share-cell {
  min-width: 170px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.share-bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.share-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e 0%, #14b8a6 100%);
}

@media (max-width: 960px) {
  .cost-page {
    padding: 24px 16px;
  }

  .cost-header {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
