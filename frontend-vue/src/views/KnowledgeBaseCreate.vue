<template>
  <div class="knowledge-create-wrapper">
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
            <label>访问权限 *</label>
            <select v-model="form.access_level" required>
              <option value="tenant">租户共享</option>
              <option value="user">仅自己可见</option>
            </select>
            <p class="hint">知识库权限会作为新上传文档的默认权限。</p>
          </div>

          <div class="section-title">索引设置</div>

          <div class="form-group">
            <label>索引方式 *</label>
            <select v-model="form.indexing_method" required>
              <option value="structured">自然结构分块</option>
              <option value="paragraph">按段落分块</option>
              <option value="chunk">固定长度分块</option>
              <option value="full">整篇索引</option>
            </select>
            <p class="hint">索引方式创建后不可更换，请谨慎选择。</p>
          </div>

          <div class="form-grid" v-if="form.indexing_method !== 'full'">
            <div class="form-group">
              <label>单块最大长度</label>
              <input type="number" min="50" max="2000" step="50" v-model.number="form.chunk_size" />
            </div>
            <div class="form-group">
              <label>超长块重叠</label>
              <input type="number" min="0" max="500" step="10" v-model.number="form.chunk_overlap" />
            </div>
          </div>

          <div class="section-title">检索设置</div>

          <div class="form-group">
            <label>检索方式 *</label>
            <select v-model="form.retrieval_method" required>
              <option value="vector">向量检索</option>
              <option value="keyword">关键词检索</option>
              <option value="hybrid">混合检索</option>
            </select>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label>默认 Top K</label>
              <input type="number" min="1" max="50" step="1" v-model.number="form.top_k" />
            </div>
            <div class="form-group">
              <label>默认阈值</label>
              <input type="number" min="0" max="1" step="0.01" v-model.number="form.score_threshold" />
            </div>
          </div>

          <div class="section-title">初始化文档（可选）</div>

          <div class="form-group">
            <label>上传文件（可选）</label>
            <input
              type="file"
              @change="handleFileSelect"
              accept=".txt,.text,.log,.md,.markdown,.pdf,.html,.htm,.csv,.tsv,.xlsx,.docx,.rtf,.pptx,.json,.jsonl,.yaml,.yml,.xml"
              ref="fileInput"
            />
            <p class="hint">
              支持的文件类型：.txt, .text, .log, .md, .markdown, .pdf, .html, .htm, .csv, .tsv, .xlsx, .docx, .rtf,
              .pptx, .json, .jsonl, .yaml, .yml, .xml
            </p>
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

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const form = ref({
  name: '',
  description: '',
  access_level: 'tenant',
  indexing_method: 'structured',
  chunk_size: 500,
  chunk_overlap: 50,
  retrieval_method: 'hybrid',
  top_k: 5,
  score_threshold: 0
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

  let newKB = null

  try {
    newKB = await knowledgeStore.createKnowledgeBase({
      name: form.value.name,
      description: form.value.description,
      access_level: form.value.access_level
    })

    await knowledgeStore.updateIndexingSettings(newKB.id, {
      indexing_method: form.value.indexing_method,
      chunk_size: form.value.chunk_size,
      chunk_overlap: form.value.chunk_overlap,
      embedding_model_id: null
    })

    await knowledgeStore.updateRetrievalSettings(newKB.id, {
      retrieval_method: form.value.retrieval_method,
      top_k: form.value.top_k,
      score_threshold: form.value.score_threshold,
      vector_top_k: 40,
      keyword_top_k: 40,
      fusion_algorithm: 'rrf',
      rrf_k: 60,
      vector_weight: 0.65,
      keyword_weight: 0.35,
      max_candidates: 100,
      enable_rerank: false,
      rerank_model_id: null,
      query_rewrite: true
    })

    if (selectedFile.value) {
      await knowledgeStore.uploadDocument(newKB.id, selectedFile.value, {
        accessLevel: form.value.access_level
      })
    }

    router.push(`/knowledge/${newKB.id}`)
  } catch (err) {
    if (newKB?.id) {
      router.push(`/knowledge/${newKB.id}/settings`)
      return
    }
    error.value = err.response?.data?.detail || err.response?.data?.error || '创建知识库失败'
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
  flex: 1;
  min-height: 0;
  width: 100%;
  background: #f3f6fb;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.knowledge-create-container {
  max-width: 900px;
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

.form-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 32px;
}

.section-title {
  margin: 4px 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.form-group {
  margin-bottom: 24px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #1e293b;
}

.form-group input[type="text"],
.form-group input[type="number"],
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
.form-group input[type="number"]:focus,
.form-group textarea:focus,
.form-group select:focus {
  outline: none;
  border-color: #93a4b8;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
}

.form-group input[type="file"] {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
  cursor: pointer;
  background: #ffffff;
  color: #0f172a;
}

.hint {
  font-size: 12px;
  color: #64748b;
  margin-top: 6px;
}

.selected-file {
  font-size: 14px;
  color: #2563eb;
  margin-top: 8px;
  font-weight: 500;
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
