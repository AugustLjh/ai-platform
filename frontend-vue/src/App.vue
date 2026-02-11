<template>
  <div id="app">
    <AppShell v-if="showShell">
      <router-view />
    </AppShell>
    <router-view v-else />
    <ToastStack />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useActivityTracker } from '@/composables/useActivityTracker'
import AppShell from '@/components/AppShell.vue'
import ToastStack from '@/components/ToastStack.vue'

const route = useRoute()
const showShell = computed(() => route.meta?.requiresAuth)

// Initialize activity tracker
useActivityTracker()
</script>

<style>
#app {
  width: 100%;
  min-height: 100vh;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
}
</style>
