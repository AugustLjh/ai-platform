<template>
  <div class="code-block rich-code-block">
    <div class="code-header">
      <span class="code-lang">{{ block.languageLabel }}</span>
      <button class="code-copy-btn" type="button" title="复制代码">
        <span class="code-copy-icon">⧉</span>
        <span>复制</span>
      </button>
    </div>
    <pre><code class="hljs" :class="`language-${block.language}`" v-html="block.highlightedCode"></code></pre>
  </div>
</template>

<script setup>
defineProps({
  block: {
    type: Object,
    required: true
  }
})
</script>
