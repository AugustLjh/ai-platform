<template>
  <div class="mcp-page">
    <section class="mcp-hero">
      <div>
        <div class="hero-kicker">MCP Registry</div>
        <h1>MCP Servers 管理</h1>
        <p>维护 tenant 级 MCP server，执行连接测试、工具发现和 catalog 缓存刷新。</p>
      </div>
      <div class="hero-actions">
        <button type="button" class="btn btn-secondary" @click="loadServers">刷新列表</button>
        <button type="button" class="btn btn-primary" @click="openCreate">新增 Server</button>
      </div>
    </section>

    <div v-if="errorMessage" class="error-banner">
      {{ errorMessage }}
    </div>

    <section class="mcp-grid">
      <div class="card server-list-card">
        <div class="section-head">
          <div>
            <h2>Server 列表</h2>
            <p>选择一个 server 查看配置、缓存工具和最近测试状态。</p>
          </div>
        </div>

        <div v-if="loading && servers.length === 0" class="panel-empty">
          正在加载 MCP servers...
        </div>

        <div v-else-if="servers.length === 0" class="panel-empty">
          还没有配置任何 MCP server。
        </div>

        <div v-else class="server-list">
          <button
            v-for="server in servers"
            :key="server.id"
            type="button"
            :class="['server-item', { active: selectedServer?.id === server.id }]"
            @click="selectServer(server.id)"
          >
            <div class="server-item-top">
              <strong>{{ server.name }}</strong>
              <span :class="['server-status', `status-${server.status}`]">{{ server.status }}</span>
            </div>
            <div class="server-item-meta">
              <span>{{ server.transport }}</span>
              <span>{{ (server.catalog?.toolCount ?? server.tools?.length) || 0 }} tools</span>
            </div>
            <div class="server-item-sub">
              {{ server.command || server.endpoint || '未配置连接地址' }}
            </div>
            <div class="server-item-badges">
              <span :class="['mini-badge', statusTone('availability', server.availability?.status)]">
                {{ statusLabel('availability', server.availability?.status) }}
              </span>
              <span :class="['mini-badge', statusTone('catalog', server.catalog?.status)]">
                {{ statusLabel('catalog', server.catalog?.status) }}
              </span>
            </div>
            <div v-if="server.lastError" class="server-item-error">
              {{ server.lastError }}
            </div>
          </button>
        </div>
      </div>

      <div class="card editor-card">
        <div class="section-head">
          <div>
            <h2>{{ editingServerId ? '编辑 Server' : '新增 Server' }}</h2>
            <p>支持 `stdio`、`http`、`sse` 三种 transport。`metadata` 可放 `headers`、`cwd`、超时等扩展配置。</p>
          </div>
        </div>

        <form class="server-form" @submit.prevent="saveServer">
          <label class="field">
            <span>名称</span>
            <input v-model="form.name" class="input" maxlength="120" />
          </label>

          <div class="field-row">
            <label class="field">
              <span>Transport</span>
              <select v-model="form.transport" class="input">
                <option value="stdio">stdio</option>
                <option value="http">http</option>
                <option value="sse">sse</option>
              </select>
            </label>

            <label class="field">
              <span>状态</span>
              <select v-model="form.status" class="input">
                <option value="active">active</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
          </div>

          <label v-if="form.transport === 'stdio'" class="field">
            <span>Command</span>
            <input v-model="form.command" class="input" placeholder="例如: npx" />
          </label>

          <label v-if="form.transport === 'stdio'" class="field">
            <span>Args JSON</span>
            <textarea
              v-model="form.argsText"
              class="input textarea"
              rows="4"
              placeholder='["-y", "@modelcontextprotocol/server-filesystem", "/data"]'
            ></textarea>
          </label>

          <label v-else class="field">
            <span>Endpoint</span>
            <input
              v-model="form.endpoint"
              class="input"
              :placeholder="form.transport === 'http' ? 'https://example.com/mcp' : 'https://example.com/sse'"
            />
          </label>

          <label class="field">
            <span>Env JSON</span>
            <textarea
              v-model="form.envText"
              class="input textarea"
              rows="5"
              placeholder='{"OPENAI_API_KEY":"********"}'
            ></textarea>
          </label>

          <label class="field">
            <span>Metadata JSON</span>
            <textarea
              v-model="form.metadataText"
              class="input textarea"
              rows="7"
              placeholder='{"headers":{"Authorization":"Bearer ********"},"timeout_seconds":30}'
            ></textarea>
          </label>

          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="resetForm">清空</button>
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? '保存中...' : (editingServerId ? '保存修改' : '创建 Server') }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section v-if="selectedServer" class="card detail-card">
      <div class="section-head">
        <div>
          <h2>{{ selectedServer.name }}</h2>
          <p>测试连接和刷新 catalog 都会落库，agent 侧工具列表基于这里的缓存结果。</p>
        </div>
        <div class="detail-actions">
          <button type="button" class="btn btn-secondary" :disabled="busyAction === 'test'" @click="testServer">
            {{ busyAction === 'test' ? '测试中...' : '连接测试' }}
          </button>
          <button type="button" class="btn btn-secondary" :disabled="busyAction === 'refresh'" @click="refreshTools">
            {{ busyAction === 'refresh' ? '刷新中...' : 'Refresh Tools' }}
          </button>
          <button type="button" class="btn btn-secondary" @click="loadServerDetail(selectedServer.id)">重新载入</button>
          <button type="button" class="btn btn-danger" :disabled="busyAction === 'delete'" @click="deleteServer">
            删除
          </button>
        </div>
      </div>

      <div class="detail-grid">
        <div class="detail-panel">
          <h3>连接信息</h3>
          <div class="detail-table">
            <div><span>Transport</span><strong>{{ selectedServer.transport }}</strong></div>
            <div><span>Status</span><strong>{{ selectedServer.status }}</strong></div>
            <div><span>Command / Endpoint</span><strong>{{ selectedServer.command || selectedServer.endpoint || '未配置' }}</strong></div>
            <div><span>Last Tested</span><strong>{{ formatTime(selectedServer.lastTestedAt) }}</strong></div>
          </div>
          <div class="summary-grid">
            <article class="summary-card">
              <div class="summary-head">
                <span class="summary-kicker">Connection</span>
                <span :class="['summary-badge', statusTone('connection', selectedServer.connection?.status)]">
                  {{ statusLabel('connection', selectedServer.connection?.status) }}
                </span>
              </div>
              <strong>{{ selectedServer.connection?.summary || '尚未执行连接测试。' }}</strong>
              <p v-if="selectedServer.connection?.testedAt">最近测试：{{ formatTime(selectedServer.connection?.testedAt) }}</p>
            </article>

            <article class="summary-card">
              <div class="summary-head">
                <span class="summary-kicker">Catalog</span>
                <span :class="['summary-badge', statusTone('catalog', selectedServer.catalog?.status)]">
                  {{ statusLabel('catalog', selectedServer.catalog?.status) }}
                </span>
              </div>
              <strong>{{ selectedServer.catalog?.summary || '尚未建立工具 catalog。' }}</strong>
              <p>缓存工具：{{ (selectedServer.catalog?.toolCount ?? selectedServer.tools?.length) || 0 }} 个</p>
              <p>最近刷新：{{ summarizeCatalogAge(selectedServer.catalog) }}</p>
            </article>

            <article class="summary-card">
              <div class="summary-head">
                <span class="summary-kicker">Availability</span>
                <span :class="['summary-badge', statusTone('availability', selectedServer.availability?.status)]">
                  {{ statusLabel('availability', selectedServer.availability?.status) }}
                </span>
              </div>
              <strong>{{ selectedServer.availability?.summary || '尚未准备好。' }}</strong>
              <p>绑定到 agent：{{ selectedServer.availability?.bindable ? '允许' : '暂不建议' }}</p>
            </article>
          </div>
          <div v-if="selectedServer.lastError" class="detail-error">
            {{ selectedServer.lastError }}
          </div>
          <div v-if="lastTestResult" class="test-result">
            <pre>{{ formatJSON(lastTestResult) }}</pre>
          </div>
        </div>

        <div class="detail-panel">
          <h3>缓存工具 Catalog</h3>
          <div v-if="selectedServer.catalog?.sampleTools?.length" class="catalog-samples">
            <span v-for="name in selectedServer.catalog.sampleTools" :key="name" class="sample-tool">{{ name }}</span>
          </div>
          <div v-if="!selectedServer.tools?.length" class="mini-empty">当前没有缓存工具，先执行 refresh。</div>
          <div v-else class="tool-catalog">
            <article v-for="tool in selectedServer.tools" :key="tool.runtimeName || tool.toolName" class="catalog-tool">
              <div class="catalog-tool-head">
                <strong>{{ tool.title || tool.toolName }}</strong>
                <span>{{ tool.runtimeName || tool.metadata?.runtime_name || 'runtime name pending' }}</span>
              </div>
              <p>{{ tool.description || '暂无描述' }}</p>
              <div class="catalog-tool-meta">
                <span>{{ Object.keys(tool.inputSchema?.properties || {}).length }} input fields</span>
                <span>{{ Object.keys(tool.outputSchema?.properties || {}).length }} output fields</span>
                <span>{{ formatTime(tool.discoveredAt) }}</span>
              </div>
              <div class="tool-schema-tags">
                <span
                  v-for="key in Object.keys(tool.inputSchema?.properties || {})"
                  :key="`${tool.toolName}-${key}`"
                  class="schema-tag"
                >
                  {{ key }}
                </span>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { mcpAPI } from '@/api'
