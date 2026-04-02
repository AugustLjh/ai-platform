<template>
  <article :class="cardClass">
    <div class="artifact-head">
      <div>
        <div class="artifact-kicker">{{ kicker }}</div>
        <h4>{{ artifact.name }}</h4>
      </div>
      <span v-if="summaryText" class="artifact-meta">{{ summaryText }}</span>
    </div>

    <div class="rich-toolbar">
      <input
        v-model="query"
        type="search"
        class="rich-search"
        :placeholder="searchPlaceholder"
      >
      <span class="rich-count">{{ countText }}</span>
    </div>

    <div v-if="artifact.artifactType === 'directory_tree'" class="rich-grid">
      <div class="rich-list tree-list">
        <button
          v-for="row in directoryExplorer.rows"
          :key="row.key"
          type="button"
          :class="['rich-row', 'tree-row', { active: row.key === directoryExplorer.selectedKey }]"
          @click="selectRow(row.key)"
        >
          <span :style="{ paddingLeft: `${row.depth * 16}px` }" class="tree-row-main">
            <span
              v-if="row.hasChildren"
              class="tree-toggle"
              @click.stop="toggleExpanded(row.key)"
            >
              {{ row.expanded ? '▾' : '▸' }}
            </span>
            <span v-else class="tree-toggle tree-toggle-spacer"></span>
            <span class="tree-badge">{{ row.isDirectory ? 'D' : 'F' }}</span>
            <span class="tree-label">{{ row.name }}</span>
          </span>
          <span v-if="row.node?.size_bytes" class="row-meta">{{ formatBytes(row.node.size_bytes) }}</span>
        </button>
      </div>

      <div class="rich-detail">
        <template v-if="directoryExplorer.selectedNode">
          <div class="detail-title">{{ directoryExplorer.selectedNode.name || directoryExplorer.selectedNode.path }}</div>
          <div class="detail-meta">{{ directoryNodeMeta(directoryExplorer.selectedNode) }}</div>
          <a
            v-if="directoryExplorer.selectedNode.uri"
            :href="directoryExplorer.selectedNode.uri"
            target="_blank"
            rel="noreferrer"
            class="detail-link"
          >
            打开资源
          </a>
          <pre>{{ formatJSON(directoryExplorer.selectedNode.metadata || {}) }}</pre>
        </template>
        <div v-else class="empty-mini">当前筛选下没有目录节点。</div>
      </div>
    </div>

    <div v-else-if="artifact.artifactType === 'document_pages'" class="rich-grid">
      <div class="rich-list">
        <button
          v-for="page in documentExplorer.items"
          :key="String(page.page_number)"
          type="button"
          :class="['rich-row', { active: String(page.page_number) === documentExplorer.selectedKey }]"
          @click="selectRow(String(page.page_number))"
        >
          <span>
            <strong>{{ page.title || `Page ${page.page_number}` }}</strong>
            <span class="row-subtitle">第 {{ page.page_number }} 页</span>
          </span>
          <span class="row-meta">{{ page.mime_type || '文档页' }}</span>
        </button>
      </div>

      <div class="rich-detail">
        <template v-if="documentExplorer.selectedPage">
          <div class="detail-title">{{ documentExplorer.selectedPage.title || `Page ${documentExplorer.selectedPage.page_number}` }}</div>
          <div class="detail-meta">{{ documentPageMeta(documentExplorer.selectedPage) }}</div>
          <div v-if="documentExplorer.selectedPage.thumbnail_uri" class="preview-frame">
            <img :src="documentExplorer.selectedPage.thumbnail_uri" :alt="documentExplorer.selectedPage.title || `Page ${documentExplorer.selectedPage.page_number}`" class="preview-image">
          </div>
          <p v-if="documentExplorer.selectedPage.text" class="detail-copy">{{ documentExplorer.selectedPage.text }}</p>
          <div class="detail-links">
            <a v-if="documentExplorer.selectedPage.thumbnail_uri" :href="documentExplorer.selectedPage.thumbnail_uri" target="_blank" rel="noreferrer">打开缩略图</a>
            <a v-if="documentExplorer.selectedPage.uri" :href="documentExplorer.selectedPage.uri" target="_blank" rel="noreferrer">打开页面资源</a>
          </div>
          <pre v-if="hasMetadata(documentExplorer.selectedPage.metadata)">{{ formatJSON(documentExplorer.selectedPage.metadata) }}</pre>
        </template>
        <div v-else class="empty-mini">当前筛选下没有文档页。</div>
      </div>
    </div>

    <div v-else-if="artifact.artifactType === 'media_gallery'" class="media-shell">
      <div v-if="mediaExplorer.selectedItem" class="media-feature">
        <div class="preview-frame">
          <img v-if="mediaExplorer.selectedItem.kind === 'image' && mediaExplorer.selectedItem.uri" :src="mediaExplorer.selectedItem.uri" :alt="mediaExplorer.selectedItem.alt || mediaExplorer.selectedItem.title" class="preview-image">
          <video v-else-if="mediaExplorer.selectedItem.kind === 'video' && mediaExplorer.selectedItem.uri" controls class="preview-video">
            <source :src="mediaExplorer.selectedItem.uri" :type="mediaExplorer.selectedItem.mime_type || undefined">
          </video>
          <audio v-else-if="mediaExplorer.selectedItem.kind === 'audio' && mediaExplorer.selectedItem.uri" controls class="preview-audio">
            <source :src="mediaExplorer.selectedItem.uri" :type="mediaExplorer.selectedItem.mime_type || undefined">
          </audio>
          <div v-else class="media-fallback">{{ mediaKindLabel(mediaExplorer.selectedItem.kind) }}</div>
        </div>
        <div class="detail-title">{{ mediaExplorer.selectedItem.title }}</div>
        <div class="detail-meta">{{ mediaMeta(mediaExplorer.selectedItem) }}</div>
        <div class="detail-links">
          <a v-if="mediaExplorer.selectedItem.uri" :href="mediaExplorer.selectedItem.uri" target="_blank" rel="noreferrer">打开资源</a>
        </div>
      </div>

      <div class="thumb-grid">
        <button
          v-for="(item, index) in mediaExplorer.items"
          :key="itemKey(item, index)"
          type="button"
          :class="['thumb-card', { active: itemKey(item, index) === mediaExplorer.selectedKey }]"
          @click="selectRow(itemKey(item, index))"
        >
          <img v-if="item.kind === 'image' && item.uri" :src="item.uri" :alt="item.alt || item.title" class="thumb-image">
          <div v-else class="thumb-fallback">{{ mediaKindLabel(item.kind) }}</div>
          <span class="thumb-title">{{ item.title }}</span>
        </button>
      </div>
    </div>

    <div v-else-if="artifact.artifactType === 'paged_collection'" class="rich-grid">
      <div class="rich-list">
        <button
          v-for="(item, index) in pagedExplorer.items"
          :key="itemKey(item, index)"
          type="button"
          :class="['rich-row', { active: itemKey(item, index) === pagedExplorer.selectedKey }]"
          @click="selectRow(itemKey(item, index))"
        >
          <span class="row-json">{{ summarizeItem(item) }}</span>
        </button>
      </div>

      <div class="rich-detail">
        <template v-if="pagedExplorer.selectedItem">
          <div v-if="pagedExplorer.columns.length > 0" class="detail-table-wrap">
            <table>
              <tbody>
                <tr v-for="column in pagedExplorer.columns" :key="column">
                  <th>{{ column }}</th>
                  <td>{{ displayCell(pagedExplorer.selectedItem?.[column]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <pre v-else>{{ formatJSON(pagedExplorer.selectedItem) }}</pre>
        </template>
        <div v-else class="empty-mini">当前筛选下没有结果项。</div>
      </div>
    </div>

    <div v-else-if="artifact.artifactType === 'file_bundle' || artifact.artifactType === 'archive_bundle'" class="rich-grid">
      <div class="rich-list">
        <button
          v-for="(item, index) in bundleExplorer.items"
          :key="itemKey(item, index)"
          type="button"
          :class="['rich-row', { active: itemKey(item, index) === bundleExplorer.selectedKey }]"
          @click="selectRow(itemKey(item, index))"
        >
          <span>
            <strong>{{ item.name }}</strong>
            <span class="row-subtitle">{{ item.path || item.uri || '未提供路径' }}</span>
          </span>
          <span class="row-meta">{{ bundleItemMeta(item) }}</span>
        </button>
      </div>

      <div class="rich-detail">
        <template v-if="bundleExplorer.selectedItem">
          <div class="detail-title">{{ bundleExplorer.selectedItem.name }}</div>
          <div class="detail-meta">{{ bundleItemMeta(bundleExplorer.selectedItem) }}</div>
          <p v-if="bundleExplorer.selectedItem.description" class="detail-copy">{{ bundleExplorer.selectedItem.description }}</p>
          <pre v-if="bundleExplorer.selectedItem.preview_text">{{ bundleExplorer.selectedItem.preview_text }}</pre>
          <p v-if="bundleExplorer.selectedItem.checksum" class="detail-copy">校验: {{ bundleExplorer.selectedItem.checksum }}</p>
          <div class="detail-links">
            <a v-if="bundleExplorer.selectedItem.uri" :href="bundleExplorer.selectedItem.uri" target="_blank" rel="noreferrer">打开资源</a>
          </div>
          <pre v-if="hasMetadata(bundleExplorer.selectedItem.metadata)">{{ formatJSON(bundleExplorer.selectedItem.metadata) }}</pre>
        </template>
        <div v-else class="empty-mini">当前筛选下没有文件。</div>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  buildArchiveBundleExplorer,
  buildDirectoryTreeExplorer,
  buildDocumentPagesExplorer,
  buildFileBundleExplorer,
  buildMediaGalleryExplorer,
  buildPagedCollectionExplorer
} from '@/utils/agentArtifactInteractions'

const props = defineProps({
  artifact: {
    type: Object,
    required: true
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const query = ref('')
const selectedKey = ref('')
const expandedPaths = ref([])

watch(() => props.artifact.clientKey || props.artifact.id || props.artifact.name, () => {
  query.value = ''
  selectedKey.value = ''
  expandedPaths.value = []
})

const kickerMap = {
  paged_collection: '分页结果',
  directory_tree: '目录树',
  document_pages: '多页文档',
  media_gallery: '媒体资源',
  file_bundle: '附件集合',
  archive_bundle: '压缩包清单'
}

const searchPlaceholderMap = {
  paged_collection: '筛选结果项',
  directory_tree: '搜索路径、名称或元数据',
  document_pages: '搜索页标题或正文',
  media_gallery: '搜索媒体标题或类型',
  file_bundle: '搜索文件名、路径或预览',
  archive_bundle: '搜索归档成员'
}

const cardClass = computed(() => [props.compact ? 'preview-card' : 'artifact-card', 'rich-card'])
const kicker = computed(() => kickerMap[props.artifact.artifactType] || '结构化结果')
const searchPlaceholder = computed(() => searchPlaceholderMap[props.artifact.artifactType] || '搜索')

const directoryExplorer = computed(() => buildDirectoryTreeExplorer(props.artifact.payload, {
  query: query.value,
  selectedPath: selectedKey.value,
  expandedPaths: expandedPaths.value
}))
const documentExplorer = computed(() => buildDocumentPagesExplorer(props.artifact.payload, {
  query: query.value,
  selectedPage: selectedKey.value
}))
const mediaExplorer = computed(() => buildMediaGalleryExplorer(props.artifact.payload, {
  query: query.value,
  selectedItem: selectedKey.value
}))
const pagedExplorer = computed(() => buildPagedCollectionExplorer(props.artifact.payload, {
  query: query.value,
  selectedItem: selectedKey.value
}))
const fileBundleExplorer = computed(() => buildFileBundleExplorer(props.artifact.payload, {
  query: query.value,
  selectedItem: selectedKey.value
}))
const archiveBundleExplorer = computed(() => buildArchiveBundleExplorer(props.artifact.payload, {
  query: query.value,
  selectedItem: selectedKey.value
}))

const bundleExplorer = computed(() => (
  props.artifact.artifactType === 'archive_bundle'
    ? archiveBundleExplorer.value
    : fileBundleExplorer.value
))

const countText = computed(() => {
  if (props.artifact.artifactType === 'directory_tree') {
    return `${directoryExplorer.value.rows.length} 个节点`
  }
  const explorer = props.artifact.artifactType === 'document_pages'
    ? documentExplorer.value
    : props.artifact.artifactType === 'media_gallery'
      ? mediaExplorer.value
      : props.artifact.artifactType === 'paged_collection'
        ? pagedExplorer.value
        : bundleExplorer.value
  return `${explorer.items.length}/${explorer.totalCount || explorer.items.length}`
})

const summaryText = computed(() => {
  const payload = props.artifact.payload || {}
  if (props.artifact.artifactType === 'directory_tree') {
    const summary = payload.summary || {}
    return [summary.directory_count ? `${summary.directory_count} 个目录` : '', summary.file_count ? `${summary.file_count} 个文件` : '', summary.max_depth ? `深度 ${summary.max_depth}` : '']
      .filter(Boolean)
      .join(' · ')
  }
  if (props.artifact.artifactType === 'document_pages') {
    return payload.page_count ? `${payload.page_count} 页` : ''
  }
  if (props.artifact.artifactType === 'paged_collection') {
    const pagination = payload.pagination || {}
    return [
      pagination.page ? `第 ${pagination.page} 页` : '',
      pagination.returned_count ? `返回 ${pagination.returned_count} 条` : '',
      pagination.total_count ? `共 ${pagination.total_count} 条` : '',
      pagination.next_cursor ? '含下一页游标' : ''
    ].filter(Boolean).join(' · ')
  }
  if (props.artifact.artifactType === 'archive_bundle') {
    return [
      payload.format ? String(payload.format).toUpperCase() : '',
      payload.entry_count ? `${payload.entry_count} 个条目` : '',
      payload.total_size_bytes ? `原始 ${formatBytes(payload.total_size_bytes)}` : '',
      payload.total_compressed_size_bytes ? `压缩后 ${formatBytes(payload.total_compressed_size_bytes)}` : ''
    ].filter(Boolean).join(' · ')
  }
  return ''
})

const selectRow = (value) => {
  selectedKey.value = String(value || '')
}

const toggleExpanded = (path) => {
  if (!path) return
  if (expandedPaths.value.includes(path)) {
    expandedPaths.value = expandedPaths.value.filter((item) => item !== path)
    return
  }
  expandedPaths.value = [...expandedPaths.value, path]
}

const formatJSON = (value) => JSON.stringify(value || {}, null, 2)

const formatBytes = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return ''
  if (parsed < 1024) return `${parsed} B`
  if (parsed < 1024 * 1024) return `${(parsed / 1024).toFixed(1)} KB`
  return `${(parsed / (1024 * 1024)).toFixed(1)} MB`
}

const displayCell = (value) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const hasMetadata = (value) => value && typeof value === 'object' && Object.keys(value).length > 0

const summarizeItem = (item) => {
  if (!item || typeof item !== 'object') {
    return String(item || '')
  }
  const entries = Object.entries(item).slice(0, 3)
  return entries.map(([key, value]) => `${key}: ${displayCell(value)}`).join(' · ')
}

const mediaKindLabel = (kind) => ({
  image: '图片',
  video: '视频',
  audio: '音频'
}[kind] || '媒体')

const mediaMeta = (item) => [mediaKindLabel(item?.kind), item?.mime_type, formatBytes(item?.size_bytes)].filter(Boolean).join(' · ')
const directoryNodeMeta = (item) => [item?.path, item?.mime_type, formatBytes(item?.size_bytes)].filter(Boolean).join(' · ')
const documentPageMeta = (item) => [`第 ${item?.page_number} 页`, item?.mime_type, item?.source].filter(Boolean).join(' · ')
const bundleItemMeta = (item) => [
  item?.path,
  item?.mime_type,
  formatBytes(item?.size_bytes),
  item?.compressed_size_bytes ? `压缩后 ${formatBytes(item.compressed_size_bytes)}` : ''
].filter(Boolean).join(' · ')

const itemKey = (item, index) => String(
  item?.uri ||
  item?.path ||
  item?.name ||
  item?.title ||
  item?.page_number ||
  item?.id ||
  index + 1
)
</script>

<style scoped>
.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
}

.preview-card {
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.rich-card {
  display: grid;
  gap: 14px;
}

.artifact-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.artifact-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--primary-700);
}

.artifact-head h4 {
  margin-top: 6px;
  font-size: 17px;
}

.artifact-meta {
  color: var(--gray-500);
  font-size: 12px;
}

.rich-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.rich-search {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.88);
}

.rich-count {
  font-size: 12px;
  color: var(--gray-500);
  white-space: nowrap;
}

.rich-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
}

