const textKeys = [
  'final_output_text',
  'answer',
  'summary',
  'final_answer',
  'response',
  'message',
  'content',
  'result'
]
const artifactPriority = {
  answer: 0,
  workspace_summary: 1,
  review_findings: 1,
  citations: 2,
  code_patch: 3,
  verification_report: 4,
  code_files: 5,
  task_plan: 6,
  table: 7,
  paged_collection: 8,
  directory_tree: 9,
  document_pages: 10,
  document_excerpt: 11,
  media_gallery: 12,
  archive_bundle: 13,
  file_bundle: 14
}
const implicitListKeys = ['items', 'results', 'entries', 'records', 'matches', 'documents', 'data']
const pagedKeys = ['paged_collection', 'paged_results', 'page', 'page_result']
const mediaKeys = ['media_gallery', 'image_gallery', 'images', 'media']
const fileBundleKeys = ['file_bundle', 'attachments', 'resources', 'downloads']
const directoryTreeKeys = ['directory_tree', 'tree', 'file_tree']
const documentPageKeys = ['document_pages', 'pages', 'document_preview_pages']
const archiveBundleKeys = ['archive_bundle', 'archive_entries', 'compressed_bundle']
const codeFileExtensions = {
  '.c': 'c',
  '.cc': 'cpp',
  '.cpp': 'cpp',
  '.cs': 'csharp',
  '.css': 'css',
  '.go': 'go',
  '.h': 'c',
  '.html': 'html',
  '.java': 'java',
  '.js': 'javascript',
  '.json': 'json',
  '.jsx': 'javascript',
  '.kt': 'kotlin',
  '.md': 'markdown',
  '.php': 'php',
  '.py': 'python',
  '.rb': 'ruby',
  '.rs': 'rust',
  '.sh': 'bash',
  '.sql': 'sql',
  '.swift': 'swift',
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.txt': 'text',
  '.xml': 'xml',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.zsh': 'zsh'
}
const mediaExtensions = {
  '.apng': 'image',
  '.avif': 'image',
  '.gif': 'image',
  '.jpeg': 'image',
  '.jpg': 'image',
  '.png': 'image',
  '.svg': 'image',
  '.webp': 'image',
  '.bmp': 'image',
  '.ico': 'image',
  '.mp3': 'audio',
  '.wav': 'audio',
  '.ogg': 'audio',
  '.m4a': 'audio',
  '.aac': 'audio',
  '.mp4': 'video',
  '.mov': 'video',
  '.webm': 'video',
  '.mkv': 'video'
}

export const parseJSON = (value, fallback = null) => {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  if (typeof value === 'object') {
    return value
  }
  try {
    return JSON.parse(value)
  } catch (error) {
    return fallback
  }
}

const parseJSONLike = (value) => {
  if (typeof value !== 'string') {
    return value
  }
  const text = value.trim()
  if (text.length < 2) {
    return value
  }
  const first = text[0]
  const last = text[text.length - 1]
  if (!((first === '{' && last === '}') || (first === '[' && last === ']'))) {
    return value
  }
  try {
    return JSON.parse(text)
  } catch {
    return value
  }
}

const isNonEmptyString = (value) => typeof value === 'string' && value.trim().length > 0

const titleize = (value, fallback) => {
  const text = String(value || '').trim()
  if (!text) {
    return fallback
  }
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

const extractTextCandidate = (value) => {
  if (isNonEmptyString(value)) {
    return value.trim()
  }

  if (Array.isArray(value)) {
    const strings = value
      .map((item) => extractTextCandidate(item))
      .filter(Boolean)
      .slice(0, 3)
    return strings.length > 0 ? strings.join('\n') : ''
  }

  if (!value || typeof value !== 'object') {
    return ''
  }

  for (const key of textKeys) {
    if (isNonEmptyString(value[key])) {
      return value[key].trim()
    }
  }

  for (const nestedKey of ['answer', 'summary', 'response', 'result']) {
    if (value[nestedKey] && typeof value[nestedKey] === 'object') {
      const nested = extractTextCandidate(value[nestedKey])
      if (nested) {
        return nested
      }
    }
  }

  for (const nestedKey of ['document_excerpt', 'document_excerpts', 'excerpts', 'excerpt']) {
    const nested = value[nestedKey]
    if (Array.isArray(nested)) {
      for (const entry of nested) {
        if (entry && typeof entry === 'object' && isNonEmptyString(entry.text)) {
          return entry.text.trim()
        }
      }
    }
    const nestedText = extractTextCandidate(nested)
    if (nestedText) {
      return nestedText
    }
  }

  for (const nestedKey of ['review_findings', 'findings', 'issues', 'risks']) {
    const nested = value[nestedKey]
    if (Array.isArray(nested)) {
      for (const entry of nested) {
        if (!entry || typeof entry !== 'object') {
          continue
        }
        if (isNonEmptyString(entry.title)) {
          return entry.title.trim()
        }
        if (isNonEmptyString(entry.description)) {
          return entry.description.trim()
        }
      }
    }
    const nestedText = extractTextCandidate(nested)
    if (nestedText) {
      return nestedText
    }
  }

  for (const nestedKey of [...pagedKeys, ...mediaKeys, ...fileBundleKeys]) {
    const nestedText = extractTextCandidate(value[nestedKey])
    if (nestedText) {
      return nestedText
    }
  }

  for (const nestedKey of documentPageKeys) {
    const nested = value[nestedKey]
    if (Array.isArray(nested)) {
      for (const entry of nested) {
        if (entry && typeof entry === 'object') {
          for (const pageKey of ['text', 'content', 'excerpt', 'summary']) {
            if (isNonEmptyString(entry[pageKey])) {
              return entry[pageKey].trim()
            }
          }
        }
      }
    }
    const nestedText = extractTextCandidate(nested)
    if (nestedText) {
      return nestedText
    }
  }

  for (const nestedKey of ['task_plan', 'plan', 'implementation_plan', 'steps', 'items']) {
    const nested = extractTextCandidate(value[nestedKey])
    if (nested) {
      return nested
    }
  }

  for (const key of ['text', 'description', 'details', 'title']) {
    if (isNonEmptyString(value[key])) {
      return value[key].trim()
    }
  }

  return ''
}

const normalizeStructuredResultRoot = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return value
  }

  if (!('task_plan' in value) && Array.isArray(value.steps)) {
    return {
      ...value,
      task_plan: {
        summary: value.summary || value.answer || '',
        steps: value.steps || [],
        decisions: value.decisions || []
      }
    }
  }

  return value
}

const hasArtifactType = (artifacts, artifactType) => artifacts.some((artifact) => artifact?.artifactType === artifactType)

const looksLikeCitationList = (value) => Array.isArray(value) && value.some((item) => item && typeof item === 'object' && !Array.isArray(item) && (
  isNonEmptyString(item.url) ||
  isNonEmptyString(item.link) ||
  (isNonEmptyString(item.source) && (isNonEmptyString(item.snippet) || isNonEmptyString(item.quote) || isNonEmptyString(item.excerpt)))
))

const looksLikeFindingList = (value) => Array.isArray(value) && value.some((item) => item && typeof item === 'object' && !Array.isArray(item) && (
  isNonEmptyString(item.severity) ||
  isNonEmptyString(item.level) ||
  isNonEmptyString(item.description) ||
  isNonEmptyString(item.details) ||
  isNonEmptyString(item.message)
))

const looksLikeCodeFileList = (value) => Array.isArray(value) && value.some((item) => item && typeof item === 'object' && !Array.isArray(item) && (
  isNonEmptyString(item.path) ||
  isNonEmptyString(item.file_path) ||
  isNonEmptyString(item.name)
) && (
  isNonEmptyString(item.content) ||
  isNonEmptyString(item.patch)
))

const looksLikeMediaList = (value) => Array.isArray(value) && normalizeMediaItems(value).length > 0

const looksLikeFileBundleList = (value) => Array.isArray(value) && normalizeFileBundle(value).length > 0

const looksLikeExcerptList = (value) => {
  if (isNonEmptyString(value)) {
    return true
  }
  if (!Array.isArray(value)) {
    return false
  }
  if (value.every((item) => isNonEmptyString(item))) {
    return true
  }
  return value.some((item) => item && typeof item === 'object' && !Array.isArray(item) && (
    isNonEmptyString(item.text) ||
    isNonEmptyString(item.content) ||
    isNonEmptyString(item.excerpt)
  ))
}

