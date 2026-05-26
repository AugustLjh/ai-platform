export const REDACTION_MASK = '********'

const sensitiveTokens = [
  'secret',
  'password',
  'passwd',
  'token',
  'api_key',
  'apikey',
  'access_key',
  'authorization',
  'cookie',
  'client_secret',
  'credential',
  'refresh_token',
  'private_key',
  'ssh_key',
  'jwt',
  'bearer'
]

const sensitiveContainers = new Set(['env', 'headers', 'credentials', 'auth'])

const sensitiveTextPatterns = [
  /(\bauthorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/=-]{8,})/gi,
  /(\bbearer\s+)([A-Za-z0-9._~+/=-]{16,})/gi,
  /(\b(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|client[_-]?secret)\s*[:=]\s*)("[^"]+"|'[^']+'|[^\s,;]+)/gi,
  /\b(sk-[A-Za-z0-9]{10,})\b/g,
  /\b(AKIA[0-9A-Z]{12,})\b/g
]

const isSensitiveKey = (key = '') => {
  const normalized = String(key || '').trim().toLowerCase()
  return sensitiveTokens.some((token) => normalized.includes(token))
}

export const redactRuntimeText = (value = '') => {
  let redacted = String(value || '')
  for (const pattern of sensitiveTextPatterns) {
    redacted = redacted.replace(pattern, (...args) => {
      const match = args[0]
      const group1 = args[1]
      const group2 = args[2]
      if (group1 && group2 && match.includes(group2)) {
        return `${group1}${REDACTION_MASK}`
      }
      return REDACTION_MASK
    })
  }
  return redacted
}

export const redactRuntimePayload = (value, path = []) => {
  if (Array.isArray(value)) {
    const current = String(path[path.length - 1] || '').toLowerCase()
    if (sensitiveContainers.has(current)) {
      return value.map(() => REDACTION_MASK)
    }
    return value.map((item) => redactRuntimePayload(item, path))
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        redactRuntimePayload(item, [...path, key])
      ])
    )
  }

  if (typeof value !== 'string') {
    return value
  }

  const current = String(path[path.length - 1] || '').toLowerCase()
  const parent = String(path[path.length - 2] || '').toLowerCase()
  if (isSensitiveKey(current) || sensitiveContainers.has(current) || sensitiveContainers.has(parent)) {
    return value ? REDACTION_MASK : value
  }
  return redactRuntimeText(value)
}

export const summarizeRedactedObject = (value = {}) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  const keys = Object.keys(value)
  if (keys.length === 0) return ''
  const preview = keys.slice(0, 6).join(', ')
  const suffix = keys.length > 6 ? ` +${keys.length - 6}` : ''
  return `${preview}${suffix}`
}
