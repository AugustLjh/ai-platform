<template>
  <div class="markdown-blocks">
    <div
      v-for="block in blocks"
      :key="`${blockKeyPrefix}${block.id}`"
      class="markdown-block"
      :class="`markdown-block-${block.type}`"
    >
      <MessageCodeBlock v-if="block.type === 'code'" :block="block" />
      <div v-else class="markdown-block-html" v-html="block.html"></div>
    </div>
  </div>
</template>

<script setup>
import MessageCodeBlock from '@/components/MessageCodeBlock.vue'

defineProps({
  blocks: {
    type: Array,
    default: () => []
  },
  blockKeyPrefix: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.markdown-blocks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.markdown-block {
  min-width: 0;
}
</style>