const appendImplicitListArtifacts = (artifacts, value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return
  }

  for (const key of implicitListKeys) {
    const candidate = value[key]
    if (candidate === undefined || candidate === null || candidate === '') {
      continue
    }

    if (!hasArtifactType(artifacts, 'citations') && looksLikeCitationList(candidate)) {
      const items = normalizeCitations(candidate)
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'citations',
          name: titleize(key, 'Citations'),
          payload: { items }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'review_findings') && looksLikeFindingList(candidate)) {
      const items = normalizeFindings(candidate)
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'review_findings',
          name: titleize(key, 'Review Findings'),
          payload: { items }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'code_files') && looksLikeCodeFileList(candidate)) {
      const files = normalizeCodeFiles(candidate)
      if (files.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'code_files',
          name: titleize(key, 'Code Files'),
          payload: { files }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'media_gallery') && looksLikeMediaList(candidate)) {
      const items = normalizeMediaItems(candidate)
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'media_gallery',
          name: titleize(key, 'Media Gallery'),
          payload: { items }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'file_bundle') && looksLikeFileBundleList(candidate)) {
      const files = normalizeFileBundle(candidate)
      if (files.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'file_bundle',
          name: titleize(key, 'File Bundle'),
          payload: { files }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'paged_collection')) {
      const pagedCollection = normalizePagedCollection(candidate, {
        context: value,
        title: titleize(key, 'Paged Collection')
      })
      if (pagedCollection) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'paged_collection',
          name: titleize(key, 'Paged Collection'),
          payload: pagedCollection
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'document_excerpt') && looksLikeExcerptList(candidate)) {
      const items = normalizeExcerpts(candidate)
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'document_excerpt',
          name: titleize(key, 'Document Excerpt'),
          payload: { items }
        }))
        continue
      }
    }

    if (!hasArtifactType(artifacts, 'table')) {
      const table = normalizeTable(candidate)
      if (table) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'table',
          name: titleize(key, 'Table'),
          payload: table
        }))
      }
    }
  }
}

const stableStringify = (value) => {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

const artifactSignature = (artifact) => stableStringify({
  artifactType: artifact.artifactType,
  payload: artifact.payload,
  mimeType: artifact.mimeType,
  uri: artifact.uri
})

const normalizeArtifactPayload = (artifactType, payload) => {
  const type = String(artifactType || '').trim() || 'answer'

  if (type === 'answer') {
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
      const text = extractTextCandidate(payload.text) || extractTextCandidate(payload)
      return {
        text: text || '',
        format: payload.format || 'markdown'
      }
    }
    return {
      text: extractTextCandidate(payload) || '',
      format: 'markdown'
    }
  }

  if (type === 'citations') {
    const items = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.items : payload
    return { items: normalizeCitations(items) }
  }

  if (type === 'workspace_summary') {
    return payload && typeof payload === 'object' && !Array.isArray(payload) ? { ...payload } : {}
  }

  if (type === 'review_findings') {
    const items = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.items : payload
    return { items: normalizeFindings(items) }
  }

  if (type === 'code_files') {
    const files = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.files : payload
    return { files: normalizeCodeFiles(files) }
  }

  if (type === 'code_patch') {
    const source = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {}
    const files = Array.isArray(source.files)
      ? source.files
        .filter((file) => file && typeof file === 'object')
        .map((file) => ({
          path: String(file.path || '').trim(),
          operation: String(file.operation || source.operation || 'modify').trim(),
          beforeSha256: file.before_sha256 || file.beforeSha256 || null,
          afterSha256: file.after_sha256 || file.afterSha256 || null,
          sizeBytes: Number(file.size_bytes ?? file.sizeBytes ?? 0) || 0,
          changed: file.changed !== false
        }))
        .filter((file) => file.path)
      : []
    return {
      operation: String(source.operation || '').trim(),
      status: String(source.status || '').trim(),
      dryRun: Boolean(source.dry_run ?? source.dryRun),
      files,
      diff: String(source.diff || ''),
      truncated: Boolean(source.truncated),
      reviewNotes: Array.isArray(source.review_notes)
        ? source.review_notes.map((item) => String(item || '').trim()).filter(Boolean)
        : Array.isArray(source.reviewNotes)
          ? source.reviewNotes.map((item) => String(item || '').trim()).filter(Boolean)
          : [],
      mergePolicy: String(source.merge_policy || source.mergePolicy || 'manual_review_required').trim()
    }
  }

  if (type === 'verification_report') {
    const source = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {}
    const logs = source.logs && typeof source.logs === 'object' && !Array.isArray(source.logs) ? source.logs : {}
    const runner = source.runner && typeof source.runner === 'object' && !Array.isArray(source.runner) ? source.runner : {}
    return {
      kind: String(source.kind || source.purpose || 'shell').trim() || 'shell',
      status: String(source.status || 'unknown').trim() || 'unknown',
      exitCode: source.exit_code ?? source.exitCode ?? null,
      command: Array.isArray(source.command) ? source.command.map((item) => String(item)) : [],
      cwd: String(source.cwd || '.').trim() || '.',
      durationMs: Number(source.duration_ms ?? source.durationMs ?? 0) || 0,
      timeoutSeconds: source.timeout_seconds ?? source.timeoutSeconds ?? null,
      summary: String(source.summary || '').trim(),
      failureCategory: source.failure_category ?? source.failureCategory ?? null,
      truncated: Boolean(source.truncated),
      logs: {
        stdout: String(logs.stdout || source.stdout || ''),
        stderr: String(logs.stderr || source.stderr || '')
      },
      runner,
      selector: source.selector ?? null,
      target: source.target ?? null
    }
  }

  if (type === 'file_bundle') {
    const files = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.files : payload
    return { files: normalizeFileBundle(files) }
  }

  if (type === 'archive_bundle') {
    return normalizeArchiveBundle(payload, {
      title: payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.title || '' : '',
      force: true
    }) || payload
  }

  if (type === 'media_gallery') {
    const items = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.items : payload
    return { items: normalizeMediaItems(items) }
  }

  if (type === 'directory_tree') {
    return normalizeDirectoryTree(payload, {
      title: payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.title || '' : '',
      force: true
    }) || payload
  }

  if (type === 'document_pages') {
    return normalizeDocumentPages(payload, {
      title: payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.title || '' : '',
      force: true
    }) || payload
  }

  if (type === 'document_excerpt') {
    const items = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.items : payload
    return { items: normalizeExcerpts(items) }
  }

  if (type === 'paged_collection') {
    return normalizePagedCollection(payload, {
      title: payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.title || '' : '',
      force: true
    }) || payload
  }

  if (type === 'table') {
    return normalizeTable(payload) || payload
  }

  return payload
}

export const normalizeArtifact = (raw = {}) => {
  const artifactType = raw.artifact_type || raw.artifactType || 'answer'
  const artifact = {
    id: raw.id || '',
    runId: raw.run_id || raw.runId || '',
    stepId: raw.step_id || raw.stepId || '',
    artifactType,
    name: raw.name || 'Untitled Artifact',
    mimeType: raw.mime_type || raw.mimeType || '',
    uri: raw.uri || '',
    payload: normalizeArtifactPayload(
      artifactType,
      parseJSON(raw.payload, {})
    ),
    metadata: parseJSON(raw.metadata, {}),
    createdAt: raw.created_at || raw.createdAt || null,
    updatedAt: raw.updated_at || raw.updatedAt || null
  }

  return {
    ...artifact,
    clientKey: raw.client_key || raw.clientKey || raw.id || artifactSignature(artifact)
  }
}

export const mergeArtifacts = (...groups) => {
  const merged = []
  const seen = new Set()

  for (const group of groups) {
    if (!Array.isArray(group)) continue
    for (const item of group) {
      if (!item || typeof item !== 'object') continue
      const artifact = normalizeArtifact(item)
      const signature = artifactSignature(artifact)
      if (seen.has(signature)) continue
      seen.add(signature)
      merged.push(artifact)
    }
  }

  return merged.sort((left, right) => {
    const priorityDiff = (artifactPriority[left.artifactType] ?? 100) - (artifactPriority[right.artifactType] ?? 100)
    if (priorityDiff !== 0) return priorityDiff
    return String(left.name || '').localeCompare(String(right.name || ''))
  })
}

const normalizeFindings = (value) => {
  if (!Array.isArray(value)) return []
  return value.map((item, index) => {
    if (item && typeof item === 'object') {
      return {
        title: item.title || item.summary || item.message || `Finding ${index + 1}`,
        severity: item.severity || item.level || 'info',
        description: item.description || item.details || item.message || '',
        path: item.path || item.file || '',
        line: item.line || null,
        code: item.code || '',
        metadata: item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
          ? { ...item.metadata }
          : Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'summary', 'message', 'severity', 'level', 'description', 'details', 'path', 'file', 'line', 'code', 'metadata'].includes(key)))
      }
    }
    return {
      title: `Finding ${index + 1}`,
      severity: 'info',
      description: String(item || '')
    }
  })
}

const normalizeCitations = (value) => {
  if (!Array.isArray(value)) return []
  return value.map((item, index) => {
    if (item && typeof item === 'object') {
      return {
        title: item.title || item.name || item.source || `Source ${index + 1}`,
        url: item.url || item.link || '',
        snippet: item.snippet || item.quote || item.excerpt || '',
        metadata: item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
          ? { ...item.metadata }
          : Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'name', 'source', 'url', 'link', 'snippet', 'quote', 'excerpt', 'metadata'].includes(key)))
      }
    }
    return {
      title: `Source ${index + 1}`,
      snippet: String(item || '')
    }
  })
}

