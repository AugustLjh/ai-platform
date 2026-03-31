<template>
  <article class="artifact-card">
    <div class="artifact-head">
      <div>
        <div class="artifact-kicker">代码文件</div>
        <h4>{{ artifact.name || 'Code Files' }}</h4>
      </div>
      <span class="artifact-count">{{ files.length }}</span>
    </div>

    <div v-if="files.length === 0" class="artifact-empty">
      当前没有可展示的代码文件。
    </div>

    <div v-else class="file-list">
      <section v-for="file in files" :key="`${file.path}-${file.language}`" class="file-card">
        <div class="file-head">
          <strong>{{ file.path }}</strong>
          <span v-if="file.language">{{ file.language }}</span>
        </div>
        <pre>{{ file.content }}</pre>
      </section>
    </div>
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

const files = computed(() => Array.isArray(props.artifact?.payload?.files) ? props.artifact.payload.files : [])
</script>

<style scoped>
.artifact-card {
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfc 100%);
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
  color: var(--primary-700);
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
  background: rgba(16, 163, 127, 0.1);
  color: var(--primary-700);
  font-weight: 700;
}

.artifact-empty {
  margin-top: 12px;
  color: var(--gray-500);
  font-size: 14px;
}

.file-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.file-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  overflow: hidden;
  background: #f8fafc;
}

.file-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: white;
  font-size: 13px;
}

.file-head span {
  color: var(--gray-500);
}

pre {
  margin: 0;
  padding: 14px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}
</style>
