import { defineStore } from 'pinia'

let toastCounter = 0

export const useToastStore = defineStore('toast', {
  state: () => ({
    toasts: []
  }),

  actions: {
    showToast(payload) {
      const message = payload?.message || ''
      if (!message) return null
      const id = ++toastCounter
      const toast = {
        id,
        message,
        type: payload?.type || 'info',
        duration: payload?.duration ?? 3000
      }
      this.toasts.push(toast)

      if (toast.duration > 0) {
        setTimeout(() => {
          this.removeToast(id)
        }, toast.duration)
      }

      return id
    },

    removeToast(id) {
      this.toasts = this.toasts.filter((toast) => toast.id !== id)
    }
  }
})