const normalizeCodeFiles = (value) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.entries(value).map(([path, content]) => ({
      path,
      language: '',
      content: typeof content === 'string' ? content : JSON.stringify(content, null, 2),
      metadata: {}
    }))
  }
  if (!Array.isArray(value)) return []
  return value.map((item, index) => {
    if (item && typeof item === 'object') {
      const content = item.content ?? item.patch ?? ''
      return {
        path: item.path || item.file_path || item.name || `file-${index + 1}`,
        language: item.language || '',
        content: typeof content === 'string' ? content : JSON.stringify(content || {}, null, 2),
        metadata: item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
          ? { ...item.metadata }
          : Object.fromEntries(Object.entries(item).filter(([key]) => !['path', 'file_path', 'name', 'language', 'content', 'patch', 'metadata'].includes(key)))
      }
    }
    return {
      path: `file-${index + 1}`,
      language: '',
      content: String(item || ''),
      metadata: {}
    }
  })
}

const normalizeExcerpts = (value) => {
  if (isNonEmptyString(value)) {
    return [{ title: '', text: value.trim(), source: '', metadata: {} }]
  }
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (item && typeof item === 'object') {
      return {
        title: item.title || item.heading || '',
        text: item.text || item.content || item.excerpt || item.preview || item.snippet || '',
        source: item.source || '',
        metadata: item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
          ? { ...item.metadata }
          : Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'heading', 'text', 'content', 'excerpt', 'preview', 'snippet', 'source', 'metadata'].includes(key)))
      }
    }
    return { title: '', text: String(item || ''), source: '', metadata: {} }
  })
}

const normalizeTable = (value) => {
  if (!value) return null
  if (Array.isArray(value) && value.length > 0 && value.every((row) => row && typeof row === 'object' && !Array.isArray(row))) {
    return {
      columns: Object.keys(value[0]),
      rows: value
    }
  }
  if (typeof value === 'object' && !Array.isArray(value) && Array.isArray(value.rows)) {
    return {
      title: value.title || '',
      columns: Array.isArray(value.columns) ? value.columns : (value.rows[0] && typeof value.rows[0] === 'object' ? Object.keys(value.rows[0]) : []),
      rows: value.rows
    }
  }
  return null
}

const normalizeMetadata = (value, excludedKeys = []) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  const metadata = value.metadata && typeof value.metadata === 'object' && !Array.isArray(value.metadata)
    ? { ...value.metadata }
    : {}
  for (const [key, item] of Object.entries(value)) {
    if (!excludedKeys.includes(key) && key !== 'metadata') {
      metadata[key] = item
    }
  }
  return metadata
}

const normalizeMCPContentEntries = (value) => {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') return [value]
  return []
}

const coerceInt = (value) => {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

const coerceBool = (value) => {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'string') {
    const text = value.trim().toLowerCase()
    if (['true', '1', 'yes'].includes(text)) return true
    if (['false', '0', 'no'].includes(text)) return false
  }
  return null
}

const normalizeInlineUri = (source, mimeType = '', data = '') => {
  const sourceText = String(source || '').trim()
  if (sourceText) {
    return sourceText
  }
  if (!isNonEmptyString(data)) {
    return ''
  }
  const dataText = data.trim()
  if (dataText.startsWith('data:')) {
    return dataText
  }
  return `data:${String(mimeType || 'application/octet-stream').trim() || 'application/octet-stream'};base64,${dataText}`
}

const guessMediaKind = (path, mimeType = '') => {
  const normalizedMime = String(mimeType || '').trim().toLowerCase()
  if (normalizedMime.startsWith('image/')) return 'image'
  if (normalizedMime.startsWith('video/')) return 'video'
  if (normalizedMime.startsWith('audio/')) return 'audio'

  const normalizedPath = String(path || '').trim().toLowerCase()
  const extension = normalizedPath.includes('.') ? `.${normalizedPath.split('.').pop()}` : ''
  return mediaExtensions[extension] || ''
}

const extractPaginationMetadata = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }

  let source = value.pagination && typeof value.pagination === 'object' && !Array.isArray(value.pagination)
    ? value.pagination
    : null
  if (!source) {
    for (const alias of ['page_info', 'pageInfo']) {
      if (value[alias] && typeof value[alias] === 'object' && !Array.isArray(value[alias])) {
        source = value[alias]
        break
      }
    }
  }
  source = source || value

  const metadata = {
    cursor: source.cursor || '',
    next_cursor: source.next_cursor || source.nextCursor || '',
    previous_cursor: source.previous_cursor || source.previousCursor || source.prev_cursor || '',
    has_more: coerceBool(source.has_more ?? source.hasMore),
    page: coerceInt(source.page ?? source.page_index ?? source.pageIndex),
    page_size: coerceInt(source.page_size ?? source.pageSize ?? source.limit),
    offset: coerceInt(source.offset),
    total_count: coerceInt(source.total_count ?? source.totalCount ?? source.total)
  }

  return Object.fromEntries(Object.entries(metadata).filter(([, item]) => item !== null && item !== ''))
}

const extractPagedItems = (value) => {
  if (Array.isArray(value)) return value
  if (!value || typeof value !== 'object') return []
  for (const key of [...implicitListKeys, 'rows']) {
    if (Array.isArray(value[key])) {
      return value[key]
    }
  }
  return []
}

const normalizePagedCollection = (value, { context = null, title = '', force = false } = {}) => {
  const items = extractPagedItems(value)
  if (!Array.isArray(items) || items.length === 0) {
    return null
  }

  const pagination = extractPaginationMetadata(value && typeof value === 'object' && !Array.isArray(value) ? value : context)
  if (!force && Object.keys(pagination).length === 0) {
    return null
  }

  const columns = items[0] && typeof items[0] === 'object' && !Array.isArray(items[0])
    ? Object.keys(items[0])
    : []

  return {
    title,
    items,
    columns,
    display: columns.length > 0 ? 'table' : 'list',
    pagination: {
      ...pagination,
      returned_count: items.length
    }
  }
}

const normalizeMediaItems = (value) => {
  const entries = Array.isArray(value) ? value : (value && typeof value === 'object' ? [value] : [])
  return entries.flatMap((entry, index) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      return []
    }
    const resource = entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)
      ? entry.resource
      : {}
    const source = String(entry.uri || entry.url || entry.href || entry.resource_link || entry.resourceLink || resource.uri || resource.url || resource.href || resource.resource_link || resource.resourceLink || '').trim()
    const mimeType = String(entry.mimeType || entry.mime_type || resource.mimeType || resource.mime_type || '').trim()
    const path = String(entry.path || entry.file_path || resource.path || resource.file_path || resource.name || pathFromSource(source)).trim()
    const kind = guessMediaKind(path, mimeType)
    if (!['image', 'video', 'audio'].includes(kind)) {
      return []
    }
    const data = entry.data || entry.blob || resource.data || resource.blob || ''
    const title = String(entry.title || entry.name || resource.title || resource.name || path || `Media ${index + 1}`).trim()
    return [{
      title,
      uri: normalizeInlineUri(source, mimeType, data),
      mime_type: mimeType,
      kind,
      alt: String(entry.alt || entry.description || resource.alt || title).trim(),
      path,
      source,
      size_bytes: coerceInt(entry.size_bytes ?? entry.sizeBytes ?? entry.bytes ?? resource.size_bytes ?? resource.sizeBytes ?? resource.bytes),
      metadata: normalizeMetadata(
        { ...resource, ...entry },
        ['resource', 'uri', 'url', 'href', 'mimeType', 'mime_type', 'path', 'file_path', 'name', 'title', 'alt', 'description', 'data', 'blob', 'size_bytes', 'sizeBytes', 'bytes']
      )
    }]
  })
}

const normalizeFileBundle = (value) => {
  const entries = Array.isArray(value) ? value : (value && typeof value === 'object' ? [value] : [])
  return entries.flatMap((entry, index) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      return []
    }
    const resource = entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)
      ? entry.resource
      : {}
    const source = String(entry.uri || entry.url || entry.href || entry.resource_link || entry.resourceLink || resource.uri || resource.url || resource.href || resource.resource_link || resource.resourceLink || '').trim()
    const mimeType = String(entry.mimeType || entry.mime_type || resource.mimeType || resource.mime_type || '').trim()
    const path = String(entry.path || entry.file_path || resource.path || resource.file_path || resource.name || pathFromSource(source)).trim()
    if (!(source || mimeType || isNonEmptyString(entry.name) || isNonEmptyString(entry.title) || isNonEmptyString(resource.name) || isNonEmptyString(resource.title) || isNonEmptyString(entry.data) || isNonEmptyString(resource.data))) {
      return []
    }
    if (['image', 'video', 'audio'].includes(guessMediaKind(path, mimeType))) {
      return []
    }

    let previewText = ''
    for (const candidate of [entry.preview_text, entry.previewText, entry.text, entry.content, entry.excerpt, resource.preview_text, resource.previewText, resource.text, resource.content, resource.excerpt]) {
      if (isNonEmptyString(candidate)) {
        previewText = candidate.trim()
        break
      }
    }

    return [{
      name: String(entry.name || entry.title || resource.name || resource.title || path || `File ${index + 1}`).trim(),
      path,
      uri: normalizeInlineUri(source, mimeType, entry.data || resource.data || ''),
      mime_type: mimeType,
      size_bytes: coerceInt(entry.size_bytes ?? entry.sizeBytes ?? entry.bytes ?? resource.size_bytes ?? resource.sizeBytes ?? resource.bytes),
      description: String(entry.description || resource.description || '').trim(),
      preview_text: previewText,
      source,
      metadata: normalizeMetadata(
        { ...resource, ...entry },
        ['resource', 'uri', 'url', 'href', 'mimeType', 'mime_type', 'path', 'file_path', 'name', 'title', 'description', 'preview_text', 'previewText', 'text', 'content', 'excerpt', 'data', 'blob', 'size_bytes', 'sizeBytes', 'bytes']
      )
    }]
  })
}

