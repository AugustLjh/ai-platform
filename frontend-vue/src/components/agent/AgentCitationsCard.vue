<template>
  <article class="artifact-card">
    <div class="artifact-head">
      <div>
        <div class="artifact-kicker">引用</div>
        <h4>{{ artifact.name || 'Citations' }}</h4>
      </div>
      <span class="artifact-count">{{ items.length }}</span>
    </div>

    <div v-if="items.length === 0" class="artifact-empty">
      当前没有可展示的引用。
    </div>

    <ol v-else class="citation-list">
      <li v-for="(item, index) in items" :key="`${item.title}-${index}`" class="citation-item">
        <div class="citation-title-row">
          <strong>{{ item.title || `Source ${index + 1}` }}</strong>
          <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">打开来源</a>
        </div>
        <p v-if="item.snippet" class="citation-snippet">{{ item.snippet }}</p>
      </li>
    </ol>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  artifact: {
    type: Object,
    required: true
  }
})

const items = computed(() => Array.isArray(props.artifact?.payload?.items) ? props.artifact.payload.items : [])
</script>

<style scoped>
.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
  max-height: min(52vh, 520px);
  overflow: auto;
}

.artifact-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.artifact-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: #1d4ed8;
}

.artifact-head h4 {
  margin-top: 6px;
  font-size: 17px;
}

.artifact-count {
  min-width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
  font-weight: 700;
}

.artifact-empty {
  margin-top: 12px;
  color: var(--gray-500);
  font-size: 14px;
}

.citation-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  padding-left: 18px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
}

.citation-item {
  padding-left: 4px;
}

.citation-title-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.citation-title-row a {
  color: #1d4ed8;
  text-decoration: none;
  font-size: 13px;
  font-weight: 700;
}

.citation-snippet {
  margin-top: 6px;
  color: var(--gray-700);
  line-height: 1.6;
}
</style>
