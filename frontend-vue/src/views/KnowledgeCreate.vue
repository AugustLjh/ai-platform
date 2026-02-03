<template>
  <div class="knowledge-create-wrapper">
    <Navbar />
    <div class="knowledge-create-container">
    <div class="header">
      <button @click="goBack" class="btn-back">← 返回</button>
      <h1>创建知识库</h1>
    </div>

    <div class="form-card">
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
          <label>上传文件（可选）</label>
          <input
            type="file"
            @change="handleFileSelect"
            accept=".txt,.md,.pdf,.html,.htm"
            ref="fileInput"
          />
          <p class="hint">支持的文件类型：.txt, .md, .pdf, .html, .htm</p>
          <p v-if="selectedFile" class="selected-file">
            已选择：{{ selectedFile.name }}
          </p>
        </div>

        <div v-if="error" class="error">{{ error }}</div>

        <div class="form-actions">
          <button type="button" @click="goBack" class="btn-secondary">
            取消
          </button>
          <button type="submit" :disabled="loading" class="btn-primary">
            {{ loading ? '创建中...' : '创建知识库' }}
          </button>
        </div>
      </form>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/store/knowledge'
import Navbar from '@/components/Navbar.vue'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const form = ref({
  name: '',
  description: ''
})

const loading = ref(false)
const error = ref('')
const selectedFile = ref(null)
const fileInput = ref(null)

const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
  }
}

const handleSubmit = async () => {
  loading.value = true
  error.value = ''

  try {
    // 如果用户上传了文件，直接上传文件
    if (selectedFile.value) {
      const newDoc = await knowledgeStore.uploadDocument(null, selectedFile.value)
      router.push(`/knowledge/${newDoc.id}`)
    } else {
      // 如果没有上传文件，创建一个空的知识库文档
      const newKB = await knowledgeStore.createKnowledgeBase(form.value)
      router.push(`/knowledge/${newKB.id}`)
    }
  } catch (err) {
    error.value = err.response?.data?.error || '创建知识库失败'
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/knowledge')
}
</script>

<style scoped>
.knowledge-create-wrapper {
  min-height: 100vh;
  background: linear-gradient(180deg, #f8f9ff 0%, #ffffff 100%);
}

.knowledge-create-container {
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
  color: #111827;
  margin: 0;
}

.btn-back {
  padding: 8px 16px;
  background: #F3F4F6;
  color: #374151;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-back:hover {
  background: #E5E7EB;
}

.form-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 32px;
}

.form-group {
  margin-bottom: 24px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #374151;
}

.form-group input[type="text"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
}

.form-group input[type="text"]:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.form-group input[type="file"] {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
  cursor: pointer;
}

.hint {
  font-size: 12px;
  color: #6B7280;
  margin-top: 4px;
}

.selected-file {
  font-size: 14px;
  color: #4F46E5;
  margin-top: 8px;
  font-weight: 500;
}

.error {
  padding: 12px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 8px;
  margin-bottom: 20px;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 32px;
}

.btn-primary {
  padding: 12px 24px;
  background: #4F46E5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #4338CA;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 12px 24px;
  background: #E5E7EB;
  color: #374151;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-secondary:hover {
  background: #D1D5DB;
}
</style>