const pathSegments = (value) => String(value || '').trim().replace(/^\/+|\/+$/g, '').split('/').filter(Boolean)

const coerceTreeNodeType = (value) => {
  if (typeof value === 'boolean') {
    return value ? 'directory' : 'file'
  }
  const text = String(value || '').trim().toLowerCase()
  if (['dir', 'directory', 'folder'].includes(text)) return 'directory'
  if (['file', 'document', 'blob', 'leaf'].includes(text)) return 'file'
  return ''
}

const normalizeDirectoryTreeNode = (entry, index = 0) => {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    const path = String(entry || '').trim()
    if (!path) return null
    const trimmedPath = path.replace(/\/+$/, '')
    const name = trimmedPath.split('/').filter(Boolean).pop() || trimmedPath || `Node ${index + 1}`
    return {
      name,
      path: trimmedPath,
      node_type: path.endsWith('/') ? 'directory' : 'file',
      children: [],
      metadata: {}
    }
  }

  const resource = entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)
    ? entry.resource
    : {}
  const merged = { ...resource, ...entry }
  const rawPath = String(
    merged.path ||
    merged.file_path ||
    merged.uri ||
    merged.url ||
    merged.href ||
    merged.name ||
    merged.title ||
    ''
  ).trim()
  const path = rawPath.replace(/\/+$/, '')
  const childrenSource = Array.isArray(merged.children)
    ? merged.children
    : Array.isArray(merged.nodes)
      ? merged.nodes
      : Array.isArray(merged.entries)
        ? merged.entries
        : Array.isArray(merged.items)
          ? merged.items
          : []
  let nodeType = coerceTreeNodeType(merged.node_type) ||
    coerceTreeNodeType(merged.type) ||
    coerceTreeNodeType(merged.kind) ||
    coerceTreeNodeType(merged.is_dir) ||
    coerceTreeNodeType(merged.is_directory)
  if (!nodeType) {
    nodeType = childrenSource.length > 0 || rawPath.endsWith('/') ? 'directory' : 'file'
  }

  const children = childrenSource
    .map((item, childIndex) => normalizeDirectoryTreeNode(item, childIndex))
    .filter(Boolean)
  if (children.length > 0) {
    nodeType = 'directory'
  }

  return {
    name: String(merged.name || merged.title || path.split('/').filter(Boolean).pop() || path || `Node ${index + 1}`).trim(),
    path,
    node_type: nodeType,
    uri: String(merged.uri || merged.url || merged.href || '').trim(),
    mime_type: String(merged.mimeType || merged.mime_type || '').trim(),
    size_bytes: coerceInt(merged.size_bytes ?? merged.sizeBytes ?? merged.bytes),
    children,
    metadata: normalizeMetadata(
      merged,
      ['metadata', 'resource', 'name', 'title', 'path', 'file_path', 'type', 'kind', 'node_type', 'is_dir', 'is_directory', 'children', 'nodes', 'entries', 'items', 'uri', 'url', 'href', 'mimeType', 'mime_type', 'size_bytes', 'sizeBytes', 'bytes']
    )
  }
}

const insertDirectoryPath = (rootNodes, entry, index) => {
  const path = String(entry.path || entry.file_path || entry.name || entry.title || '').trim()
  const segments = pathSegments(path)
  if (segments.length === 0) {
    const normalized = normalizeDirectoryTreeNode(entry, index)
    if (normalized) rootNodes.push(normalized)
    return
  }

  let nodeType = coerceTreeNodeType(entry.node_type) ||
    coerceTreeNodeType(entry.type) ||
    coerceTreeNodeType(entry.kind) ||
    coerceTreeNodeType(entry.is_dir) ||
    coerceTreeNodeType(entry.is_directory)
  if (!nodeType) {
    nodeType = path.endsWith('/') ? 'directory' : 'file'
  }

  let current = rootNodes
  const accumulated = []
  segments.forEach((segment, segmentIndex) => {
    accumulated.push(segment)
    const isLeaf = segmentIndex === segments.length - 1
    const expectedType = isLeaf ? nodeType : 'directory'
    let existing = current.find((item) => item.name === segment)
    if (!existing) {
      existing = {
        name: segment,
        path: accumulated.join('/'),
        node_type: expectedType,
        children: [],
        metadata: {}
      }
      current.push(existing)
    }
    if (!isLeaf) {
      existing.node_type = 'directory'
      existing.children = Array.isArray(existing.children) ? existing.children : []
      current = existing.children
      return
    }

    const normalized = normalizeDirectoryTreeNode(entry, index) || {}
    Object.assign(existing, {
      name: segment,
      path: accumulated.join('/'),
      node_type: expectedType,
      uri: normalized.uri || '',
      mime_type: normalized.mime_type || '',
      size_bytes: normalized.size_bytes ?? null,
      metadata: normalized.metadata || {}
    })
    if (Array.isArray(normalized.children) && normalized.children.length > 0) {
      existing.children = normalized.children
      existing.node_type = 'directory'
    }
  })
}

const countDirectoryTree = (nodes, depth = 1) => {
  let fileCount = 0
  let directoryCount = 0
  let maxDepth = Array.isArray(nodes) && nodes.length > 0 ? depth : 0
  for (const node of Array.isArray(nodes) ? nodes : []) {
    const children = Array.isArray(node.children) ? node.children : []
    if (node.node_type === 'directory') {
      directoryCount += 1
    } else {
      fileCount += 1
    }
    const childCounts = countDirectoryTree(children, depth + 1)
    fileCount += childCounts.file_count
    directoryCount += childCounts.directory_count
    maxDepth = Math.max(maxDepth, childCounts.max_depth)
  }
  return { file_count: fileCount, directory_count: directoryCount, max_depth: maxDepth }
}

const normalizeDirectoryTree = (value, { title = '', force = false } = {}) => {
  let rootName = ''
  let nodes = []
  let explicitStructure = false

  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const childEntries = Array.isArray(value.children)
      ? value.children
      : Array.isArray(value.nodes)
        ? value.nodes
        : Array.isArray(value.entries)
          ? value.entries
          : Array.isArray(value.items)
            ? value.items
            : []
    rootName = String(value.name || value.title || value.path || '').trim().replace(/\/+$/, '')
    if (childEntries.length > 0) {
      explicitStructure = true
      nodes = childEntries.map((item, index) => normalizeDirectoryTreeNode(item, index)).filter(Boolean)
    } else if (typeof value.path === 'string' && (
      coerceTreeNodeType(value.type) === 'directory' ||
      coerceTreeNodeType(value.kind) === 'directory' ||
      String(value.path || '').endsWith('/')
    )) {
      const normalized = normalizeDirectoryTreeNode(value, 0)
      if (normalized) nodes = [normalized]
    }
  } else if (Array.isArray(value)) {
    const entries = value.filter((item) => (typeof item === 'string' && String(item).trim()) || (item && typeof item === 'object' && !Array.isArray(item)))
    if (entries.length > 0) {
      if (entries.some((item) => item && typeof item === 'object' && Array.isArray(item.children))) {
        nodes = entries.map((item, index) => normalizeDirectoryTreeNode(item, index)).filter(Boolean)
      } else {
        const flatRoot = []
        entries.forEach((item, index) => {
          if (item && typeof item === 'object' && !Array.isArray(item)) {
            insertDirectoryPath(flatRoot, item, index)
          } else {
            insertDirectoryPath(flatRoot, { path: String(item) }, index)
          }
        })
        nodes = flatRoot
      }
    }
  }

  if (nodes.length === 0) return null
  if (!force && !(
    explicitStructure ||
    nodes.some((node) => Array.isArray(node.children) && node.children.length > 0) ||
    nodes.some((node) => node.node_type === 'directory')
  )) {
    return null
  }

  return {
    title: title || rootName,
    root_name: rootName,
    nodes,
    summary: countDirectoryTree(nodes)
  }
}

const looksLikeDocumentPageEntry = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  if (value.page !== undefined || value.page_number !== undefined || value.pageNumber !== undefined) return true
  return ['text', 'content', 'excerpt', 'thumbnail_uri', 'thumbnailUrl', 'image_uri', 'imageUrl'].some((key) => isNonEmptyString(value[key]))
}

