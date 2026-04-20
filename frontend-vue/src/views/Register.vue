<template>
  <div class="register-container">
    <div class="background-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>

    <div class="register-content">
      <div class="register-left">
        <div class="brand-section">
          <div class="brand-icon">🤖</div>
          <h1 class="brand-title">开始您的 AI 之旅</h1>
          <p class="brand-subtitle">注册账号，体验智能对话和知识管理</p>
        </div>

        <div class="benefits">
          <div class="benefit-item">
            <div class="benefit-icon">✨</div>
            <div class="benefit-text">
              <h3>免费使用</h3>
              <p>注册即可免费使用所有核心功能</p>
            </div>
          </div>
          <div class="benefit-item">
            <div class="benefit-icon">🔒</div>
            <div class="benefit-text">
              <h3>安全可靠</h3>
              <p>企业级安全保障，数据加密存储</p>
            </div>
          </div>
          <div class="benefit-item">
            <div class="benefit-icon">⚡</div>
            <div class="benefit-text">
              <h3>快速响应</h3>
              <p>毫秒级响应，流畅的使用体验</p>
            </div>
          </div>
        </div>
      </div>

      <div class="register-right">
        <div class="register-card">
          <div class="card-header">
            <h2>创建账号</h2>
            <p>填写信息，开始使用 AI Platform</p>
          </div>

          <form @submit.prevent="handleRegister" class="register-form">
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
                placeholder="至少8个字符"
                minlength="8"
                class="form-input"
                @input="validatePassword"
              />
              <div class="password-strength">
                <div class="strength-bar">
                  <div
                    class="strength-fill"
                    :style="{ width: passwordStrength.width, background: passwordStrength.color }"
                  ></div>
                </div>
                <span class="strength-text" :style="{ color: passwordStrength.color }">
                  {{ passwordStrength.text }}
                </span>
              </div>
            </div>

            <div class="form-group">
              <label>
                <span class="label-icon">🔑</span>
                <span>确认密码</span>
              </label>
              <input
                v-model="form.confirmPassword"
                type="password"
                required
                placeholder="再次输入密码"
                class="form-input"
              />
            </div>

            <div v-if="error" class="error-message">
              <span class="error-icon">⚠️</span>
              <span>{{ error }}</span>
            </div>

            <div v-if="success" class="success-message">
              <span class="success-icon">✅</span>
              <span>{{ success }}</span>
            </div>

            <button type="submit" :disabled="loading" class="btn-register">
              <span v-if="!loading">注册</span>
              <span v-else class="loading-text">
                <span class="spinner"></span>
                注册中...
              </span>
            </button>
          </form>

          <div class="divider">
            <span>或</span>
          </div>

          <div class="footer-links">
            <p>已有账号？<router-link to="/login" class="link-primary">立即登录</router-link></p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
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

const passwordStrength = computed(() => {
  const password = form.value.password
  if (!password) {
    return { width: '0%', color: '#E5E7EB', text: '' }
  }

  let strength = 0
  if (password.length >= 8) strength++
  if (password.length >= 12) strength++
  if (/[a-z]/.test(password)) strength++
  if (/[A-Z]/.test(password)) strength++
  if (/[0-9]/.test(password)) strength++
  if (/[^a-zA-Z0-9]/.test(password)) strength++

  if (strength <= 2) {
    return { width: '33%', color: '#EF4444', text: '弱' }
  } else if (strength <= 4) {
    return { width: '66%', color: '#F59E0B', text: '中等' }
  } else {
    return { width: '100%', color: '#10B981', text: '强' }
  }
})

const validatePassword = () => {
  // 实时验证密码
}

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
    error.value = err.response?.data?.error || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
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

.register-content {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 20px;
  gap: 60px;
}

.register-left {
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

.benefits {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.benefit-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.benefit-item:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateX(10px);
}

.benefit-icon {
  font-size: 32px;
  flex-shrink: 0;
}

.benefit-text h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
}

.benefit-text p {
  margin: 0;
  opacity: 0.9;
  font-size: 14px;
}

.register-right {
  flex: 0 0 480px;
  display: flex;
  align-items: center;
}

.register-card {
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

.register-form {
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
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary-500);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.password-strength {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.strength-bar {
  flex: 1;
  height: 4px;
  background: var(--gray-200);
  border-radius: 2px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  transition: all 0.3s ease;
  border-radius: 2px;
}

.strength-text {
  font-size: 12px;
  font-weight: 600;
  min-width: 40px;
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

.success-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #D1FAE5;
  color: #065F46;
  border-radius: 12px;
  font-size: 14px;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease;
}

.success-icon {
  font-size: 16px;
}

.btn-register {
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

.btn-register:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}

.btn-register:active:not(:disabled) {
  transform: translateY(0);
}

.btn-register:disabled {
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

/* 响应式设计 */
@media (max-width: 1024px) {
  .register-content {
    flex-direction: column;
    gap: 40px;
  }

  .register-left {
    text-align: center;
  }

  .brand-icon {
    margin-left: auto;
    margin-right: auto;
  }

  .benefits {
    max-width: 600px;
    margin: 0 auto;
  }

  .benefit-item:hover {
    transform: translateY(-5px);
  }

  .register-right {
    flex: 1;
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
  }
}

@media (max-width: 768px) {
  .register-card {
    padding: 32px 24px;
  }

  .brand-title {
    font-size: 36px;
  }

  .brand-subtitle {
    font-size: 16px;
  }

  .benefits {
    gap: 16px;
  }

  .benefit-item {
    padding: 16px;
  }
}
</style>
