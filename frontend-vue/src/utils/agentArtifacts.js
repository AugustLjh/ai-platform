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
    const strings = value.filter(isNonEmptyString).map((item) => item.trim())
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

  return ''
}

export const normalizeArtifact = (raw = {}) => ({
  id: raw.id || '',
  runId: raw.run_id || raw.runId || '',
  stepId: raw.step_id || raw.stepId || '',
  artifactType: raw.artifact_type || raw.artifactType || 'answer',
  name: raw.name || 'Untitled Artifact',
  mimeType: raw.mime_type || raw.mimeType || '',
  uri: raw.uri || '',
  payload: parseJSON(raw.payload, {}),
  metadata: parseJSON(raw.metadata, {}),
  createdAt: raw.created_at || raw.createdAt || null,
  updatedAt: raw.updated_at || raw.updatedAt || null
})

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
        metadata: Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'summary', 'message', 'severity', 'level', 'description', 'details', 'path', 'file', 'line', 'code'].includes(key)))
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
        metadata: Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'name', 'source', 'url', 'link', 'snippet', 'quote', 'excerpt'].includes(key)))
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
        metadata: Object.fromEntries(Object.entries(item).filter(([key]) => !['path', 'file_path', 'name', 'language', 'content', 'patch'].includes(key)))
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
        text: item.text || item.content || item.excerpt || '',
        source: item.source || '',
        metadata: Object.fromEntries(Object.entries(item).filter(([key]) => !['title', 'heading', 'text', 'content', 'excerpt', 'source'].includes(key)))
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

export const buildArtifactsFromStructuredResult = (value, fallbackText = '') => {
  const artifacts = []
  const answerText = extractTextCandidate(value) || extractTextCandidate(fallbackText)
  const structured = value && typeof value === 'object' ? value : null

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
  }

  if (Array.isArray(value)) {
    const table = normalizeTable(value)
    if (table) {
      artifacts.push(normalizeArtifact({
        artifact_type: 'table',
        name: 'Result Table',
        payload: table
      }))
    }
  }

  return artifacts
}

const normalizeMCPContentItems = (items = []) => {
  if (!Array.isArray(items)) return []
  return items
    .map((item, index) => {
      if (!item || typeof item !== 'object') {
        return {
          kind: 'text',
          title: `Content ${index + 1}`,
          text: String(item || '').trim(),
          source: ''
        }
      }

      const itemType = String(item.type || '').trim().toLowerCase()
      if (itemType === 'text') {
        return {
          kind: 'text',
          title: item.title || '',
          text: String(item.text || '').trim(),
          source: item.uri || item.url || ''
        }
      }

      const payloadText = extractTextCandidate(item) || (typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item || ''))
      return {
        kind: itemType || 'json',
        title: item.title || item.name || `Content ${index + 1}`,
        text: payloadText.trim(),
        source: item.uri || item.url || item.mimeType || item.mime_type || ''
      }
    })
    .filter((item) => item.text)
}

export const buildArtifactsFromToolResult = (result, toolCall = {}) => {
  const payload = parseJSON(result, result)
  if (!payload || typeof payload !== 'object') {
    return []
  }

  const toolName = toolCall.toolName || toolCall.tool_name || 'Tool Result'
  const structuredContent = payload.structured_content ?? payload.structuredContent
  const text = isNonEmptyString(payload.text) ? payload.text.trim() : ''
  const contentItems = normalizeMCPContentItems(payload.content)

  if (structuredContent !== null && structuredContent !== undefined && structuredContent !== '') {
    const artifacts = buildArtifactsFromStructuredResult(structuredContent, text)
    if (artifacts.length > 0) {
      return artifacts.map((artifact) => ({
        ...artifact,
        name: artifact.name || `${toolName} Result`
      }))
    }
  }

  if (contentItems.length > 0) {
    return [
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        name: `${toolName} Preview`,
        payload: {
          items: contentItems.map((item) => ({
            title: item.title,
            text: item.text,
            source: item.source
          }))
        },
        metadata: {
          tool_kind: toolCall.toolKind || toolCall.tool_kind || '',
          source: 'tool_call'
        }
      })
    ]
  }

  if (text) {
    return [
      normalizeArtifact({
        artifact_type: 'document_excerpt',
        name: `${toolName} Preview`,
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
          tool_kind: toolCall.toolKind || toolCall.tool_kind || '',
          source: 'tool_call'
        }
      })
    ]
  }

  return []
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
  const derivedArtifacts = explicitArtifacts.length > 0 ? explicitArtifacts : buildArtifactsFromStructuredResult(finalOutputJson, answerText)

  return {
    finalOutput: legacyFinalOutput || answerText,
    finalOutputText: answerText,
    finalOutputJson,
    artifacts: derivedArtifacts
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
    code_files: '代码文件',
    citations: '引用',
    review_findings: '审查发现',
    task_plan: '任务计划',
    table: '表格',
    document_excerpt: '文档摘录'
  }
  return labels[type] || type || '结构化结果'
}

export const summarizeArtifacts = (artifacts = []) => {
  return artifacts.map((artifact) => artifactTypeLabel(artifact.artifactType)).join(' · ')
}