const normalizeDocumentPages = (value, { title = '', force = false } = {}) => {
  let payload = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  let pagesSource = value
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    for (const key of ['pages', 'items', 'entries']) {
      if (Array.isArray(payload[key])) {
        pagesSource = payload[key]
        break
      }
    }
  }

  if (!Array.isArray(pagesSource) || pagesSource.length === 0) return null
  if (!force && !pagesSource.some((item) => looksLikeDocumentPageEntry(item))) return null

  const pages = pagesSource.map((entry, index) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      const text = String(entry || '').trim()
      if (!text) return null
      return {
        page_number: index + 1,
        title: `Page ${index + 1}`,
        text,
        uri: '',
        thumbnail_uri: '',
        mime_type: '',
        source: '',
        metadata: {}
      }
    }

    const pageNumber = coerceInt(entry.page_number ?? entry.pageNumber ?? entry.page ?? entry.index) || index + 1
    return {
      page_number: pageNumber,
      title: String(entry.title || entry.heading || `Page ${pageNumber}`).trim(),
      text: String(entry.text || entry.content || entry.excerpt || '').trim(),
      uri: String(entry.uri || entry.url || '').trim(),
      thumbnail_uri: String(entry.thumbnail_uri || entry.thumbnailUrl || entry.image_uri || entry.imageUrl || '').trim(),
      mime_type: String(entry.mimeType || entry.mime_type || '').trim(),
      source: String(entry.source || entry.uri || entry.url || '').trim(),
      metadata: normalizeMetadata(
        entry,
        ['metadata', 'page_number', 'pageNumber', 'page', 'index', 'title', 'heading', 'text', 'content', 'excerpt', 'uri', 'url', 'thumbnail_uri', 'thumbnailUrl', 'image_uri', 'imageUrl', 'mimeType', 'mime_type', 'source']
      )
    }
  }).filter(Boolean)

  if (pages.length === 0) return null

  return {
    title: title || String(payload.title || payload.name || '').trim(),
    page_count: coerceInt(payload.page_count ?? payload.pageCount) || pages.length,
    pages
  }
}

const archiveFormatFromValue = (value) => {
  const text = String(value || '').trim().toLowerCase()
  if (!text) return ''
  for (const suffix of ['.tar.gz', '.tgz', '.tar', '.zip', '.rar', '.7z', '.gz']) {
    if (text.endsWith(suffix)) {
      return suffix.replace(/^\./, '')
    }
  }
  if (['zip', 'tar', 'tgz', 'tar.gz', 'rar', '7z', 'gz'].includes(text)) {
    return text
  }
  return ''
}

const looksLikeArchivePayload = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  if (archiveFormatFromValue(value.format)) return true
  if (archiveFormatFromValue(value.path) || archiveFormatFromValue(value.name) || archiveFormatFromValue(value.uri)) return true
  return ['application/zip', 'application/x-tar', 'application/gzip', 'application/x-7z-compressed', 'application/vnd.rar'].includes(
    String(value.mimeType || value.mime_type || '').trim().toLowerCase()
  )
}

const normalizeArchiveBundle = (value, { title = '', force = false } = {}) => {
  const payload = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  let entriesSource = value
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    for (const key of ['entries', 'items', 'members', 'files']) {
      if (Array.isArray(payload[key])) {
        entriesSource = payload[key]
        break
      }
    }
  }

  if (!Array.isArray(entriesSource) || entriesSource.length === 0) return null
  if (!force && !looksLikeArchivePayload(payload)) return null

  let totalSize = 0
  let totalCompressedSize = 0
  const files = entriesSource.map((entry, index) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      const path = String(entry || '').trim()
      if (!path) return null
      return {
        name: path.split('/').filter(Boolean).pop() || path,
        path,
        mime_type: '',
        size_bytes: null,
        compressed_size_bytes: null,
        checksum: '',
        description: '',
        metadata: {}
      }
    }

    const sizeBytes = coerceInt(entry.size_bytes ?? entry.sizeBytes ?? entry.bytes)
    const compressedSizeBytes = coerceInt(entry.compressed_size_bytes ?? entry.compressedSizeBytes ?? entry.compressed_bytes ?? entry.compressedBytes)
    if (typeof sizeBytes === 'number') totalSize += sizeBytes
    if (typeof compressedSizeBytes === 'number') totalCompressedSize += compressedSizeBytes
    return {
      name: String(entry.name || entry.title || entry.path || entry.file_path || `Entry ${index + 1}`).trim(),
      path: String(entry.path || entry.file_path || entry.name || '').trim(),
      mime_type: String(entry.mimeType || entry.mime_type || '').trim(),
      size_bytes: sizeBytes,
      compressed_size_bytes: compressedSizeBytes,
      checksum: String(entry.checksum || entry.digest || entry.sha256 || '').trim(),
      description: String(entry.description || '').trim(),
      metadata: normalizeMetadata(
        entry,
        ['metadata', 'name', 'title', 'path', 'file_path', 'mimeType', 'mime_type', 'size_bytes', 'sizeBytes', 'bytes', 'compressed_size_bytes', 'compressedSizeBytes', 'compressed_bytes', 'compressedBytes', 'checksum', 'digest', 'sha256', 'description']
      )
    }
  }).filter(Boolean)

  if (files.length === 0) return null

  const archiveName = String(payload.name || payload.title || payload.path || payload.uri || '').trim()
  return {
    title: title || archiveName,
    archive_name: archiveName,
    format: archiveFormatFromValue(payload.format) || archiveFormatFromValue(payload.path) || archiveFormatFromValue(payload.name) || archiveFormatFromValue(payload.uri),
    entry_count: files.length,
    total_size_bytes: totalSize || null,
    total_compressed_size_bytes: totalCompressedSize || null,
    files
  }
}

export const buildArtifactsFromStructuredResult = (value, fallbackText = '') => {
  const artifacts = []
  const normalizedValue = normalizeStructuredResultRoot(parseJSONLike(value))
  const answerText = extractTextCandidate(normalizedValue) || extractTextCandidate(fallbackText)
  const structured = normalizedValue && typeof normalizedValue === 'object' ? normalizedValue : null

  if (answerText) {
    artifacts.push(normalizeArtifact({
      artifact_type: 'answer',
      name: 'Final Answer',
      payload: { text: answerText, format: 'markdown' }
    }))
  }

  if (structured && !Array.isArray(structured)) {
    for (const key of ['task_plan', 'plan', 'implementation_plan']) {
      if (structured[key] !== undefined) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'task_plan',
          name: titleize(key, 'Task Plan'),
          payload: structured[key]
        }))
        break
      }
    }

    for (const key of ['citations', 'sources', 'references']) {
      const items = normalizeCitations(structured[key])
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'citations',
          name: titleize(key, 'Citations'),
          payload: { items }
        }))
        break
      }
    }

    for (const key of ['review_findings', 'findings', 'issues', 'risks']) {
      const items = normalizeFindings(structured[key])
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'review_findings',
          name: titleize(key, 'Review Findings'),
          payload: { items }
        }))
        break
      }
    }

    for (const key of ['code_files', 'files']) {
      const files = normalizeCodeFiles(structured[key])
      if (files.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'code_files',
          name: titleize(key, 'Code Files'),
          payload: { files }
        }))
        break
      }
    }

    for (const key of directoryTreeKeys) {
      const directoryTree = normalizeDirectoryTree(structured[key], {
        title: titleize(key, 'Directory Tree'),
        force: Object.prototype.hasOwnProperty.call(structured, key)
      })
      if (directoryTree) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'directory_tree',
          name: titleize(key, 'Directory Tree'),
          payload: directoryTree
        }))
        break
      }
    }

    for (const key of documentPageKeys) {
      const documentPages = normalizeDocumentPages(structured[key], {
        title: titleize(key, 'Document Pages'),
        force: Object.prototype.hasOwnProperty.call(structured, key)
      })
      if (documentPages) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'document_pages',
          name: titleize(key, 'Document Pages'),
          payload: documentPages
        }))
        break
      }
    }

    for (const key of pagedKeys) {
      const pagedCollection = normalizePagedCollection(structured[key], {
        context: structured,
        title: titleize(key, 'Paged Collection'),
        force: Object.prototype.hasOwnProperty.call(structured, key)
      })
      if (pagedCollection) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'paged_collection',
          name: titleize(key, 'Paged Collection'),
          payload: pagedCollection
        }))
        break
      }
    }

    for (const key of mediaKeys) {
      const items = normalizeMediaItems(structured[key])
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'media_gallery',
          name: titleize(key, 'Media Gallery'),
          payload: { items }
        }))
        break
      }
    }

    for (const key of fileBundleKeys) {
      const files = normalizeFileBundle(structured[key])
      if (files.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'file_bundle',
          name: titleize(key, 'File Bundle'),
          payload: { files }
        }))
        break
      }
    }

    for (const key of archiveBundleKeys) {
      const archiveBundle = normalizeArchiveBundle(structured[key], {
        title: titleize(key, 'Archive Bundle'),
        force: Object.prototype.hasOwnProperty.call(structured, key)
      })
      if (archiveBundle) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'archive_bundle',
          name: titleize(key, 'Archive Bundle'),
          payload: archiveBundle
        }))
        break
      }
    }

    for (const key of ['table', 'tables', 'rows']) {
      const table = normalizeTable(structured[key])
      if (table) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'table',
          name: titleize(key, 'Table'),
          payload: table
        }))
        break
      }
    }

    for (const key of ['document_excerpt', 'document_excerpts', 'excerpts', 'excerpt']) {
      const items = normalizeExcerpts(structured[key])
      if (items.length > 0) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'document_excerpt',
          name: titleize(key, 'Document Excerpt'),
          payload: { items }
        }))
        break
      }
    }

    appendImplicitListArtifacts(artifacts, structured)

    if (!hasArtifactType(artifacts, 'directory_tree')) {
      const directoryTree = normalizeDirectoryTree(structured)
      if (directoryTree) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'directory_tree',
          name: directoryTree.title || 'Directory Tree',
          payload: directoryTree
        }))
      }
    }

    if (!hasArtifactType(artifacts, 'document_pages')) {
      const documentPages = normalizeDocumentPages(structured)
      if (documentPages) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'document_pages',
          name: documentPages.title || 'Document Pages',
          payload: documentPages
        }))
      }
    }

    if (!hasArtifactType(artifacts, 'archive_bundle')) {
      const archiveBundle = normalizeArchiveBundle(structured)
      if (archiveBundle) {
        artifacts.push(normalizeArtifact({
          artifact_type: 'archive_bundle',
          name: archiveBundle.title || 'Archive Bundle',
          payload: archiveBundle
        }))
      }
    }
  }

  if (Array.isArray(value)) {
    const directoryTree = normalizeDirectoryTree(value)
    if (directoryTree) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'directory_tree',
        name: directoryTree.title || 'Directory Tree',
        payload: directoryTree
      }))
    }

    const documentPages = normalizeDocumentPages(value)
    if (documentPages) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'document_pages',
        name: documentPages.title || 'Document Pages',
        payload: documentPages
      }))
    }

    const mediaItems = normalizeMediaItems(value)
    if (mediaItems.length > 0) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'media_gallery',
        name: 'Media Gallery',
        payload: { items: mediaItems }
      }))
    }

    const bundleFiles = normalizeFileBundle(value)
    if (bundleFiles.length > 0) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'file_bundle',
        name: 'File Bundle',
        payload: { files: bundleFiles }
      }))
    }

    const archiveBundle = normalizeArchiveBundle(value)
    if (archiveBundle) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'archive_bundle',
        name: archiveBundle.title || 'Archive Bundle',
        payload: archiveBundle
      }))
    }

    const table = normalizeTable(value)
    if (table) {
      artifacts.push(normalizeArtifact({
          artifact_type: 'table',
        name: 'Result Table',
        payload: table
      }))
    }
  }

  return mergeArtifacts(artifacts)
}

