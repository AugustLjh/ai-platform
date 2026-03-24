<template>
  <div class="eval-page">
    <div class="eval-container">
      <div class="page-header">
        <div>
          <div class="title-row">
            <button class="back-btn" @click="goToSettings" title="返回">←</button>
            <h1>检索评测中心</h1>
          </div>
          <p class="subtitle">管理测试集、保存评测运行、对比不同检索配置，并将评测结果一键应用为生产配置。</p>
        </div>
      </div>

      <div v-if="pageError" class="error-banner">
        <span class="error-icon">⚠️</span>
        <span>{{ pageError }}</span>
      </div>

      <section class="card">
        <div class="section-head">
          <div>
            <h2>快速召回测试</h2>
            <p>用于即时验证单个问题的当前召回效果。</p>
          </div>
        </div>

        <div class="form-row">
          <label>测试问题</label>
          <textarea v-model="quickTest.query" placeholder="输入一个问题，测试当前检索设置的召回效果"></textarea>
        </div>

        <div class="form-grid">
          <div class="form-row">
            <label>测试 Top K</label>
            <input v-model.number="quickTest.topK" type="number" min="1" max="50" />
          </div>
          <div class="form-row">
            <label>测试阈值</label>
            <input v-model.number="quickTest.scoreThreshold" type="number" min="0" max="1" step="0.01" />
          </div>
        </div>

        <button class="btn-primary" :disabled="quickTesting || !quickTest.query.trim()" @click="runQuickTest">
          {{ quickTesting ? '测试中...' : '开始测试' }}
        </button>

        <div v-if="quickTestMeta" class="meta-strip">
          <span>检索方式：{{ quickTestMeta.retrieval_method }}</span>
          <span>Top K：{{ quickTestMeta.top_k }}</span>
          <span>阈值：{{ quickTestMeta.score_threshold }}</span>
          <span>命中：{{ quickTestMeta.total }}</span>
        </div>

        <div v-if="quickTestResults.length" class="result-list">
          <div v-for="(item, index) in quickTestResults" :key="item.document.id" class="result-card">
            <div class="result-head">
              <strong>{{ index + 1 }}. {{ item.document.title }}</strong>
              <span>Score {{ item.score.toFixed(4) }}</span>
            </div>
            <div class="result-sub">{{ item.document.source || '-' }}</div>
            <div v-for="segment in item.matched_segments" :key="`${item.document.id}-${segment.segment_index}`" class="segment-card">
              <div class="segment-head">
                <span>#{{ segment.segment_index }}</span>
                <span v-if="segment.citation_label">{{ segment.citation_label }}</span>
                <span v-else-if="segment.section_title">{{ segment.section_title }}</span>
                <span>{{ segment.start_offset }} - {{ segment.end_offset }}</span>
              </div>
              <div class="segment-text">{{ segment.content }}</div>
            </div>
          </div>
        </div>
      </section>

      <div class="two-column">
        <section class="card">
          <div class="section-head">
            <div>
              <h2>测试集管理</h2>
              <p>用固定测试问题和期望文档，形成可复盘的评测样本集。</p>
            </div>
            <button class="btn-secondary" @click="resetDatasetForm">新建测试集</button>
          </div>

          <div class="dataset-list" v-if="datasets.length">
            <button
              v-for="dataset in datasets"
              :key="dataset.id"
              :class="['dataset-item', { active: dataset.id === datasetForm.id }]"
              @click="editDataset(dataset)"
            >
              <strong>{{ dataset.name }}</strong>
              <span>{{ (dataset.cases || []).length }} 条样本</span>
            </button>
          </div>
          <div v-else class="empty-state">还没有测试集，先创建一个。</div>

          <div class="form-row">
            <label>测试集名称</label>
            <input v-model="datasetForm.name" type="text" placeholder="例如：客服 FAQ 基线集" />
          </div>

          <div class="form-row">
            <label>描述</label>
            <textarea v-model="datasetForm.description" placeholder="说明这个测试集覆盖的业务场景"></textarea>
          </div>

          <div class="cases-head">
            <h3>测试样本</h3>
            <button class="btn-secondary" @click="addCase">添加样本</button>
          </div>

          <div v-if="datasetForm.cases.length" class="case-list">
            <div v-for="(item, index) in datasetForm.cases" :key="item.localId" class="case-card">
              <div class="case-card-head">
                <strong>样本 {{ index + 1 }}</strong>
                <button class="text-btn danger" @click="removeCase(index)">删除</button>
              </div>

              <div class="form-row">
                <label>问题</label>
                <textarea v-model="item.query" placeholder="输入测试问题"></textarea>
              </div>

              <div class="form-row">
                <label>期望命中文档</label>
                <select v-model="item.expectedDocumentIds" multiple size="6">
                  <option v-for="doc in documents" :key="doc.id" :value="doc.id">
                    {{ doc.title }}
                  </option>
                </select>
              </div>

              <div class="form-row">
                <label>备注</label>
                <input v-model="item.notes" type="text" placeholder="例如：应命中产品说明文档" />
              </div>
            </div>
          </div>
          <div v-else class="empty-state compact">至少添加 1 条测试样本。</div>

          <div class="action-row">
            <button
              class="btn-primary"
              :disabled="savingDataset || !datasetForm.name.trim() || !datasetForm.cases.length"
              @click="saveDataset"
            >
              {{ savingDataset ? '保存中...' : datasetForm.id ? '更新测试集' : '保存测试集' }}
            </button>
            <button
              v-if="datasetForm.id"
              class="btn-secondary danger"
              :disabled="savingDataset"
              @click="deleteDataset"
            >
              删除测试集
            </button>
          </div>
        </section>

        <section class="card">
          <div class="section-head">
            <div>
              <h2>发起评测</h2>
              <p>基于测试集保存一轮评测运行，用于后续对比和应用配置。</p>
            </div>
          </div>

          <div class="form-row">
            <label>选择测试集</label>
            <select v-model="runForm.testSetId">
              <option value="">请选择测试集</option>
              <option v-for="dataset in datasets" :key="dataset.id" :value="dataset.id">
                {{ dataset.name }}
              </option>
            </select>
          </div>

          <div class="form-row">
            <label>运行名称</label>
            <input v-model="runForm.name" type="text" placeholder="例如：Hybrid Top10 Rerank" />
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>检索方式</label>
              <select v-model="runForm.config.retrieval_method">
                <option value="">沿用生产配置</option>
                <option value="vector">向量检索</option>
                <option value="keyword">关键词检索</option>
                <option value="hybrid">混合检索</option>
              </select>
            </div>
            <div class="form-row">
              <label>Top K</label>
              <input v-model.number="runForm.config.top_k" type="number" min="1" max="50" />
            </div>
            <div class="form-row">
              <label>阈值</label>
              <input v-model.number="runForm.config.score_threshold" type="number" min="0" max="1" step="0.01" />
            </div>
            <div class="form-row">
              <label>Rerank</label>
              <select v-model="runForm.config.enable_rerank">
                <option value="">沿用生产配置</option>
                <option value="true">启用</option>
                <option value="false">关闭</option>
              </select>
            </div>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>向量候选数</label>
              <input v-model.number="runForm.config.vector_top_k" type="number" min="1" max="200" />
            </div>
            <div class="form-row">
              <label>关键词候选数</label>
              <input v-model.number="runForm.config.keyword_top_k" type="number" min="1" max="200" />
            </div>
            <div class="form-row">
              <label>融合算法</label>
              <select v-model="runForm.config.fusion_algorithm">
                <option value="">沿用生产配置</option>
                <option value="rrf">RRF</option>
              </select>
            </div>
            <div class="form-row">
              <label>RRF K</label>
              <input v-model.number="runForm.config.rrf_k" type="number" min="1" max="200" />
            </div>
          </div>

          <div class="form-grid">
            <div class="form-row">
              <label>向量权重</label>
              <input v-model.number="runForm.config.vector_weight" type="number" min="0" max="5" step="0.05" />
            </div>
            <div class="form-row">
              <label>关键词权重</label>
              <input v-model.number="runForm.config.keyword_weight" type="number" min="0" max="5" step="0.05" />
            </div>
            <div class="form-row">
              <label>最大候选数</label>
              <input v-model.number="runForm.config.max_candidates" type="number" min="1" max="300" />
            </div>
            <div class="form-row">
              <label>查询改写</label>
              <select v-model="runForm.config.query_rewrite">
                <option value="">沿用生产配置</option>
                <option value="true">启用</option>
                <option value="false">关闭</option>
              </select>
            </div>
          </div>

          <button class="btn-primary" :disabled="runningEval || !runForm.testSetId" @click="runEvaluation">
            {{ runningEval ? '评测中...' : '保存本次评测运行' }}
          </button>

          <div class="section-head run-history-head">
            <div>
              <h2>历史运行</h2>
              <p>选择 2 到 3 轮运行可直接对比核心指标。</p>
            </div>
          </div>

          <div v-if="runs.length" class="run-list">
            <div
              v-for="run in runs"
              :key="run.id"
              :class="['run-card', { active: selectedRunId === run.id }]"
            >
              <div class="run-card-top">
                <label class="run-check">
                  <input
                    type="checkbox"
                    :checked="compareRunIds.includes(run.id)"
                    @change="toggleCompare(run.id)"
                  />
                  对比
                </label>
                <button class="text-btn" @click="selectRun(run.id)">查看详情</button>
              </div>
              <strong>{{ run.name || '未命名运行' }}</strong>
              <span>{{ run.metadata?.test_set_name || run.test_set_id || '-' }}</span>
              <div class="run-metrics">
                <span>命中率 {{ formatPercent(run.summary?.hit_rate) }}</span>
                <span>首条命中率 {{ formatPercent(run.summary?.top_hit_rate) }}</span>
                <span>人工评分 {{ formatScore(run.summary?.avg_manual_score) }}</span>
              </div>
              <button class="btn-secondary slim" @click="applyRunConfig(run.id)">设为生产配置</button>
            </div>
          </div>
          <div v-else class="empty-state">还没有评测运行。</div>
        </section>
      </div>

      <section v-if="compareRuns.length" class="card">
        <div class="section-head">
          <div>
            <h2>运行对比</h2>
            <p>聚焦命中率、首条命中率和人工评分的差异。</p>
          </div>
        </div>

        <div class="compare-table">
          <div class="compare-row compare-head">
            <div>运行</div>
            <div>测试集</div>
            <div>检索方式</div>
            <div>Top K</div>
            <div>命中率</div>
            <div>首条命中率</div>
            <div>人工评分</div>
          </div>
          <div v-for="run in compareRuns" :key="run.id" class="compare-row">
            <div>{{ run.name || '未命名运行' }}</div>
            <div>{{ run.metadata?.test_set_name || '-' }}</div>
            <div>{{ run.config?.retrieval_method || '-' }}</div>
            <div>{{ run.config?.top_k || '-' }}</div>
            <div>{{ formatPercent(run.summary?.hit_rate) }}</div>
            <div>{{ formatPercent(run.summary?.top_hit_rate) }}</div>
            <div>{{ formatScore(run.summary?.avg_manual_score) }}</div>
          </div>
        </div>
      </section>

      <section v-if="selectedRun" class="card">
        <div class="section-head">
          <div>
            <h2>运行详情</h2>
            <p>{{ selectedRun.name || '未命名运行' }}，共 {{ selectedRun.summary?.total_cases || 0 }} 条样本。</p>
          </div>
        </div>

        <div class="meta-strip">
          <span>测试集：{{ selectedRun.metadata?.test_set_name || '-' }}</span>
          <span>命中率：{{ formatPercent(selectedRun.summary?.hit_rate) }}</span>
          <span>首条命中率：{{ formatPercent(selectedRun.summary?.top_hit_rate) }}</span>
          <span>人工评分：{{ formatScore(selectedRun.summary?.avg_manual_score) }}</span>
        </div>

        <div class="case-result-list">
          <div v-for="item in selectedRun.results || []" :key="item.case_id" class="case-result-card">
            <div class="case-result-head">
              <strong>{{ item.query }}</strong>
              <div class="badge-row">
                <span :class="['badge', item.hit ? 'success' : 'muted']">命中 {{ item.hit ? '是' : '否' }}</span>
                <span :class="['badge', item.top_hit ? 'success' : 'muted']">首条 {{ item.top_hit ? '是' : '否' }}</span>
              </div>
            </div>

            <div class="expected-docs">
              期望文档：
              <span v-if="item.expected_documents?.length">
                {{ item.expected_documents.map(doc => doc.title).join('，') }}
              </span>
              <span v-else>-</span>
            </div>

            <div class="inline-grid">
              <div class="form-row">
                <label>人工评分（0-5）</label>
                <input v-model.number="feedbackDrafts[item.case_id].manual_score" type="number" min="0" max="5" step="0.5" />
              </div>
              <div class="form-row">
                <label>备注</label>
                <input v-model="feedbackDrafts[item.case_id].manual_comment" type="text" placeholder="记录人工判断依据" />
              </div>
            </div>

            <button class="btn-secondary slim" @click="saveFeedback(item.case_id)" :disabled="savingFeedbackCaseId === item.case_id">
              {{ savingFeedbackCaseId === item.case_id ? '保存中...' : '保存评分' }}
            </button>

            <div v-if="item.results?.length" class="result-list compact">
              <div v-for="result in item.results" :key="`${item.case_id}-${result.document_id}`" class="result-card">
                <div class="result-head">
                  <strong>{{ result.title }}</strong>
                  <span>Score {{ Number(result.score || 0).toFixed(4) }}</span>
                </div>
                <div class="result-sub">{{ result.source || '-' }}</div>
                <div
                  v-for="segment in result.matched_segments || []"
                  :key="`${result.document_id}-${segment.segment_index}`"
                  class="segment-card"
                >
                  <div class="segment-head">
                    <span>#{{ segment.segment_index }}</span>
                    <span v-if="segment.citation_label">{{ segment.citation_label }}</span>
                    <span v-else-if="segment.section_title">{{ segment.section_title }}</span>
                    <span>{{ segment.start_offset }} - {{ segment.end_offset }}</span>
                  </div>
                  <div class="segment-text">{{ segment.content }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'

const route = useRoute()
const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const knowledgeBaseId = route.params.id

const pageError = ref('')
const quickTesting = ref(false)
const quickTestMeta = ref(null)
const quickTestResults = ref([])
const quickTest = ref({
  query: '',
  topK: null,
  scoreThreshold: null
})

const documents = ref([])
const datasets = ref([])
const runs = ref([])
const selectedRunId = ref('')
const compareRunIds = ref([])
const savingDataset = ref(false)
const runningEval = ref(false)
const savingFeedbackCaseId = ref('')

const datasetForm = ref(createEmptyDatasetForm())
const runForm = ref({
  testSetId: '',
  name: '',
  config: {
    retrieval_method: '',
    top_k: null,
    score_threshold: null,
    enable_rerank: '',
    vector_top_k: null,
    keyword_top_k: null,
    fusion_algorithm: '',
    rrf_k: null,
    vector_weight: null,
    keyword_weight: null,
    max_candidates: null,
    query_rewrite: ''
  }
})
const feedbackDrafts = ref({})

const selectedRun = computed(() => runs.value.find(item => item.id === selectedRunId.value) || null)
const compareRuns = computed(() => runs.value.filter(item => compareRunIds.value.includes(item.id)))

onMounted(async () => {
  await loadPage()
})

function createEmptyDatasetForm() {
  return {
    id: '',
    name: '',
    description: '',
    cases: [createEmptyCase()]
  }
}

function createEmptyCase() {
  return {
    localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    id: '',
    query: '',
    expectedDocumentIds: [],
    notes: ''
  }
}

async function loadPage() {
  pageError.value = ''
  try {
    const [docs, datasetList, runList] = await Promise.all([
      fetchAllDocuments(),
      knowledgeStore.fetchEvaluationDatasets(knowledgeBaseId),
      knowledgeStore.fetchEvaluationRuns(knowledgeBaseId, 20)
    ])
    documents.value = docs || []
    datasets.value = datasetList || []
    runs.value = runList || []
    if (runs.value.length && !selectedRunId.value) {
      selectRun(runs.value[0].id)
    }
  } catch (err) {
    pageError.value = extractErrorMessage(err, '加载检索评测中心失败')
  }
}

async function fetchAllDocuments() {
  const pageSize = 100
  let page = 1
  let total = 0
  const allDocuments = []

  do {
    const pageItems = await knowledgeStore.fetchDocuments(knowledgeBaseId, page, pageSize)
    allDocuments.push(...(pageItems || []))
    total = knowledgeStore.pagination.total || allDocuments.length
    page += 1
  } while (allDocuments.length < total)

  return allDocuments
}

function goToSettings() {
  router.push(`/knowledge/${knowledgeBaseId}/settings`)
}

async function runQuickTest() {
  if (!quickTest.value.query.trim()) return
  quickTesting.value = true
  pageError.value = ''
  quickTestMeta.value = null
  quickTestResults.value = []
  try {
    const data = await knowledgeStore.testKnowledgeRetrieval(knowledgeBaseId, {
      query: quickTest.value.query.trim(),
      top_k: Number.isFinite(quickTest.value.topK) ? quickTest.value.topK : null,
      score_threshold: Number.isFinite(quickTest.value.scoreThreshold) ? quickTest.value.scoreThreshold : null
    })
    quickTestMeta.value = data
    quickTestResults.value = data.results || []
  } catch (err) {
    pageError.value = extractErrorMessage(err, '召回测试失败')
  } finally {
    quickTesting.value = false
  }
}

function resetDatasetForm() {
  datasetForm.value = createEmptyDatasetForm()
}

function addCase() {
  datasetForm.value.cases.push(createEmptyCase())
}

function removeCase(index) {
  datasetForm.value.cases.splice(index, 1)
  if (!datasetForm.value.cases.length) {
    datasetForm.value.cases.push(createEmptyCase())
  }
}

function editDataset(dataset) {
  datasetForm.value = {
    id: dataset.id,
    name: dataset.name || '',
    description: dataset.description || '',
    cases: (dataset.cases || []).map(item => ({
      localId: item.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      id: item.id || '',
      query: item.query || '',
      expectedDocumentIds: Array.isArray(item.expected_document_ids) ? [...item.expected_document_ids] : [],
      notes: item.notes || ''
    }))
  }
  if (!datasetForm.value.cases.length) {
    datasetForm.value.cases.push(createEmptyCase())
  }
  runForm.value.testSetId = dataset.id
}

function buildDatasetPayload() {
  return {
    name: datasetForm.value.name.trim(),
    description: datasetForm.value.description.trim(),
    cases: datasetForm.value.cases
      .map(item => ({
        id: item.id || undefined,
        query: item.query.trim(),
        expected_document_ids: item.expectedDocumentIds,
        notes: item.notes.trim()
      }))
      .filter(item => item.query)
  }
}

async function saveDataset() {
  const payload = buildDatasetPayload()
  if (!payload.name || !payload.cases.length) {
    pageError.value = '请补全测试集名称和测试样本'
    return
  }
  savingDataset.value = true
  pageError.value = ''
  try {
    let data
    if (datasetForm.value.id) {
      data = await knowledgeStore.updateEvaluationDataset(knowledgeBaseId, datasetForm.value.id, payload)
      datasets.value = datasets.value.map(item => item.id === data.id ? data : item)
    } else {
      data = await knowledgeStore.createEvaluationDataset(knowledgeBaseId, payload)
      datasets.value = [data, ...datasets.value.filter(item => item.id !== data.id)]
    }
    editDataset(data)
  } catch (err) {
    pageError.value = extractErrorMessage(err, '保存测试集失败')
  } finally {
    savingDataset.value = false
  }
}

async function deleteDataset() {
  if (!datasetForm.value.id) return
  if (!window.confirm('删除后不可恢复，确定删除这个测试集吗？')) return

  savingDataset.value = true
  pageError.value = ''
  try {
    await knowledgeStore.deleteEvaluationDataset(knowledgeBaseId, datasetForm.value.id)
    datasets.value = datasets.value.filter(item => item.id !== datasetForm.value.id)
    if (runForm.value.testSetId === datasetForm.value.id) {
      runForm.value.testSetId = ''
    }
    resetDatasetForm()
  } catch (err) {
    pageError.value = extractErrorMessage(err, '删除测试集失败')
  } finally {
    savingDataset.value = false
  }
}

function buildRunPayload() {
  return {
    test_set_id: runForm.value.testSetId,
    name: runForm.value.name.trim() || null,
    config: {
      retrieval_method: runForm.value.config.retrieval_method || null,
      top_k: Number.isFinite(runForm.value.config.top_k) ? runForm.value.config.top_k : null,
      score_threshold: Number.isFinite(runForm.value.config.score_threshold) ? runForm.value.config.score_threshold : null,
      enable_rerank: runForm.value.config.enable_rerank === '' ? null : runForm.value.config.enable_rerank === 'true',
      vector_top_k: Number.isFinite(runForm.value.config.vector_top_k) ? runForm.value.config.vector_top_k : null,
      keyword_top_k: Number.isFinite(runForm.value.config.keyword_top_k) ? runForm.value.config.keyword_top_k : null,
      fusion_algorithm: runForm.value.config.fusion_algorithm || null,
      rrf_k: Number.isFinite(runForm.value.config.rrf_k) ? runForm.value.config.rrf_k : null,
      vector_weight: Number.isFinite(runForm.value.config.vector_weight) ? runForm.value.config.vector_weight : null,
      keyword_weight: Number.isFinite(runForm.value.config.keyword_weight) ? runForm.value.config.keyword_weight : null,
      max_candidates: Number.isFinite(runForm.value.config.max_candidates) ? runForm.value.config.max_candidates : null,
      query_rewrite: runForm.value.config.query_rewrite === '' ? null : runForm.value.config.query_rewrite === 'true'
    }
  }
}

async function runEvaluation() {
  if (!runForm.value.testSetId) return
  runningEval.value = true
  pageError.value = ''
  try {
    const run = await knowledgeStore.runEvaluation(knowledgeBaseId, buildRunPayload())
    runs.value = [run, ...runs.value.filter(item => item.id !== run.id)]
    selectRun(run.id)
  } catch (err) {
    pageError.value = extractErrorMessage(err, '运行评测失败')
  } finally {
    runningEval.value = false
  }
}

async function selectRun(runId) {
  pageError.value = ''
  try {
    const run = await knowledgeStore.fetchEvaluationRun(knowledgeBaseId, runId)
    runs.value = runs.value.map(item => item.id === run.id ? run : item)
    initializeFeedbackDrafts(run)
    selectedRunId.value = runId
  } catch (err) {
    pageError.value = extractErrorMessage(err, '加载评测详情失败')
  }
}

function initializeFeedbackDrafts(run) {
  const drafts = {}
  for (const item of run.results || []) {
    drafts[item.case_id] = {
      manual_score: item.manual_score,
      manual_comment: item.manual_comment || ''
    }
  }
  feedbackDrafts.value = drafts
}

function toggleCompare(runId) {
  if (compareRunIds.value.includes(runId)) {
    compareRunIds.value = compareRunIds.value.filter(item => item !== runId)
    return
  }
  if (compareRunIds.value.length >= 3) {
    compareRunIds.value = [...compareRunIds.value.slice(1), runId]
    return
  }
  compareRunIds.value = [...compareRunIds.value, runId]
}

async function saveFeedback(caseId) {
  if (!selectedRun.value || !feedbackDrafts.value[caseId]) return
  savingFeedbackCaseId.value = caseId
  pageError.value = ''
  try {
    const run = await knowledgeStore.updateEvaluationFeedback(knowledgeBaseId, selectedRun.value.id, {
      case_id: caseId,
      manual_score: feedbackDrafts.value[caseId].manual_score ?? null,
      manual_comment: feedbackDrafts.value[caseId].manual_comment || ''
    })
    runs.value = runs.value.map(item => item.id === run.id ? run : item)
    initializeFeedbackDrafts(run)
  } catch (err) {
    pageError.value = extractErrorMessage(err, '保存人工评分失败')
  } finally {
    savingFeedbackCaseId.value = ''
  }
}

async function applyRunConfig(runId) {
  if (!window.confirm('确认将这轮评测的检索配置设为当前生产配置？')) return
  pageError.value = ''
  try {
    await knowledgeStore.applyEvaluationRunConfig(knowledgeBaseId, runId)
    await knowledgeStore.fetchRetrievalSettings(knowledgeBaseId)
    await knowledgeStore.fetchEvaluationRuns(knowledgeBaseId, 20)
    runs.value = knowledgeStore.evaluationRuns || []
  } catch (err) {
    pageError.value = extractErrorMessage(err, '应用评测配置失败')
  }
}

function formatPercent(value) {
  if (typeof value !== 'number') return '-'
  return `${(value * 100).toFixed(1)}%`
}

function formatScore(value) {
  if (typeof value !== 'number') return '-'
  return value.toFixed(2)
}

function extractErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return fallback
}
</script>

