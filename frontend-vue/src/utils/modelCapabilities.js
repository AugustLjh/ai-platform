export const ENDPOINT_PROTOCOL_OPTIONS = [
  { value: 'openai.chat_completions', label: 'OpenAI Chat Completions' },
  { value: 'openai.responses', label: 'OpenAI Responses' },
  { value: 'jina.responses', label: 'Jina Responses' },
  { value: 'deepseek.chat_completions', label: 'DeepSeek Chat Completions' },
  { value: 'dashscope.openai_compatible', label: 'DashScope OpenAI Compatible' },
  { value: 'dashscope.responses', label: 'DashScope Responses' },
  { value: 'bigmodel.chat_completions', label: 'BigModel Chat Completions' },
  { value: 'bigmodel.responses', label: 'BigModel Responses' },
  { value: 'moonshot.chat_completions', label: 'Moonshot Chat Completions' },
  { value: 'moonshot.responses', label: 'Moonshot Responses' },
  { value: 'volcengine.ark_chat_completions', label: 'Volcengine Ark Chat Completions' },
  { value: 'volcengine.ark_responses', label: 'Volcengine Ark Responses' },
  { value: 'baidu.qianfan_chat_completions', label: 'Baidu Qianfan Chat Completions' },
  { value: 'baidu.qianfan_responses', label: 'Baidu Qianfan Responses' },
  { value: 'local.chat_completions', label: 'Local Chat Completions' }
]

export const MODEL_INPUT_MODALITY_OPTIONS = [
  { value: 'text', label: 'Text' },
  { value: 'image', label: 'Image' },
  { value: 'audio', label: 'Audio' },
  { value: 'video', label: 'Video' },
  { value: 'file', label: 'File' }
]

export const ENDPOINT_PROTOCOL_INPUT_MODALITIES = {
  'openai.chat_completions': ['text', 'image'],
  'openai.responses': ['text', 'image', 'audio', 'video', 'file'],
  'jina.responses': ['text', 'image', 'audio', 'video', 'file'],
  'deepseek.chat_completions': ['text'],
  'dashscope.openai_compatible': ['text', 'image'],
  'dashscope.responses': ['text', 'image', 'audio', 'video', 'file'],
  'bigmodel.chat_completions': ['text', 'image'],
  'bigmodel.responses': ['text', 'image', 'file'],
  'moonshot.chat_completions': ['text', 'image'],
  'moonshot.responses': ['text', 'image', 'file'],
  'volcengine.ark_chat_completions': ['text', 'image'],
  'volcengine.ark_responses': ['text', 'image', 'file'],
  'baidu.qianfan_chat_completions': ['text', 'image'],
  'baidu.qianfan_responses': ['text', 'image', 'audio', 'video', 'file'],
  'local.chat_completions': ['text']
}

const IMAGE_ACCEPT_PATTERNS = [
  'image/*',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.gif',
  '.bmp',
  '.avif',
  '.heic'
]

const AUDIO_ACCEPT_PATTERNS = [
  'audio/*',
  '.mp3',
  '.wav',
  '.m4a',
  '.aac',
  '.flac',
  '.ogg',
  '.opus'
]

const VIDEO_ACCEPT_PATTERNS = [
  'video/*',
  '.mp4',
  '.mov',
  '.mkv',
  '.webm',
  '.avi',
  '.m4v'
]

const DOCUMENT_ACCEPT_PATTERNS = [
  '.txt',
  '.text',
  '.log',
  '.md',
  '.markdown',
  '.pdf',
  '.html',
  '.htm',
  '.csv',
  '.tsv',
  '.doc',
  '.docx',
  '.rtf',
  '.ppt',
  '.pptx',
  '.xls',
  '.xlsx',
  '.json',
  '.jsonl',
  '.yaml',
  '.yml',
  '.xml'
]

export const DEFAULT_ENDPOINT_PROTOCOL_BY_PROVIDER = {
  openai: 'openai.chat_completions',
  deepseek: 'deepseek.chat_completions',
  qwen: 'dashscope.openai_compatible',
  wenxin: 'baidu.qianfan_chat_completions',
  glm: 'bigmodel.chat_completions',
  kimi: 'moonshot.chat_completions',
  doubao: 'volcengine.ark_chat_completions',
  local: 'local.chat_completions',
  mock: 'local.chat_completions'
}