const normalizeMCPContentItems = (items = []) => {
  return normalizeMCPContentEntries(items)
    .map((item, index) => {
      if (!item || typeof item !== 'object') {
        return {
          kind: 'text',
          title: `Content ${index + 1}`,
          text: String(item || '').trim(),
          source: '',
          metadata: {}
        }
      }

      const itemType = String(item.type || '').trim().toLowerCase()
      if (itemType === 'text') {
        return {
          kind: 'text',
          title: item.title || '',
          text: String(item.text || '').trim(),
          source: item.uri || item.url || item.href || item.resource_link || item.resourceLink || '',
          metadata: normalizeMetadata(
            item,
            ['metadata', 'type', 'title', 'name', 'text', 'content', 'excerpt', 'uri', 'url', 'href', 'resource_link', 'resourceLink', 'mimeType', 'mime_type']
          )
        }
      }

      const payloadText = extractTextCandidate(item) || (typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item || ''))
      return {
        kind: itemType || 'json',
        title: item.title || item.name || `Content ${index + 1}`,
        text: payloadText.trim(),
        source: item.uri || item.url || item.href || item.resource_link || item.resourceLink || item.mimeType || item.mime_type || '',
        metadata: normalizeMetadata(
          item,
          ['metadata', 'type', 'title', 'name', 'text', 'content', 'excerpt', 'uri', 'url', 'href', 'resource_link', 'resourceLink', 'mimeType', 'mime_type']
        )
      }
    })
    .filter((item) => item.text)
}

const pathFromSource = (source) => {
  const text = String(source || '').trim()
  if (!text) {
    return ''
  }
  try {
    const url = new URL(text)
    return url.pathname.split('/').filter(Boolean).pop() || text
  } catch {
    return text.split('#')[0].split('?')[0].split('/').filter(Boolean).pop() || text
  }
}

const guessLanguage = (path, mimeType = '') => {
  const normalizedPath = String(path || '').trim().toLowerCase()
  const extension = normalizedPath.includes('.') ? `.${normalizedPath.split('.').pop()}` : ''
  if (codeFileExtensions[extension]) {
    return codeFileExtensions[extension]
  }

  const normalizedMime = String(mimeType || '').trim().toLowerCase()
  const mimeTokens = {
    javascript: 'javascript',
    typescript: 'typescript',
    json: 'json',
    markdown: 'markdown',
    html: 'html',
    css: 'css',
    xml: 'xml',
    yaml: 'yaml',
    python: 'python',
    shell: 'bash'
  }
  for (const [token, language] of Object.entries(mimeTokens)) {
    if (normalizedMime.includes(token)) {
      return language
    }
  }
  return ''
}

const isCodeLikeContent = (path, mimeType) => {
  const normalizedPath = String(path || '').trim().toLowerCase()
  const extension = normalizedPath.includes('.') ? `.${normalizedPath.split('.').pop()}` : ''
  if (codeFileExtensions[extension] && extension !== '.txt') {
    return true
  }

  const normalizedMime = String(mimeType || '').trim().toLowerCase()
  if (!normalizedMime) {
    return false
  }

  return (
    normalizedMime.startsWith('text/x-') ||
    normalizedMime.startsWith('application/x-') ||
    [
      'application/json',
      'application/javascript',
      'application/xml',
      'text/css',
      'text/html',
      'text/javascript',
      'text/markdown',
      'text/xml'
    ].includes(normalizedMime) ||
    normalizedMime.endsWith('+json') ||
    normalizedMime.endsWith('+xml')
  )
}

const extractContentCore = (entry, index) => {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return {
      title: `Content ${index + 1}`,
      text: String(entry || '').trim(),
      source: '',
      uri: '',
      mimeType: '',
      path: '',
      kind: '',
      description: '',
      sizeBytes: null
    }
  }

  const resource = entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)
    ? entry.resource
    : {}
  const source = String(entry.uri || entry.url || entry.href || entry.resource_link || entry.resourceLink || resource.uri || resource.url || resource.href || resource.resource_link || resource.resourceLink || '').trim()
  const mimeType = String(entry.mimeType || entry.mime_type || resource.mimeType || resource.mime_type || '').trim()
  const path = String(entry.path || entry.file_path || resource.path || resource.file_path || resource.name || pathFromSource(source)).trim()

  let text = ''
  const itemType = String(entry.type || '').trim().toLowerCase()
  if (itemType === 'text' && isNonEmptyString(entry.text)) {
    text = entry.text.trim()
  }
  if (!text) {
    for (const candidate of [entry.text, entry.content, entry.excerpt, resource.text, resource.content, resource.excerpt]) {
      if (isNonEmptyString(candidate)) {
        text = candidate.trim()
        break
      }
    }
  }
  if (!text) {
    text = extractTextCandidate(resource) || extractTextCandidate(entry) || ''
  }

  return {
    title: String(entry.title || entry.name || resource.title || resource.name || path || `Content ${index + 1}`).trim(),
    text: String(text || '').trim(),
    source,
    uri: normalizeInlineUri(source, mimeType, entry.data || entry.blob || resource.data || resource.blob || ''),
    mimeType,
    path,
    kind: guessMediaKind(path, mimeType),
    description: String(entry.description || resource.description || '').trim(),
    sizeBytes: coerceInt(entry.size_bytes ?? entry.sizeBytes ?? entry.bytes ?? resource.size_bytes ?? resource.sizeBytes ?? resource.bytes),
    metadata: normalizeMetadata(
      { ...resource, ...entry },
      ['resource', 'metadata', 'type', 'uri', 'url', 'href', 'mimeType', 'mime_type', 'path', 'file_path', 'name', 'title', 'text', 'content', 'excerpt', 'description', 'data', 'blob', 'size_bytes', 'sizeBytes', 'bytes', 'structured_content', 'structuredContent']
    )
  }
}

const buildToolArtifactName = (toolName, artifactName, fallback) => {
  const toolLabel = String(toolName || '').trim() || 'Tool Result'
  const baseName = String(artifactName || '').trim() || fallback
  if (baseName.toLowerCase().startsWith(toolLabel.toLowerCase())) {
    return baseName
  }
  return `${toolLabel} - ${baseName}`
}

const verificationTitle = (toolName, purpose) => {
  if (toolName === 'run_tests' || purpose === 'test') return 'Test Verification'
  if (toolName === 'run_lint' || purpose === 'lint') return 'Lint Verification'
  if (toolName === 'run_build' || purpose === 'build') return 'Build Verification'
  return 'Sandbox Verification'
}

const verificationKind = (toolName, purpose) => {
  if (toolName === 'run_tests' || purpose === 'test') return 'test'
  if (toolName === 'run_lint' || purpose === 'lint') return 'lint'
  if (toolName === 'run_build' || purpose === 'build') return 'build'
  return 'shell'
}

const verificationSummary = (status, exitCode, failureCategory) => {
  const statusText = String(status || 'unknown').trim() || 'unknown'
  if (statusText === 'completed') return 'Verification completed successfully.'
  if (statusText === 'timeout') return 'Verification timed out before completion.'
  if (statusText === 'failed') {
    const category = String(failureCategory || 'non_zero_exit').trim() || 'non_zero_exit'
    return `Verification failed (${category}).`
  }
  if (exitCode !== null && exitCode !== undefined) return `Verification finished with exit code ${exitCode}.`
  return `Verification status: ${statusText}.`
}

