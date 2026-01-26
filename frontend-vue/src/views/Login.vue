<template>
  <div class="login-container">
    <div class="login-card">
      <h1>🤖 AI 平台</h1>
      <p class="subtitle">Vue 前端</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label>邮箱</label>
          <input v-model="form.email" type="email" required placeholder="your@example.com" />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" required placeholder="请输入密码" />
        </div>

        <button type="submit" :disabled="loading" class="btn-primary">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <div class="footer">
        <p>还没有账号？<router-link to="/register">立即注册</router-link></p>
        <div class="demo-info">
          <p><strong>演示账号：</strong></p>
          <p>邮箱：demo@example.com</p>
          <p>密码：demo123456</p>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = ref({
  email: '',
  password: ''
})
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  loading.value = true
  error.value = ''

  try {
    await authStore.login(form.value.email, form.value.password)
    router.push('/knowledge')
  } catch (err) {
    error.value = err.response?.data?.error || '登录失败，请检查邮箱和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  background: white;
  border-radius: 12px;
  padding: 40px;
  width: 100%;
  max-width: 450px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
}

h1 {
  text-align: center;
  margin-bottom: 8px;
  color: #111827;
}

.subtitle {
  text-align: center;
  color: #6B7280;
  margin-bottom: 32px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #374151;
}

.form-group input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.btn-primary {
  width: 100%;
  padding: 12px;
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

.footer {
  margin-top: 24px;
  text-align: center;
}

.footer a {
  color: #4F46E5;
  text-decoration: none;
  font-weight: 500;
}

.demo-info {
  margin-top: 20px;
  padding: 16px;
  background: #F3F4F6;
  border-radius: 8px;
  font-size: 13px;
}

.error {
  margin-top: 16px;
  padding: 12px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 8px;
  font-size: 14px;
  text-align: center;
}
</style>