const normalizeList = (value, fallback = ['text']) => {
  if (value == null) {
    return [...fallback]
  }

  const items = Array.isArray(value) ? value : String(value).split(',')
  const normalized = []
  const seen = new Set()

  for (const item of items) {
    const token = String(item || '').trim().toLowerCase()
    if (!token || seen.has(token)) {
      continue
    }
    seen.add(token)
    normalized.push(token)
  }

  return normalized.length > 0 ? normalized : [...fallback]
}

const unique = (values) => [...new Set(values.filter(Boolean))]

const getModelConfig = (model) => (model && typeof model === 'object' ? (model.config || model) : {})

export const normalizeEndpointProtocol = (value, fallback = 'openai.chat_completions') => {
  const protocol = String(value || fallback || '').trim().toLowerCase()
  return protocol || fallback
}

export const defaultEndpointProtocolForProvider = (provider) => (
  DEFAULT_ENDPOINT_PROTOCOL_BY_PROVIDER[provider] || 'openai.chat_completions'
)

export const getModelEndpointProtocol = (model) => {
  const config = getModelConfig(model)
  return normalizeEndpointProtocol(
    config.endpoint_protocol || model?.endpoint_protocol || defaultEndpointProtocolForProvider(model?.provider)
  )
}

export const getModelInputModalities = (model) => {
  const config = getModelConfig(model)
  const capabilities = config.capabilities || {}
  const modalities = normalizeList(
    capabilities.input_modalities ?? config.input_modalities ?? model?.input_modalities,
    ['text']
  )

  const flagSources = [capabilities, config, model]
  const hasFlag = (key) => flagSources.some((source) => Boolean(source && source[key]))

  if (hasFlag('supports_vision') && !modalities.includes('image')) {
    modalities.push('image')
  }
  if (hasFlag('supports_audio_input') && !modalities.includes('audio')) {
    modalities.push('audio')
  }
  if (hasFlag('supports_video_input') && !modalities.includes('video')) {
    modalities.push('video')
  }
  if (hasFlag('supports_file_input') && !modalities.includes('file')) {
    modalities.push('file')
  }

  return modalities
}

export const getEndpointSupportedInputModalities = (protocol) => {
  const normalized = normalizeEndpointProtocol(protocol, '')
  return normalized ? ENDPOINT_PROTOCOL_INPUT_MODALITIES[normalized] || null : null
}

export const getSupportedInputModalities = (model) => {
  const declaredModalities = getModelInputModalities(model)
  const protocolModalities = getEndpointSupportedInputModalities(getModelEndpointProtocol(model))
  if (!protocolModalities) {
    return declaredModalities
  }

  const allowed = declaredModalities.filter((modality) => protocolModalities.includes(modality))
  return allowed.length > 0 ? allowed : ['text']
}

export const getAttachmentModalities = (model) => (
  getSupportedInputModalities(model).filter((modality) => modality !== 'text')
)

export const canModelAcceptAttachments = (model) => getAttachmentModalities(model).length > 0

export const buildAttachmentAccept = (modalities) => {
  const patterns = []
  const enabled = new Set(modalities || [])

  if (enabled.has('image')) {
    patterns.push(...IMAGE_ACCEPT_PATTERNS)
  }
  if (enabled.has('audio')) {
    patterns.push(...AUDIO_ACCEPT_PATTERNS)
  }
  if (enabled.has('video')) {
    patterns.push(...VIDEO_ACCEPT_PATTERNS)
  }
  if (enabled.has('file')) {
    patterns.push(...DOCUMENT_ACCEPT_PATTERNS)
  }

  return unique(patterns).join(',')
}

export const getAttachmentSupportSummary = (model) => {
  const modalities = getAttachmentModalities(model)
  if (modalities.length === 0) {
    return '当前模型仅支持文本输入'
  }

  const labels = modalities
    .map((modality) => MODEL_INPUT_MODALITY_OPTIONS.find((item) => item.value === modality)?.label || modality)
    .join('、')

  return `当前模型支持 ${labels} 附件`
}
