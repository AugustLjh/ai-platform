export const normalizeIndexingSettings = (settings = {}) => ({
  indexing_method: settings.indexing_method || 'structured',
  chunk_size: settings.chunk_size ?? 500,
  chunk_overlap: settings.chunk_overlap ?? 50,
  embedding_model_id: settings.embedding_model_id || '',
  tokenizer_mode: settings.tokenizer_mode || 'cjk',
  custom_terms: Array.isArray(settings.custom_terms) ? settings.custom_terms : [],
  synonym_map: settings.synonym_map && typeof settings.synonym_map === 'object' ? settings.synonym_map : {}
})

export const normalizeRetrievalSettings = (settings = {}) => ({
  retrieval_method: settings.retrieval_method || 'hybrid',
  top_k: settings.top_k ?? 5,
  score_threshold: settings.score_threshold ?? 0,
  vector_top_k: settings.vector_top_k ?? 40,
  keyword_top_k: settings.keyword_top_k ?? 40,
  fusion_algorithm: settings.fusion_algorithm || 'rrf',
  rrf_k: settings.rrf_k ?? 60,
  vector_weight: settings.vector_weight ?? 0.65,
  keyword_weight: settings.keyword_weight ?? 0.35,
  max_candidates: settings.max_candidates ?? 100,
  enable_rerank: settings.enable_rerank ?? false,
  rerank_model_id: settings.rerank_model_id || '',
  query_rewrite: settings.query_rewrite ?? true
})

export const stringifyCustomTerms = (terms = []) => (
  Array.isArray(terms) ? terms.join('\n') : ''
)

export const parseCustomTerms = (raw = '') => (
  String(raw)
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
)

export const stringifySynonymMap = (synonymMap = {}) => (
  Object.entries(synonymMap || {})
    .filter(([key, values]) => key && Array.isArray(values) && values.length > 0)
    .map(([key, values]) => `${key}=${values.join(', ')}`)
    .join('\n')
)

export const parseSynonymMap = (raw = '') => {
  const synonymMap = {}

  for (const line of String(raw).split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue

    const separatorIndex = trimmed.includes('=') ? trimmed.indexOf('=') : trimmed.indexOf('：')
    if (separatorIndex === -1) continue

    const key = trimmed.slice(0, separatorIndex).trim()
    const valueText = trimmed.slice(separatorIndex + 1).trim()
    if (!key || !valueText) continue

    const values = valueText
      .split(/[，,]/)
      .map((item) => item.trim())
      .filter(Boolean)

    if (values.length > 0) {
      synonymMap[key] = values
    }
  }

  return synonymMap
}