const buildEmbeddedResourceArtifacts = (entry, toolCall = {}) => {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return []
  }

  const toolName = toolCall.toolName || toolCall.tool_name || 'Tool Result'
  const toolKind = toolCall.toolKind || toolCall.tool_kind || ''
  const toolCallId = toolCall.id || toolCall.tool_call_id || ''
  const stepId = toolCall.stepId || toolCall.step_id || ''
  const candidates = [entry]
  if (entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)) {
    candidates.push(entry.resource)
  }

  const promoted = []
  for (const candidate of candidates) {
    const directoryTree = normalizeDirectoryTree(candidate)
    if (directoryTree) {
      promoted.push(normalizeArtifact({
        artifact_type: 'directory_tree',
        step_id: stepId,
        name: buildToolArtifactName(toolName, directoryTree.title, 'Directory Tree'),
        payload: directoryTree,
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      }))
    }

    const documentPages = normalizeDocumentPages(candidate)
    if (documentPages) {
      promoted.push(normalizeArtifact({
        artifact_type: 'document_pages',
        step_id: stepId,
        name: buildToolArtifactName(toolName, documentPages.title, 'Document Pages'),
        payload: documentPages,
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      }))
    }

    const archiveBundle = normalizeArchiveBundle(candidate)
    if (archiveBundle) {
      promoted.push(normalizeArtifact({
        artifact_type: 'archive_bundle',
        step_id: stepId,
        name: buildToolArtifactName(toolName, archiveBundle.title, 'Archive Bundle'),
        payload: archiveBundle,
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      }))
    }
  }

  return mergeArtifacts(promoted)
}

