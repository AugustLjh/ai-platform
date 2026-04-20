<template>
  <div class="app-shell">
    <button
      v-if="isMobile"
      type="button"
      class="sidebar-toggle"
      :aria-expanded="isSidebarOpen ? 'true' : 'false'"
      aria-label="切换侧边栏"
      @click="toggleSidebar"
    >
      <span v-if="isSidebarOpen">×</span>
      <span v-else>☰</span>
    </button>

    <button
      v-if="isMobile && isSidebarOpen"
      type="button"
      class="sidebar-backdrop"
      aria-label="关闭侧边栏"
      @click="closeSidebar"
    ></button>

    <div
      :class="[
        'app-shell-sidebar',
        {
          'is-mobile': isMobile,
          'is-open': isSidebarOpen
        }
      ]"
    >
      <AppSidebar />
    </div>
    <div class="app-shell-main">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'

const route = useRoute()
const isMobile = ref(false)
const isSidebarOpen = ref(false)

let mediaQuery = null

const syncViewportState = (matches) => {
  isMobile.value = matches
  isSidebarOpen.value = matches ? false : true
}

const handleViewportChange = (event) => {
  syncViewportState(event.matches)
}

const toggleSidebar = () => {
  if (!isMobile.value) return
  isSidebarOpen.value = !isSidebarOpen.value
}

const closeSidebar = () => {
  if (!isMobile.value) return
  isSidebarOpen.value = false
}

watch(
  () => route.fullPath,
  () => {
    closeSidebar()
  }
)

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 1024px)')
  syncViewportState(mediaQuery.matches)

  if (mediaQuery.addEventListener) {
    mediaQuery.addEventListener('change', handleViewportChange)
    return
  }

  mediaQuery.addListener(handleViewportChange)
})

onBeforeUnmount(() => {
  if (!mediaQuery) return

  if (mediaQuery.removeEventListener) {
    mediaQuery.removeEventListener('change', handleViewportChange)
    return
  }

  mediaQuery.removeListener(handleViewportChange)
})
</script>

<style scoped>
.app-shell {
  display: flex;
  width: 100%;
  height: 100svh;
  min-height: 100vh;
  overflow: hidden;
  background: var(--gpt-bg);
  position: relative;
}

.app-shell-sidebar {
  width: var(--sidebar-width);
  flex: 0 0 var(--sidebar-width);
  min-width: 0;
  min-height: 0;
  display: flex;
  z-index: 30;
}

.app-shell-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
  background: var(--gpt-bg);
}

.sidebar-toggle {
  position: fixed;
  top: max(12px, env(safe-area-inset-top, 0px) + 8px);
  left: max(12px, env(safe-area-inset-left, 0px) + 8px);
  z-index: 60;
  width: 42px;
  height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.88);
  color: #f8fafc;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  line-height: 1;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.22);
  backdrop-filter: blur(10px);
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  border: none;
  background: rgba(15, 23, 42, 0.42);
}

@media (max-width: 1024px) {
  .app-shell-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: min(82vw, 320px);
    transform: translateX(-100%);
    transition: transform 0.22s ease;
    z-index: 50;
  }

  .app-shell-sidebar.is-open {
    transform: translateX(0);
  }

  .app-shell-main {
    width: 100%;
  }
}
</style>
