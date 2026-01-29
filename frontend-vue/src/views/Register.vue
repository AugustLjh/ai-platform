<template>
  <div class="register-container">
    <div class="register-card">
      <h1>创建账号</h1>
      <p class="subtitle">加入 AI 平台</p>

      <form @submit.prevent="handleRegister" class="register-form">
        <div class="form-group">
          <label>邮箱</label>
          <input
            v-model="form.email"
            type="email"
            required
            placeholder="your@example.com"
          />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            required
            placeholder="至少8个字符，包含大小写字母和数字"
            minlength="8"
          />
          <div class="password-hint">
            密码要求：至少8个字符，包含大写字母、小写字母和数字
          </div>
        </div>

        <div class="form-group">
          <label>确认密码</label>
          <input
            v-model="form.confirmPassword"
            type="password"
            required
            placeholder="再次输入密码"
          />
        </div>

        <button type="submit" :disabled="loading" class="btn-primary">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <div class="footer">
        <p>已有账号？<router-link to="/login">立即登录</router-link></p>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="success" class="success">{{ success }}</div>
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
  password: '',
  confirmPassword: ''
})
const loading = ref(false)
const error = ref('')
const success = ref('')

const handleRegister = async () => {
  loading.value = true
  error.value = ''
  success.value = ''

  // Validate passwords match
  if (form.value.password !== form.value.confirmPassword) {
    error.value = '两次输入的密码不一致'
    loading.value = false
    return
  }

  // Validate password length
  if (form.value.password.length < 8) {
    error.value = '密码长度至少为8个字符'
    loading.value = false
    return
  }

  try {
    await authStore.register(form.value.email, form.value.password)
    success.value = '注册成功！正在跳转到登录页面...'

    setTimeout(() => {
      router.push('/login')
    }, 2000)
  } catch (err) {
    // Display detailed error message from backend
    error.value = err.response?.data?.error || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.register-card {
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
  box-sizing: border-box;
}

.form-group input:focus {
  outline: none;
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.password-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6B7280;
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

.error {
  margin-top: 16px;
  padding: 12px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 8px;
  font-size: 14px;
  text-align: center;
}

.success {
  margin-top: 16px;
  padding: 12px;
  background: #D1FAE5;
  color: #065F46;
  border-radius: 8px;
  font-size: 14px;
  text-align: center;
}
</style>
