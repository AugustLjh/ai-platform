<template>
  <div class="toast-stack" aria-live="polite">
    <transition-group name="toast" tag="div" class="toast-list">
      <div v-for="toast in toasts" :key="toast.id" :class="['toast', toast.type]">
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-close" type="button" @click="removeToast(toast.id)">×</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useToastStore } from '@/store/toast'

const toastStore = useToastStore()
const toasts = computed(() => toastStore.toasts)

const removeToast = (id) => {
  toastStore.removeToast(id)
}
</script>

<style scoped>
.toast-stack {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 9999;
  pointer-events: none;
}

.toast-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toast {
  min-width: 220px;
  max-width: 320px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #111827;
  color: #f9fafb;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  pointer-events: auto;
}

.toast.success {
  background: #16a34a;
}

.toast.error {
  background: #dc2626;
}

.toast.warning {
  background: #d97706;
}

.toast-message {
  flex: 1;
}

.toast-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