<style scoped>
.eval-page {
  flex: 1;
  min-height: 0;
  width: 100%;
  background:
    radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 22%),
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 24%),
    #f4f7fb;
  overflow: auto;
  color: #0f172a;
}

.eval-container {
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px 24px 56px;
}

.page-header {
  margin-bottom: 24px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.title-row h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
}

.subtitle {
  margin: 0;
  max-width: 760px;
  color: #64748b;
  line-height: 1.6;
}

.back-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #d0d7e2;
  background: #fff;
  color: #334155;
  cursor: pointer;
}

.card {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #dbe4ef;
  border-radius: 18px;
  padding: 22px;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.06);
  margin-bottom: 24px;
  backdrop-filter: blur(8px);
}

.two-column {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 24px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head h2 {
  margin: 0 0 6px;
  font-size: 18px;
}

.section-head p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.form-grid,
.inline-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.form-row label {
  font-size: 13px;
  color: #64748b;
}

.form-row input,
.form-row textarea,
.form-row select {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d7e0ea;
  border-radius: 12px;
  background: #fff;
  color: #0f172a;
  padding: 11px 12px;
  font-size: 14px;
  outline: none;
}

.form-row textarea {
  min-height: 84px;
  resize: vertical;
}

.form-row select[multiple] {
  min-height: 148px;
}

.btn-primary,
.btn-secondary {
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  border: none;
  color: #fff;
  background: linear-gradient(135deg, #0f766e 0%, #0891b2 100%);
  box-shadow: 0 10px 24px rgba(8, 145, 178, 0.28);
}

.btn-secondary {
  border: 1px solid #d3dce8;
  color: #1e293b;
  background: #fff;
}

.btn-secondary.danger,
.text-btn.danger {
  color: #b91c1c;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary.slim {
  padding: 8px 12px;
  font-size: 13px;
}

.text-btn {
  border: none;
  background: transparent;
  color: #0f766e;
  cursor: pointer;
  padding: 0;
}

.error-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.14);
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.32);
  margin-bottom: 20px;
}

