<template>
  <div class="knowledge-edit-wrapper">
    <div class="knowledge-edit-container">
    <div class="header">
      <button @click="goBack" class="btn-back">← 返回</button>
      <h1>编辑知识库</h1>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-if="!loading && knowledgeBase" class="form-card">
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label>名称 *</label>
          <input
            v-model="form.name"
            type="text"
            required
            placeholder="请输入知识库名称"
          />
        </div>

        <div class="form-group">
          <label>描述</label>
          <textarea
            v-model="form.description"
            rows="4"
            placeholder="请输入描述（可选）"
          ></textarea>
        </div>

        <div class="form-group">
          <label>访问权限</label>
          <select :value="form.access_level" disabled>
            <option value="tenant">租户共享</option>
            <option value="user">仅自己可见</option>
          </select>
          <p class="field-hint">访问权限由创建时确定，当前后端不支持修改。</p>
        </div>

        <div class="form-group">
          <label>元数据（JSON）</label>
          <textarea
            v-model="form.metadata_json"
            rows="8"
            placeholder="{\n  &quot;owner&quot;: &quot;team-a&quot;\n}"
          ></textarea>
        </div>

        <div v-if="error" class="error">{{ error }}</div>

        <div class="form-actions">
          <button type="button" @click="goBack" class="btn-secondary">
            取消
          </button>
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中...' : '保存更改' }}
          </button>
        </div>
      </form>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'

const router = useRouter()
const route = useRoute()
const knowledgeStore = useKnowledgeStore()

const knowledgeBase = ref(null)
const form = ref({
  name: '',
  description: '',
  access_level: 'tenant',
  metadata_json: '{}'
})

const loading = ref(false)
const saving = ref(false)
const error = ref('')

const knowledgeBaseId = route.params.id

onMounted(async () => {
  await loadKnowledgeBase()
})

const loadKnowledgeBase = async () => {
  loading.value = true
  error.value = ''
  try {
    knowledgeBase.value = await knowledgeStore.fetchKnowledgeBase(knowledgeBaseId)
    form.value = {
      name: knowledgeBase.value.name,
      description: knowledgeBase.value.description || '',
      access_level: knowledgeBase.value.access_level || 'tenant',
      metadata_json: JSON.stringify(knowledgeBase.value.metadata || {}, null, 2)
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '加载知识库失败'
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  saving.value = true
  error.value = ''

  try {
    let metadata = {}
    try {
      metadata = form.value.metadata_json.trim() ? JSON.parse(form.value.metadata_json) : {}
    } catch (_err) {
      error.value = '元数据必须是合法 JSON'
      saving.value = false
      return
    }

    await knowledgeStore.updateKnowledgeBase(knowledgeBaseId, {
      name: form.value.name.trim(),
      description: form.value.description,
      metadata
    })
    router.push(`/knowledge/${knowledgeBaseId}`)
  } catch (err) {
    error.value = err.response?.data?.detail || '更新知识库失败'
  } finally {
    saving.value = false
  }
}

const goBack = () => {
  router.push(`/knowledge/${knowledgeBaseId}`)
}
</script>

<style scoped>
.knowledge-edit-wrapper {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: #f3f6fb;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.knowledge-edit-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 32px;
  color: #0f172a;
  margin: 0;
}

.btn-back {
  padding: 8px 16px;
  background: #ffffff;
  color: #1e293b;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-back:hover {
  background: #f1f5f9;
  border-color: #93a4b8;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #64748b;
}

.form-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 32px;
}

.form-group {
  margin-bottom: 24px;
}

.field-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: #64748b;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #1e293b;
}

.form-group input[type="text"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
  background: #ffffff;
  color: #0f172a;
}

.form-group input[type="text"]:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #93a4b8;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
}

.error {
  padding: 12px;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid #fca5a5;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 32px;
}

.btn-primary {
  padding: 12px 24px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: filter 0.2s ease;
}

.btn-primary:hover {
  filter: brightness(1.05);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 12px 24px;
  background: #ffffff;
  color: #1e293b;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: #f1f5f9;
  border-color: #93a4b8;
}
</style>