import { useToastStore } from '@/store/toast'

const toastStore = useToastStore()

const loading = ref(false)
const saving = ref(false)
const busyAction = ref('')
const errorMessage = ref('')
const servers = ref([])
const selectedServer = ref(null)
const editingServerId = ref('')
const lastTestResult = ref(null)

const form = reactive({
  name: '',
  transport: 'stdio',
  endpoint: '',
  command: '',
  argsText: '[]',
  envText: '{}',
  metadataText: '{}',
  status: 'active'
})

const parseJSONField = (raw, fallback, fieldLabel) => {
  const text = String(raw || '').trim()
  if (!text) {
    return fallback
  }
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new Error(`${fieldLabel} 不是合法 JSON`)
  }
}

const normalizeTool = (tool = {}) => ({
  id: tool.id,
  serverId: tool.server_id || tool.serverId || '',
  runtimeName: tool.runtime_name || tool.runtimeName || '',
  serverName: tool.server_name || tool.serverName || '',
  toolName: tool.tool_name || tool.toolName || '',
  title: tool.title || '',
  description: tool.description || '',
  inputSchema: typeof tool.input_schema === 'object' ? tool.input_schema : (tool.inputSchema || {}),
  outputSchema: typeof tool.output_schema === 'object' ? tool.output_schema : (tool.outputSchema || {}),
  metadata: typeof tool.metadata === 'object' ? tool.metadata : {},
  discoveredAt: tool.discovered_at || tool.discoveredAt || null
})