.meta-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin: 16px 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
  color: #475569;
  font-size: 13px;
}

.dataset-list,
.run-list,
.case-list,
.result-list,
.case-result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dataset-item,
.run-card {
  border: 1px solid #dbe4ef;
  background: #fff;
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.dataset-item.active,
.run-card.active {
  border-color: #0891b2;
  box-shadow: inset 0 0 0 1px rgba(8, 145, 178, 0.25);
}

.dataset-item strong,
.run-card strong {
  font-size: 14px;
}

.dataset-item span,
.run-card span,
.result-sub,
.expected-docs {
  color: #64748b;
  font-size: 13px;
}

.run-card-top,
.case-card-head,
.case-result-head,
.result-head,
.segment-head,
.compare-row,
.action-row,
.cases-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.run-metrics,
.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.badge {
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid transparent;
}

.badge.success {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
  border-color: rgba(16, 185, 129, 0.24);
}

.badge.muted {
  background: #eef2f7;
  color: #64748b;
}

.case-card,
.case-result-card,
.result-card,
.segment-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #fff;
  padding: 14px;
}

.segment-card {
  background: #fbfdff;
}

.segment-text {
  margin-top: 8px;
  white-space: pre-wrap;
  color: #334155;
  line-height: 1.6;
  font-size: 13px;
}

.compare-table {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
}

.compare-row {
  display: grid;
  grid-template-columns: 1.5fr 1fr 0.9fr 0.6fr 0.8fr 0.9fr 0.8fr;
  padding: 12px 14px;
  border-bottom: 1px solid #edf2f7;
  font-size: 13px;
}

.compare-head {
  background: #f8fafc;
  font-weight: 600;
}

.empty-state {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed #cbd5e1;
  color: #64748b;
  text-align: center;
  background: rgba(248, 250, 252, 0.8);
}

.empty-state.compact {
  padding: 12px;
  margin-bottom: 16px;
}

@media (max-width: 1080px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .eval-container {
    padding: 20px 14px 40px;
  }

  .form-grid,
  .inline-grid {
    grid-template-columns: 1fr;
  }

  .compare-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}
</style>
