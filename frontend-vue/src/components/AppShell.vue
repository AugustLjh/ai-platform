<template>
  <div class="app-shell">
    <AppSidebar />
    <div class="app-shell-main">
      <slot />
    </div>
  </div>
</template>

<script setup>
import AppSidebar from '@/components/AppSidebar.vue'
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

.app-shell-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
  background: var(--gpt-bg);
}
</style>