const normalizeServer = (server = {}) => ({
  id: server.id,
  name: server.name || '',
  transport: server.transport || 'stdio',
  endpoint: server.endpoint || '',
  command: server.command || '',
  args: typeof server.args === 'object' ? (server.args || []) : [],
  env: typeof server.env === 'object' ? (server.env || {}) : {},
  metadata: typeof server.metadata === 'object' ? (server.metadata || {}) : {},
  status: server.status || 'active',
  lastError: server.last_error || server.lastError || '',
  lastTestedAt: server.last_tested_at || server.lastTestedAt || null,
  connection: server.connection && typeof server.connection === 'object' ? {
    status: server.connection.status || 'untested',
    summary: server.connection.summary || '',
    testedAt: server.connection.tested_at || server.connection.testedAt || null,
    error: server.connection.error || ''
  } : null,
  catalog: server.catalog && typeof server.catalog === 'object' ? {
    status: server.catalog.status || 'missing',
    summary: server.catalog.summary || '',
    toolCount: Number(server.catalog.tool_count || server.catalog.toolCount || 0),
    refreshedAt: server.catalog.refreshed_at || server.catalog.refreshedAt || null,
    ageSeconds: server.catalog.age_seconds ?? server.catalog.ageSeconds ?? null,
    staleAfterSeconds: Number(server.catalog.stale_after_seconds || server.catalog.staleAfterSeconds || 0),
    isStale: Boolean(server.catalog.is_stale || server.catalog.isStale),
    sampleTools: Array.isArray(server.catalog.sample_tools || server.catalog.sampleTools)
      ? [...(server.catalog.sample_tools || server.catalog.sampleTools)]
      : []
  } : null,
  availability: server.availability && typeof server.availability === 'object' ? {
    status: server.availability.status || 'unavailable',
    summary: server.availability.summary || '',
    bindable: Boolean(server.availability.bindable),
    reason: server.availability.reason || ''
  } : null,
  tools: Array.isArray(server.tools) ? server.tools.map(normalizeTool) : []
})

