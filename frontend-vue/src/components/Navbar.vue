<template>
  <nav class="navbar">
    <div class="navbar-container">
      <div class="navbar-left">
        <router-link to="/" class="logo">
          <div class="logo-icon">🤖</div>
          <span class="logo-text">AI Platform</span>
        </router-link>

        <div class="nav-links">
          <router-link to="/chat" class="nav-link">
            <span class="nav-icon">💬</span>
            <span>聊天</span>
          </router-link>
          <router-link to="/knowledge" class="nav-link">
            <span class="nav-icon">📚</span>
            <span>知识库</span>
          </router-link>
        </div>
      </div>

      <div class="navbar-right">
        <div class="user-menu" @click="toggleUserMenu" v-if="user">
          <div class="user-avatar">{{ getUserInitial() }}</div>
          <span class="user-name">{{ user.email }}</span>
          <span class="dropdown-icon">▼</span>

          <div v-if="showUserMenu" class="user-dropdown">
            <div class="dropdown-item" @click="handleProfile">
              <span class="dropdown-icon">👤</span>
              <span>个人信息</span>
            </div>
            <div class="dropdown-item" @click="handleSettings">
              <span class="dropdown-icon">⚙️</span>
              <span>设置</span>
            </div>
            <div class="dropdown-divider"></div>
            <div class="dropdown-item danger" @click="handleLogout">
              <span class="dropdown-icon">🚪</span>
              <span>退出登录</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()

const showUserMenu = ref(false)

const user = computed(() => authStore.user)

const toggleUserMenu = () => {
  showUserMenu.value = !showUserMenu.value
}

const closeUserMenu = (e) => {
  if (!e.target.closest('.user-menu')) {
    showUserMenu.value = false
  }
}

const getUserInitial = () => {
  if (!user.value || !user.value.email) return '?'
  return user.value.email.charAt(0).toUpperCase()
}

const handleProfile = () => {
  showUserMenu.value = false
  // TODO: 导航到个人信息页面
  console.log('Navigate to profile')
}

const handleSettings = () => {
  showUserMenu.value = false
  // TODO: 导航到设置页面
  console.log('Navigate to settings')
}

const handleLogout = async () => {
  showUserMenu.value = false
  try {
    await authStore.logout()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}

onMounted(() => {
  document.addEventListener('click', closeUserMenu)
})

onUnmounted(() => {
  document.removeEventListener('click', closeUserMenu)
})
</script>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: white;
  border-bottom: 1px solid var(--gray-200);
  box-shadow: var(--shadow-sm);
}

.navbar-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: var(--gray-900);
  font-weight: 600;
  font-size: 18px;
  transition: all var(--transition-base);
}

.logo:hover {
  transform: scale(1.05);
}

.logo-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

.logo-text {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.nav-links {
  display: flex;
  gap: 8px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--gray-600);
  font-weight: 500;
  font-size: 14px;
  transition: all var(--transition-base);
  position: relative;
}

.nav-link:hover {
  color: var(--primary-600);
  background: var(--primary-50);
}

.nav-link.router-link-active {
  color: var(--primary-600);
  background: var(--primary-50);
}

.nav-link.router-link-active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 16px;
  right: 16px;
  height: 2px;
  background: var(--primary-600);
  border-radius: var(--radius-full);
}

.nav-icon {
  font-size: 18px;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-menu {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-base);
}

.user-menu:hover {
  background: var(--gray-100);
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--gradient-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  box-shadow: var(--shadow-sm);
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--gray-700);
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-icon {
  font-size: 10px;
  color: var(--gray-400);
  transition: transform var(--transition-base);
}

.user-menu:hover .dropdown-icon {
  transform: translateY(2px);
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 200px;
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  padding: 8px;
  animation: slideInDown 0.2s ease-out;
}

@keyframes slideInDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  font-size: 14px;
  color: var(--gray-700);
}

.dropdown-item:hover {
  background: var(--gray-100);
  color: var(--gray-900);
}

.dropdown-item.danger {
  color: var(--error);
}

.dropdown-item.danger:hover {
  background: #FEE2E2;
}

.dropdown-item .dropdown-icon {
  font-size: 16px;
}

.dropdown-divider {
  height: 1px;
  background: var(--gray-200);
  margin: 8px 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .navbar-container {
    padding: 0 16px;
  }

  .navbar-left {
    gap: 16px;
  }

  .logo-text {
    display: none;
  }

  .nav-link span:not(.nav-icon) {
    display: none;
  }

  .user-name {
    display: none;
  }
}
</style>
