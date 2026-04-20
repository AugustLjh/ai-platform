import axios from 'axios'
import { buildApiUrl, getApiBaseUrl } from './base'

const api = axios.create({
  baseURL: getApiBaseUrl() || '/',
  timeout: 30000
})

// Request interceptor
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// Response interceptor
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // Try to refresh token
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post(
            buildApiUrl('/api/v1/auth/refresh'),
            { refresh_token: refreshToken }
          )
          localStorage.setItem('access_token', data.access_token)
          if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token)
          }
          // Retry original request
          error.config.headers.Authorization = `Bearer ${data.access_token}`
          return api.request(error.config)
        } catch (refreshError) {
          // Refresh failed, logout
          localStorage.clear()
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

export default api
