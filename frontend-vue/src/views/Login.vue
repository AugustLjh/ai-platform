<template>
  <div class="login-container">
    <div class="background-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>

    <div class="login-content">
      <div class="login-left">
        <div class="brand-section">
          <div class="brand-icon">🤖</div>
          <h1 class="brand-title">AI Platform</h1>
          <p class="brand-subtitle">智能对话 · 知识管理 · 高效协作</p>
        </div>

        <div class="features">
          <div class="feature-item">
            <div class="feature-icon">💬</div>
            <div class="feature-text">
              <h3>智能对话</h3>
              <p>与AI助手进行自然流畅的对话</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">📚</div>
            <div class="feature-text">
              <h3>知识管理</h3>
              <p>构建和管理您的知识库</p>
            </div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">⚡</div>
            <div class="feature-text">
              <h3>高效协作</h3>
              <p>团队共享，提升工作效率</p>
            </div>
          </div>
        </div>
      </div>

      <div class="login-right">
        <div class="login-card">
          <div class="card-header">
            <h2>欢迎回来</h2>
            <p>登录您的账号继续使用</p>
          </div>

          <form @submit.prevent="handleLogin" class="login-form">
            <div class="form-group">
              <label>
                <span class="label-icon">📧</span>
                <span>邮箱地址</span>
              </label>
              <input
                v-model="form.email"
                type="email"
                required
                placeholder="your@example.com"
                class="form-input"
              />
            </div>

            <div class="form-group">
              <label>
                <span class="label-icon">🔒</span>
                <span>密码</span>
              </label>
              <input
                v-model="form.password"
                type="password"
                required
                placeholder="请输入密码"
                class="form-input"
              />
            </div>

            <div v-if="inactivityMessage" class="info-message">
              <span class="info-icon">ℹ️</span>
              <span>{{ inactivityMessage }}</span>
            </div>

            <div v-if="error" class="error-message">
              <span class="error-icon">⚠️</span>
              <span>{{ error }}</span>
            </div>

            <button type="submit" :disabled="loading" class="btn-login">
              <span v-if="!loading">登录</span>
              <span v-else class="loading-text">
                <span class="spinner"></span>
                登录中...
              </span>
            </button>
          </form>

          <div class="divider">
            <span>或</span>
          </div>

          <div class="footer-links">
            <p>还没有账号？<router-link to="/register" class="link-primary">立即注册</router-link></p>
          </div>

          <div class="demo-info">
            <div class="demo-header">
              <span class="demo-icon">💡</span>
              <span class="demo-title">演示访问</span>
            </div>
            <p class="demo-copy">演示账号由管理员统一分配，登录页不再展示默认账号和密码。</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const form = ref({
  email: '',
  password: ''
})
const loading = ref(false)
const error = ref('')
const inactivityMessage = ref('')

// Check if user was logged out due to inactivity
if (route.query.reason === 'inactivity') {
  inactivityMessage.value = '由于24小时未活跃，您已被自动登出，请重新登录'
}

const handleLogin = async () => {
  loading.value = true
  error.value = ''
  inactivityMessage.value = ''

  try {
    await authStore.login(form.value.email, form.value.password)
    router.push('/chat')
  } catch (err) {
    error.value = err.response?.data?.error || '登录失败，请检查邮箱和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  overflow: hidden;
}

.background-shapes {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  z-index: 0;
}

.shape {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  animation: float 20s infinite ease-in-out;
}

.shape-1 {
  width: 300px;
  height: 300px;
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.shape-2 {
  width: 200px;
  height: 200px;
  bottom: -50px;
  right: 10%;
  animation-delay: 5s;
}

.shape-3 {
  width: 150px;
  height: 150px;
  top: 50%;
  right: -50px;
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) rotate(0deg);
  }
  33% {
    transform: translate(30px, -30px) rotate(120deg);
  }
  66% {
    transform: translate(-20px, 20px) rotate(240deg);
  }
}

.login-content {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
  gap: 60px;
}

.login-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: white;
}

.brand-section {
  margin-bottom: 60px;
}

.brand-icon {
  width: 80px;
  height: 80px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  margin-bottom: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.brand-title {
  font-size: 48px;
  font-weight: 700;
  margin: 0 0 16px 0;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.brand-subtitle {
  font-size: 20px;
  opacity: 0.9;
  margin: 0;
}

.features {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.feature-item:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateX(10px);
}

.feature-icon {
  font-size: 32px;
  flex-shrink: 0;
}

.feature-text h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
}

.feature-text p {
  margin: 0;
  opacity: 0.9;
  font-size: 14px;
}

.login-right {
  flex: 0 0 480px;
  display: flex;
  align-items: center;
}

.login-card {
  width: 100%;
  background: white;
  border-radius: 24px;
  padding: 48px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: slideInRight 0.6s ease-out;
}

@keyframes slideInRight {
  from {
    opacity: 0;
    transform: translateX(30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.card-header {
  margin-bottom: 32px;
  text-align: center;
}

.card-header h2 {
  font-size: 28px;
  font-weight: 700;
  color: var(--gray-900);
  margin: 0 0 8px 0;
}

.card-header p {
  font-size: 14px;
  color: var(--gray-500);
  margin: 0;
}

.login-form {
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: var(--gray-700);
}

.label-icon {
  font-size: 16px;
}

.form-input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid var(--gray-200);
  border-radius: 12px;
  font-size: 14px;
  font-family: inherit;
  transition: all 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #FEE2E2;
  color: #991B1B;
  border-radius: 12px;
  font-size: 14px;
  margin-bottom: 20px;
  animation: shake 0.5s ease;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-10px); }
  75% { transform: translateX(10px); }
}

.error-icon {
  font-size: 16px;
}

.info-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #DBEAFE;
  color: #1E40AF;
  border-radius: 12px;
  font-size: 14px;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease;
}

.info-icon {
  font-size: 16px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.btn-login {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}

.btn-login:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}

.btn-login:active:not(:disabled) {
  transform: translateY(0);
}

.btn-login:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-text {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.divider {
  position: relative;
  text-align: center;
  margin: 24px 0;
}

.divider::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--gray-200);
}

.divider span {
  position: relative;
  display: inline-block;
  padding: 0 16px;
  background: white;
  color: var(--gray-400);
  font-size: 14px;
}

.footer-links {
  text-align: center;
  margin-bottom: 24px;
}

.footer-links p {
  font-size: 14px;
  color: var(--gray-600);
  margin: 0;
}

.link-primary {
  color: var(--primary-600);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s ease;
}

.link-primary:hover {
  color: var(--primary-700);
  text-decoration: underline;
}

.demo-info {
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  border-radius: 16px;
  border: 1px solid var(--gray-200);
}

.demo-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.demo-icon {
  font-size: 20px;
}

.demo-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--gray-700);
}

.demo-copy {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--gray-700);
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .login-content {
    flex-direction: column;
    gap: 40px;
  }

  .login-left {
    text-align: center;
  }

  .brand-icon {
    margin-left: auto;
    margin-right: auto;
  }

  .features {
    max-width: 600px;
    margin: 0 auto;
  }

  .feature-item:hover {
    transform: translateY(-5px);
  }

  .login-right {
    flex: 1;
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
  }
}

@media (max-width: 768px) {
  .login-card {
    padding: 32px 24px;
  }

  .brand-title {
    font-size: 36px;
  }

  .brand-subtitle {
    font-size: 16px;
  }

  .features {
    gap: 16px;
  }

  .feature-item {
    padding: 16px;
  }
}
</style>