.rich-list {
  display: grid;
  gap: 8px;
  max-height: 440px;
  overflow: auto;
  padding-right: 4px;
}

.rich-row {
  width: 100%;
  border: 1px solid var(--gray-200);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.85);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
  cursor: pointer;
}

.rich-row.active {
  border-color: rgba(16, 163, 127, 0.35);
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.08);
}

.row-subtitle {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--gray-500);
  word-break: break-word;
}

.row-meta {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--gray-500);
}

.row-json {
  font-size: 13px;
  color: var(--gray-700);
  line-height: 1.5;
  word-break: break-word;
}

.rich-detail {
  min-height: 240px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcfb 100%);
  padding: 16px;
  overflow: auto;
}

.detail-title {
  font-weight: 700;
  color: var(--gray-900);
}

.detail-meta {
  margin-top: 6px;
  color: var(--gray-500);
  font-size: 12px;
}

.detail-copy {
  margin-top: 12px;
  line-height: 1.7;
  color: var(--gray-700);
}

.detail-links {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-link,
.detail-links a {
  color: var(--primary-700);
  text-decoration: none;
  font-weight: 600;
}

.preview-frame {
  margin-top: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.preview-image,
.preview-video {
  width: 100%;
  max-height: 320px;
  object-fit: contain;
  display: block;
}

.preview-audio {
  width: 100%;
  padding: 16px;
}

.media-shell {
  display: grid;
  gap: 14px;
}

.media-feature {
  display: grid;
  gap: 12px;
}

.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.thumb-card {
  border: 1px solid var(--gray-200);
  border-radius: 14px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: grid;
  gap: 8px;
}

.thumb-card.active {
  border-color: rgba(16, 163, 127, 0.35);
  box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.08);
}

.thumb-image {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 10px;
}

.thumb-fallback,
.media-fallback {
  min-height: 120px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.05);
  color: var(--gray-600);
  font-weight: 600;
}

.thumb-title {
  font-size: 12px;
  color: var(--gray-700);
  word-break: break-word;
}

.tree-row {
  padding: 10px 12px;
}

.tree-row-main {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tree-toggle {
  width: 16px;
  color: var(--gray-500);
  font-size: 12px;
  text-align: center;
}

.tree-toggle-spacer {
  visibility: hidden;
}

.tree-badge {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tree-label {
  word-break: break-word;
}

.detail-table-wrap {
  overflow: auto;
}

.detail-table-wrap table {
  width: 100%;
  border-collapse: collapse;
}

.detail-table-wrap th,
.detail-table-wrap td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--gray-200);
  text-align: left;
  vertical-align: top;
}

.empty-mini {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gray-500);
  text-align: center;
}

@media (max-width: 900px) {
  .rich-grid {
    grid-template-columns: 1fr;
  }
}
</style>
