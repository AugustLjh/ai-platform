const ABSOLUTE_URL_PATTERN = /^https?:\/\//i

export const getApiBaseUrl = () => {
  const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim()
  if (!rawBaseUrl || rawBaseUrl === '/') {
    return ''
  }
  return rawBaseUrl.replace(/\/+$/, '')
}

export const buildApiUrl = (path) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const baseUrl = getApiBaseUrl()

  if (!baseUrl) {
    return normalizedPath
  }
  if (ABSOLUTE_URL_PATTERN.test(baseUrl)) {
    return `${baseUrl}${normalizedPath}`
  }
  if (baseUrl.startsWith('/')) {
    return `${baseUrl}${normalizedPath}`
  }

  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
  return `${origin}/${baseUrl.replace(/^\/+/, '')}${normalizedPath}`
}
