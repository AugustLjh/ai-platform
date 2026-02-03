<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
import { useActivityTracker } from '@/composables/useActivityTracker'

// Initialize activity tracker
useActivityTracker()
</script>

<style>
#app {
  width: 100%;
  height: 100vh;
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