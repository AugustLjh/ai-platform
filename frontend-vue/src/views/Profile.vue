<template>
  <div class="profile-container">
    <div class="profile-content">
      <div class="profile-header">
        <div class="avatar">{{ userInitial }}</div>
        <div>
          <h1>个人中心</h1>
          <p>管理你的账户信息与使用偏好</p>
        </div>
      </div>

      <div class="profile-card">
        <div class="card-title">账户信息</div>
        <div class="info-grid">
          <div class="info-item">
            <span class="label">邮箱</span>
            <span class="value">{{ user?.email || '—' }}</span>
          </div>
          <div class="info-item">
            <span class="label">用户 ID</span>
            <span class="value">{{ user?.id || '—' }}</span>
          </div>
          <div class="info-item">
            <span class="label">租户 ID</span>
            <span class="value">{{ user?.tenant_id || user?.tenantId || '—' }}</span>
          </div>
          <div class="info-item">
            <span class="label">注册时间</span>
            <span class="value">{{ user?.created_at || user?.createdAt || '—' }}</span>
          </div>
        </div>
      </div>

      <div class="profile-card">
        <div class="card-title">功能规划</div>
        <p class="muted">个人资料编辑、头像上传、偏好设置等能力将在后续版本开放。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
const userInitial = computed(() => {
  if (!user.value || !user.value.email) return '?'
  return user.value.email.charAt(0).toUpperCase()
})
</script>

<style scoped>
.profile-container {
  flex: 1;
  min-height: 0;
  width: 100%;
  background: var(--gray-50);
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.profile-content {
  max-width: 1000px;
  margin: 0 auto;
  padding: 32px 24px;
  width: 100%;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-full);
  background: var(--gradient-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 600;
}

.profile-header h1 {
  margin: 0 0 6px 0;
  font-size: 28px;
}

.profile-header p {
  margin: 0;
  color: var(--gray-600);
}

.profile-card {
  background: white;
  padding: 24px;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--gray-800);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  font-size: 12px;
  color: var(--gray-500);
}

.value {
  font-size: 14px;
  color: var(--gray-800);
  word-break: break-all;
}

.muted {
  color: var(--gray-500);
  font-size: 14px;
}
</style>