export const buildArtifactsFromToolResult = (result, toolCall = {}, options = {}) => {
  const payload = parseJSON(result, result)
  if (!payload || typeof payload !== 'object') {
    return []
  }

  const toolName = toolCall.toolName || toolCall.tool_name || 'Tool Result'
  const toolKind = toolCall.toolKind || toolCall.tool_kind || ''
  const toolCallId = toolCall.id || toolCall.tool_call_id || ''
  const stepId = toolCall.stepId || toolCall.step_id || ''
  const includeAnswer = options.includeAnswer !== false
  const structuredContent = payload.structured_content ?? payload.structuredContent
  const text = isNonEmptyString(payload.text) ? payload.text.trim() : ''
  const promoted = []

  if (toolName === 'workspace_status' && payload.workspace && typeof payload.workspace === 'object' && !Array.isArray(payload.workspace)) {
    promoted.push(normalizeArtifact({
      artifact_type: 'workspace_summary',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', 'Workspace Binding'),
      payload: payload.workspace,
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (toolName === 'workspace_file_info' && isNonEmptyString(payload.path)) {
    promoted.push(normalizeArtifact({
      artifact_type: 'file_bundle',
      step_id: stepId,
      name: buildToolArtifactName(toolName, payload.path, 'File Info'),
      payload: {
        files: [{
          name: String(payload.path || '').split('/').pop() || String(payload.path || ''),
          path: payload.path,
          size_bytes: payload.size_bytes,
          description: payload.type || '',
          metadata: Object.fromEntries(Object.entries(payload).filter(([key]) => !['path', 'size_bytes', 'type'].includes(key)))
        }]
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (['workspace_apply_patch', 'workspace_create_file', 'workspace_write_file', 'workspace_rename_path', 'workspace_delete_path'].includes(toolName)) {
    const rawArtifacts = Array.isArray(payload.artifacts) ? payload.artifacts : []
    rawArtifacts
      .filter((artifact) => artifact && typeof artifact === 'object')
      .forEach((artifact) => {
        promoted.push(normalizeArtifact({
          ...artifact,
          step_id: stepId || artifact.step_id || artifact.stepId || '',
          name: buildToolArtifactName(toolName, artifact.name, 'Workspace Patch'),
          metadata: {
            ...(artifact.metadata || {}),
            source: 'tool_call',
            tool_name: toolName,
            tool_kind: toolKind,
            tool_call_id: toolCallId,
            promoted_to_run: true,
            path: payload.path,
            operation: payload.operation,
            dry_run: payload.dry_run ?? payload.dryRun,
            changed: payload.changed
          }
        }))
      })
    if (rawArtifacts.length === 0) {
      promoted.push(normalizeArtifact({
        artifact_type: 'code_patch',
        step_id: stepId,
        name: buildToolArtifactName(toolName, '', 'Workspace Patch'),
        payload: {
          operation: payload.operation,
          status: payload.status,
          dry_run: payload.dry_run ?? payload.dryRun,
          files: [{
            path: payload.path,
            operation: payload.operation,
            before_sha256: payload.before_sha256 ?? payload.beforeSha256,
            after_sha256: payload.after_sha256 ?? payload.afterSha256,
            changed: payload.changed
          }],
          diff: payload.diff || '',
          truncated: payload.truncated,
          review_notes: payload.review_notes || payload.reviewNotes || [],
          merge_policy: payload.merge_policy || payload.mergePolicy || 'manual_review_required'
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      }))
    }
  }

  if (['shell_exec', 'run_tests', 'run_lint', 'run_build'].includes(toolName)) {
    const stdout = isNonEmptyString(payload.stdout) ? String(payload.stdout) : ''
    const stderr = isNonEmptyString(payload.stderr) ? String(payload.stderr) : ''
    const purpose = isNonEmptyString(payload.purpose) ? String(payload.purpose).trim() : ''
    const exitCode = payload.exit_code ?? payload.exitCode ?? null
    const failureCategory = payload.failure_category ?? payload.failureCategory ?? null
    promoted.push(normalizeArtifact({
      artifact_type: 'verification_report',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', verificationTitle(toolName, purpose)),
      payload: {
        kind: verificationKind(toolName, purpose),
        status: payload.status || 'unknown',
        exit_code: exitCode,
        command: Array.isArray(payload.command) ? payload.command : [],
        cwd: payload.cwd || '.',
        duration_ms: payload.duration_ms ?? payload.durationMs ?? 0,
        timeout_seconds: payload.timeout_seconds ?? payload.timeoutSeconds ?? null,
        summary: verificationSummary(payload.status, exitCode, failureCategory),
        failure_category: failureCategory,
        truncated: payload.truncated,
        logs: { stdout, stderr },
        runner: payload.runner && typeof payload.runner === 'object' && !Array.isArray(payload.runner) ? payload.runner : {},
        selector: payload.selector,
        target: payload.target
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true,
        status: payload.status,
        exit_code: exitCode,
        failure_category: failureCategory
      }
    }))
  }

  if (structuredContent !== null && structuredContent !== undefined && structuredContent !== '') {
    promoted.push(...buildArtifactsFromStructuredResult(structuredContent, text)
      .filter((artifact) => includeAnswer || artifact.artifactType !== 'answer')
      .map((artifact) => normalizeArtifact({
        ...artifact,
        step_id: stepId || artifact.stepId || artifact.step_id || '',
        name: buildToolArtifactName(toolName, artifact.name, 'Result'),
        metadata: {
          ...artifact.metadata,
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      })))
  }

  const contentItems = []
  const contentCodeFiles = []
  const contentMediaItems = []
  const contentFileBundle = []
  normalizeMCPContentEntries(payload.content).forEach((entry, index) => {
      const core = extractContentCore(entry, index)
      const resource = entry && typeof entry === 'object' && !Array.isArray(entry) && entry.resource && typeof entry.resource === 'object' && !Array.isArray(entry.resource)
        ? entry.resource
        : {}
      for (const structuredCandidate of [
        entry?.structured_content,
        entry?.structuredContent,
        resource?.structured_content,
        resource?.structuredContent
      ]) {
        if (structuredCandidate === null || structuredCandidate === undefined || structuredCandidate === '') {
          continue
        }
        promoted.push(...buildArtifactsFromStructuredResult(structuredCandidate)
          .filter((artifact) => includeAnswer || artifact.artifactType !== 'answer')
          .map((artifact) => normalizeArtifact({
            ...artifact,
            step_id: stepId || artifact.stepId || artifact.step_id || '',
            name: buildToolArtifactName(toolName, artifact.name, 'Result'),
            metadata: {
              ...artifact.metadata,
              source: 'tool_call',
              tool_name: toolName,
              tool_kind: toolKind,
              tool_call_id: toolCallId,
              promoted_to_run: true,
              ...(core.metadata && Object.keys(core.metadata).length > 0 ? { content_metadata: core.metadata } : {})
            }
          })))
      }

      const embeddedArtifacts = buildEmbeddedResourceArtifacts(entry, toolCall)
      if (embeddedArtifacts.length > 0) {
        promoted.push(...embeddedArtifacts)
      }

      const parsedText = parseJSONLike(core.text)
      if (parsedText && typeof parsedText === 'object') {
        const structuredArtifacts = buildArtifactsFromStructuredResult(parsedText)
          .filter((artifact) => includeAnswer || artifact.artifactType !== 'answer')
          .map((artifact) => normalizeArtifact({
            ...artifact,
            step_id: stepId || artifact.stepId || artifact.step_id || '',
            name: buildToolArtifactName(toolName, artifact.name, 'Result'),
            metadata: {
              ...artifact.metadata,
              source: 'tool_call',
              tool_name: toolName,
              tool_kind: toolKind,
              tool_call_id: toolCallId,
              promoted_to_run: true,
              ...(core.metadata && Object.keys(core.metadata).length > 0 ? { content_metadata: core.metadata } : {})
            }
          }))
        if (structuredArtifacts.length > 0) {
          promoted.push(...structuredArtifacts)
          return
        }
      }

      if (embeddedArtifacts.length > 0 && !core.text) {
        return
      }

      if (['image', 'video', 'audio'].includes(core.kind) && core.uri) {
        contentMediaItems.push({
          title: core.title,
          uri: core.uri,
          mime_type: core.mimeType,
          kind: core.kind,
          alt: core.description || core.title,
          path: core.path,
          source: core.source,
          size_bytes: core.sizeBytes,
          metadata: core.metadata
        })
        return
      }

      if (core.text && isCodeLikeContent(core.path, core.mimeType)) {
        contentCodeFiles.push({
          path: core.path || core.title,
          language: guessLanguage(core.path, core.mimeType),
          content: core.text,
          metadata: {
            source: core.source,
            mime_type: core.mimeType,
            ...core.metadata
          }
        })
        return
      }

      if (core.text) {
        contentItems.push({
          title: core.title,
          text: core.text,
          source: core.source || core.mimeType,
          metadata: core.metadata
        })
        return
      }

      if (core.uri || core.path) {
        contentFileBundle.push({
          name: core.title,
          path: core.path,
          uri: core.uri,
          mime_type: core.mimeType,
          size_bytes: core.sizeBytes,
          description: core.description,
          preview_text: '',
          source: core.source,
          metadata: core.metadata
        })
      }
    })

  if (contentCodeFiles.length > 0) {
    promoted.push(normalizeArtifact({
      artifact_type: 'code_files',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', 'Files'),
      payload: {
        files: contentCodeFiles
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (contentMediaItems.length > 0) {
    promoted.push(normalizeArtifact({
      artifact_type: 'media_gallery',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', 'Media'),
      payload: {
        items: contentMediaItems
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (contentFileBundle.length > 0) {
    promoted.push(normalizeArtifact({
      artifact_type: 'file_bundle',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', 'Files'),
      payload: {
        files: contentFileBundle
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (contentItems.length > 0) {
    promoted.push(normalizeArtifact({
      artifact_type: 'document_excerpt',
      step_id: stepId,
      name: buildToolArtifactName(toolName, '', 'Preview'),
      payload: {
        items: contentItems
      },
      metadata: {
        source: 'tool_call',
        tool_name: toolName,
        tool_kind: toolKind,
        tool_call_id: toolCallId,
        promoted_to_run: true
      }
    }))
  }

  if (promoted.length > 0) {
    return mergeArtifacts(promoted)
  }

  if (toolName === 'web_search' && Array.isArray(payload.items)) {
    return mergeArtifacts([
      normalizeArtifact({
        artifact_type: 'citations',
        step_id: stepId,
        name: buildToolArtifactName(toolName, '', 'Search Results'),
        payload: {
          items: payload.items
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
              title: item.title || item.url || 'Search Result',
              url: item.url || '',
              snippet: item.snippet || '',
              source: payload.source || 'web_search',
              metadata: {
                query: payload.query,
                fetched_at: payload.fetched_at
              }
            }))
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true,
          query: payload.query,
          truncated: payload.truncated
        }
      })
    ])
  }

  if (['open_page', 'extract_page_text', 'fetch_url'].includes(toolName) && (isNonEmptyString(payload.text) || isNonEmptyString(payload.error))) {
    return mergeArtifacts([
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        step_id: stepId,
        name: buildToolArtifactName(toolName, payload.title, 'Web Page'),
        payload: {
          items: [{
            title: payload.title || payload.url || toolName,
            text: payload.text || payload.error || '',
            source: payload.url || payload.requested_url || 'web',
            metadata: {
              requested_url: payload.requested_url,
              status: payload.status,
              fetched_at: payload.fetched_at,
              truncated: payload.truncated,
              failure_category: payload.failure_category
            }
          }]
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true,
          url: payload.url,
          status: payload.status,
          truncated: payload.truncated
        }
      })
    ])
  }

  if (['git_status', 'git_diff', 'git_show', 'git_log', 'git_branch'].includes(toolName)) {
    let gitText = isNonEmptyString(payload.stdout) ? String(payload.stdout).trim() : ''
    if (!gitText && Number(payload.exit_code) === 0 && ['git_status', 'git_diff'].includes(toolName)) {
      gitText = 'No changes.'
    }
    if (!gitText && isNonEmptyString(payload.stderr)) {
      gitText = String(payload.stderr).trim()
    }
    if (!gitText) {
      gitText = `${toolName} completed with exit code ${payload.exit_code ?? ''}.`.trim()
    }
    return mergeArtifacts([
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        step_id: stepId,
        name: buildToolArtifactName(toolName, '', 'Git Output'),
        payload: {
          items: [{
            title: Array.isArray(payload.command) ? payload.command.join(' ') : toolName,
            text: gitText,
            source: 'git',
            metadata: {
              exit_code: payload.exit_code,
              stderr: payload.stderr,
              truncated: payload.truncated
            }
          }]
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      })
    ])
  }

  const fallbackContentItems = normalizeMCPContentItems(payload.content)
  if (fallbackContentItems.length > 0) {
    return mergeArtifacts([
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        step_id: stepId,
        name: buildToolArtifactName(toolName, '', 'Preview'),
        payload: {
          items: fallbackContentItems.map((item) => ({
            title: item.title,
            text: item.text,
            source: item.source,
            metadata: item.metadata || {}
          }))
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      })
    ])
  }

  if (text) {
    return mergeArtifacts([
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        step_id: stepId,
        name: buildToolArtifactName(toolName, '', 'Preview'),
        payload: {
          items: [
            {
              title: toolName,
              text,
              source: ''
            }
          ]
        },
        metadata: {
          source: 'tool_call',
          tool_name: toolName,
          tool_kind: toolKind,
          tool_call_id: toolCallId,
          promoted_to_run: true
        }
      })
    ])
  }

  return []
}

export const buildRunArtifactsFromToolCalls = (toolCalls = [], existingArtifacts = []) => {
  const promoted = Array.isArray(toolCalls)
    ? toolCalls
      .filter((toolCall) => (toolCall?.status || '') === 'completed')
      .flatMap((toolCall) => buildArtifactsFromToolResult(toolCall?.result || {}, toolCall, { includeAnswer: false }))
    : []
  return mergeArtifacts(existingArtifacts, promoted)
}

export const normalizeRunResult = (raw = {}) => {
  const finalOutputJson = parseJSON(raw.final_output_json || raw.finalOutputJson, null)
  const finalOutputText = isNonEmptyString(raw.final_output_text || raw.finalOutputText)
    ? String(raw.final_output_text || raw.finalOutputText).trim()
    : ''
  const legacyFinalOutput = isNonEmptyString(raw.final_output || raw.finalOutput)
    ? String(raw.final_output || raw.finalOutput).trim()
    : ''
  const answerText = finalOutputText || legacyFinalOutput || extractTextCandidate(finalOutputJson)
  const explicitArtifacts = Array.isArray(raw.artifacts) ? raw.artifacts.map(normalizeArtifact) : []
  const derivedArtifacts = buildArtifactsFromStructuredResult(finalOutputJson, answerText)

  return {
    finalOutput: legacyFinalOutput || answerText,
    finalOutputText: answerText,
    finalOutputJson,
    artifacts: mergeArtifacts(explicitArtifacts, derivedArtifacts)
  }
}

export const getRunAnswerText = (run = {}) => {
  if (isNonEmptyString(run.finalOutputText)) {
    return run.finalOutputText.trim()
  }
  if (isNonEmptyString(run.finalOutput)) {
    return run.finalOutput.trim()
  }
  if (Array.isArray(run.artifacts)) {
    const answerArtifact = run.artifacts.find((artifact) => artifact.artifactType === 'answer')
    const text = answerArtifact?.payload?.text
    if (isNonEmptyString(text)) {
      return text.trim()
    }
  }
  return extractTextCandidate(run.finalOutputJson)
}

export const artifactTypeLabel = (type) => {
  const labels = {
    answer: '回答',
    archive_bundle: '压缩包清单',
    code_patch: '代码补丁',
    code_files: '代码文件',
    citations: '引用',
    directory_tree: '目录树',
    document_pages: '多页文档',
    file_bundle: '附件文件',
    media_gallery: '媒体资源',
    paged_collection: '分页结果',
    review_findings: '审查发现',
    task_plan: '任务计划',
    table: '表格',
    verification_report: '验证报告',
    document_excerpt: '文档摘录'
  }
  return labels[type] || type || '结构化结果'
}

export const summarizeArtifacts = (artifacts = []) => {
  return artifacts.map((artifact) => artifactTypeLabel(artifact.artifactType)).join(' · ')
}