const connectionStatusMap = {
  healthy: '连接正常',
  degraded: '连接异常',
  untested: '未测试',
  disabled: '已禁用'
}

const catalogStatusMap = {
  ready: 'Catalog 就绪',
  stale: 'Catalog 过期',
  empty: 'Catalog 为空',
  missing: '未刷新',
  disabled: '已禁用'
}

const availabilityStatusMap = {
  available: '可投入使用',
  warning: '可用但需关注',
  degraded: '不建议使用',
  unavailable: '不可用',
  disabled: '已禁用'
}

const summarizeCatalogAge = (catalog) => {
  if (!catalog?.refreshedAt) return '尚未刷新'
  if (catalog.ageSeconds === null || catalog.ageSeconds === undefined) return '刚刚刷新'
  const seconds = Number(catalog.ageSeconds)
  if (seconds < 60) return `${seconds} 秒前`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`
  return `${Math.floor(seconds / 86400)} 天前`
}

const statusTone = (kind, status) => {
  const normalized = String(status || '').trim() || 'default'
  return `${kind}-${normalized}`
}

const statusLabel = (kind, status) => {
  if (kind === 'connection') return connectionStatusMap[status] || status || '未知状态'
  if (kind === 'catalog') return catalogStatusMap[status] || status || '未知状态'
  return availabilityStatusMap[status] || status || '未知状态'
}

const applyServerSnapshot = (rawServer) => {
  if (!rawServer) return null
  const normalized = normalizeServer(rawServer)
  const index = servers.value.findIndex((item) => item.id === normalized.id)
  if (index >= 0) {
    servers.value[index] = normalized
  } else {
    servers.value = [normalized, ...servers.value]
  }
  if (selectedServer.value?.id === normalized.id || !selectedServer.value) {
    selectedServer.value = normalized
  }
  return normalized
}

const loadServers = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await mcpAPI.listServers()
    servers.value = (data.servers || []).map(normalizeServer)
    if (!selectedServer.value && servers.value.length > 0) {
      selectedServer.value = servers.value[0]
      fillForm(selectedServer.value)
      editingServerId.value = selectedServer.value.id
    } else if (selectedServer.value?.id) {
      const next = servers.value.find((item) => item.id === selectedServer.value.id)
      if (next) {
        selectedServer.value = next
      }
    }
  } catch (error) {
    console.error('Failed to load MCP servers:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '加载 MCP servers 失败'
  } finally {
    loading.value = false
  }
}

const loadServerDetail = async (serverId) => {
  if (!serverId) return
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await mcpAPI.getServer(serverId)
    selectedServer.value = applyServerSnapshot(data)
    fillForm(selectedServer.value)
    editingServerId.value = serverId
  } catch (error) {
    console.error('Failed to load MCP server detail:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '加载 MCP server 详情失败'
  } finally {
    loading.value = false
  }
}

const selectServer = async (serverId) => {
  lastTestResult.value = null
  await loadServerDetail(serverId)
}

const fillForm = (server) => {
  form.name = server?.name || ''
  form.transport = server?.transport || 'stdio'
  form.endpoint = server?.endpoint || ''
  form.command = server?.command || ''
  form.argsText = formatJSON(server?.args || [])
  form.envText = formatJSON(server?.env || {})
  form.metadataText = formatJSON(server?.metadata || {})
  form.status = server?.status || 'active'
}

const resetForm = () => {
  editingServerId.value = ''
  lastTestResult.value = null
  form.name = ''
  form.transport = 'stdio'
  form.endpoint = ''
  form.command = ''
  form.argsText = '[]'
  form.envText = '{}'
  form.metadataText = '{}'
  form.status = 'active'
}

const openCreate = () => {
  selectedServer.value = null
  resetForm()
}

const buildPayload = () => ({
  name: form.name.trim(),
  transport: form.transport,
  endpoint: form.transport === 'stdio' ? '' : form.endpoint.trim(),
  command: form.transport === 'stdio' ? form.command.trim() : '',
  args: parseJSONField(form.argsText, [], 'Args JSON'),
  env: parseJSONField(form.envText, {}, 'Env JSON'),
  metadata: parseJSONField(form.metadataText, {}, 'Metadata JSON'),
  status: form.status
})

const saveServer = async () => {
  if (!form.name.trim()) {
    toastStore.showToast({ type: 'error', message: '请先填写 server 名称' })
    return
  }

  saving.value = true
  errorMessage.value = ''
  try {
    const payload = buildPayload()
    const response = editingServerId.value
      ? await mcpAPI.updateServer(editingServerId.value, payload)
      : await mcpAPI.createServer(payload)
    const saved = applyServerSnapshot(response.data)
    selectedServer.value = saved
    editingServerId.value = saved.id
    await loadServers()
    await loadServerDetail(saved.id)
    toastStore.showToast({ type: 'success', message: 'MCP server 已保存' })
  } catch (error) {
    console.error('Failed to save MCP server:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '保存 MCP server 失败'
    toastStore.showToast({ type: 'error', message: errorMessage.value })
  } finally {
    saving.value = false
  }
}

const testServer = async () => {
  if (!selectedServer.value?.id) return
  busyAction.value = 'test'
  errorMessage.value = ''
  try {
    const { data } = await mcpAPI.testServer(selectedServer.value.id)
    lastTestResult.value = data.result || data
    applyServerSnapshot(data.server)
    toastStore.showToast({ type: 'success', message: data?.result?.ok ? '连接测试通过' : '连接测试已完成' })
  } catch (error) {
    console.error('Failed to test MCP server:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '连接测试失败'
    toastStore.showToast({ type: 'error', message: errorMessage.value })
  } finally {
    busyAction.value = ''
  }
}

const refreshTools = async () => {
  if (!selectedServer.value?.id) return
  busyAction.value = 'refresh'
  errorMessage.value = ''
  try {
    const { data } = await mcpAPI.refreshTools(selectedServer.value.id)
    applyServerSnapshot(data.server)
    toastStore.showToast({ type: 'success', message: `已刷新 ${data.total || 0} 个工具` })
  } catch (error) {
    console.error('Failed to refresh MCP tools:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '刷新工具失败'
    toastStore.showToast({ type: 'error', message: errorMessage.value })
  } finally {
    busyAction.value = ''
  }
}

const deleteServer = async () => {
  if (!selectedServer.value?.id) return
  const confirmed = window.confirm(`确认删除 MCP server “${selectedServer.value.name}”吗？`)
  if (!confirmed) return

  busyAction.value = 'delete'
  errorMessage.value = ''
  try {
    await mcpAPI.deleteServer(selectedServer.value.id)
    toastStore.showToast({ type: 'success', message: 'MCP server 已删除' })
    selectedServer.value = null
    resetForm()
    await loadServers()
  } catch (error) {
    console.error('Failed to delete MCP server:', error)
    errorMessage.value = error?.response?.data?.error || error?.response?.data?.detail || error?.message || '删除 MCP server 失败'
    toastStore.showToast({ type: 'error', message: errorMessage.value })
  } finally {
    busyAction.value = ''
  }
}

const formatJSON = (value) => JSON.stringify(value ?? {}, null, 2)

const formatTime = (value) => {
  if (!value) return '未测试'
  return new Date(value).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(async () => {
  await loadServers()
})
</script>

<style scoped>
.mcp-page {
  display: grid;
  gap: 24px;
}

.mcp-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(249, 115, 22, 0.16), transparent 42%),
    linear-gradient(135deg, #fffaf5 0%, #fff 55%, #fff5eb 100%);
  border: 1px solid rgba(249, 115, 22, 0.16);
}

.hero-kicker {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #c2410c;
  margin-bottom: 8px;
}

.mcp-hero h1 {
  margin: 0;
  font-size: 32px;
}

.mcp-hero p {
  margin: 10px 0 0;
  color: var(--gray-600);
}

.hero-actions,
.detail-actions,
.form-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.mcp-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
}

.card {
  background: #fff;
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  padding: 24px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head h2,
.detail-panel h3 {
  margin: 0;
}

.section-head p,
.detail-panel p {
  margin: 8px 0 0;
  color: var(--gray-600);
}

.panel-empty,
.mini-empty {
  padding: 24px;
  border-radius: 18px;
  background: #f8fafc;
  color: var(--gray-500);
  text-align: center;
}

.server-list {
  display: grid;
  gap: 12px;
}

.server-item {
  width: 100%;
  text-align: left;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(180deg, #fff 0%, #fffaf5 100%);
}

.server-item.active {
  border-color: rgba(249, 115, 22, 0.35);
  box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.08);
}

.server-item-top,
.catalog-tool-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.server-item-meta,
.server-item-sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--gray-500);
}

.server-item-meta {
  display: flex;
  gap: 12px;
}

.server-item-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.mini-badge,
.summary-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.mini-badge {
  padding: 5px 10px;
}

.summary-badge {
  padding: 4px 10px;
}

.server-item-error,
.detail-error {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(239, 68, 68, 0.08);
  color: #b91c1c;
  font-size: 13px;
}

.server-status {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.server-status.status-active {
  background: rgba(16, 163, 127, 0.12);
  color: var(--primary-700);
}

.server-status.status-disabled {
  background: rgba(148, 163, 184, 0.14);
  color: var(--gray-600);
}

.server-form {
  display: grid;
  gap: 16px;
}

.field-row,
.detail-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 13px;
  font-weight: 700;
  color: var(--gray-700);
}

.input {
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 14px;
  padding: 12px 14px;
  background: #fff;
}

.textarea {
  min-height: 120px;
  resize: vertical;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.detail-table {
  display: grid;
  gap: 10px;
}

.detail-table div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.detail-table span {
  color: var(--gray-500);
}

.summary-grid {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.summary-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
}

.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.summary-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
  font-weight: 700;
}

.summary-card strong {
  display: block;
  font-size: 14px;
  line-height: 1.6;
  color: var(--gray-900);
}

.summary-card p {
  margin: 8px 0 0;
  font-size: 13px;
}

.test-result {
  margin-top: 14px;
  padding: 14px;
  border-radius: 16px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
}

.test-result pre {
  margin: 0;
  white-space: pre-wrap;
}

.tool-catalog {
  display: grid;
  gap: 12px;
}

.catalog-samples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.sample-tool {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}

.catalog-tool {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  padding: 14px;
  background: #fffaf5;
}

.catalog-tool-head span {
  font-size: 12px;
  color: var(--gray-500);
}

.catalog-tool-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.tool-schema-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.schema-tag {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(249, 115, 22, 0.12);
  color: #c2410c;
  font-size: 12px;
}

.btn-danger {
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: rgba(254, 242, 242, 0.9);
  color: #b91c1c;
}

.connection-healthy,
.availability-available,
.catalog-ready {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.connection-degraded,
.availability-degraded,
.availability-unavailable,
.catalog-empty,
.catalog-missing {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.connection-untested,
.availability-warning,
.catalog-stale {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.connection-disabled,
.availability-disabled,
.catalog-disabled {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

@media (max-width: 960px) {
  .mcp-grid,
  .detail-grid,
  .field-row {
    grid-template-columns: 1fr;
  }

  .mcp-hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
