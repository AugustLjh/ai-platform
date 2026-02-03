import { defineStore } from 'pinia'
import { authAPI } from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => {
    const userInfo = localStorage.getItem('user_info')
    return {
      user: userInfo ? JSON.parse(userInfo) : null,
      accessToken: localStorage.getItem('access_token'),
      refreshToken: localStorage.getItem('refresh_token'),
      isAuthenticated: !!localStorage.getItem('access_token')
    }
  },

  actions: {
    async login(email, password) {
      try {
        const { data } = await authAPI.login(email, password)
        this.setAuth(data)
        return data
      } catch (error) {
        throw error
      }
    },

    async register(email, password) {
      try {
        const { data } = await authAPI.register(email, password)
        return data
      } catch (error) {
        throw error
      }
    },

    async logout() {
      try {
        await authAPI.logout()
      } catch (error) {
        console.error('Logout error:', error)
      } finally {
        this.clearAuth()
      }
    },

    async getCurrentUser() {
      try {
        const { data } = await authAPI.getCurrentUser()
        this.user = data
        return data
      } catch (error) {
        this.clearAuth()
        throw error
      }
    },

    setAuth(data) {
      this.user = data.user
      this.accessToken = data.access_token
      this.refreshToken = data.refresh_token
      this.isAuthenticated = true

      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('user_info', JSON.stringify(data.user))
      // Initialize last activity time on login
      localStorage.setItem('last_activity_time', Date.now().toString())
    },

    clearAuth() {
      this.user = null
      this.accessToken = null
      this.refreshToken = null
      this.isAuthenticated = false

      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      localStorage.removeItem('last_activity_time')
    }
  }
})
