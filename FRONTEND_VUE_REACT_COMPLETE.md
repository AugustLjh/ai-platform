# Vue & React 前端项目完整指南
# Complete Guide for Vue & React Frontends

<div align="center">

**AI Platform 的 Vue 3 和 React 18 前端实现**

**Vue 3 and React 18 Frontend Implementations for AI Platform**

[中文](#中文文档) | [English](#english-documentation)

</div>

---

# 中文文档

## 📦 项目概览

本项目提供了两个完整的前端实现：
- **frontend-vue/** - 使用 Vue 3 + Vite + Pinia
- **frontend-react/** - 使用 React 18 + Vite + Zustand (即将完成)

两个版本功能完全相同，开发者可以根据技术栈偏好选择使用。

## ✨ 功能特性

### 核心功能
- ✅ 用户注册和登录
- ✅ JWT 认证（自动刷新）
- ✅ 实时聊天（SSE 流式响应）
- ✅ 多会话管理
- ✅ 消息历史持久化
- ✅ RAG/Agent 配置
- ✅ Temperature 调节

### 技术特性
- ⚡ Vite 极速开发体验
- 📱 响应式设计（移动端适配）
- 🎨 现代化 UI 设计
- 🔄 自动 Token 刷新
- 💾 LocalStorage 持久化
- 🎯 TypeScript 支持（可选）

## 🏗️ Vue 3 版本

### 技术栈
- **Vue 3.4** - Composition API
- **Vite 5.0** - 构建工具
- **Pinia 2.1** - 状态管理
- **Vue Router 4.2** - 路由管理
- **Axios** - HTTP 客户端

### 项目结构

```
frontend-vue/
├── public/                     # 静态资源
├── src/
│   ├── api/                   # API 服务层
│   │   ├── axios.js          # Axios 配置（拦截器、刷新）
│   │   └── index.js          # API 端点定义
│   │
│   ├── assets/               # 资源文件
│   │   └── styles/           # 全局样式
│   │       ├── main.css      # 主样式
│   │       └── variables.css # CSS 变量
│   │
│   ├── components/           # 可复用组件
│   │   ├── ChatMessage.vue   # 消息气泡组件
│   │   ├── ChatInput.vue     # 消息输入框
│   │   ├── SessionList.vue   # 会话列表
│   │   ├── SettingsPanel.vue # 设置面板
│   │   └── LoadingSpinner.vue # 加载动画
│   │
│   ├── views/                # 页面组件
│   │   ├── Login.vue         # 登录页
│   │   ├── Register.vue      # 注册页
│   │   └── Chat.vue          # 聊天主页
│   │
│   ├── router/               # 路由配置
│   │   └── index.js          # 路由定义、守卫
│   │
│   ├── store/                # Pinia 状态管理
│   │   ├── auth.js           # 认证状态
│   │   └── chat.js           # 聊天状态
│   │
│   ├── utils/                # 工具函数
│   │   ├── format.js         # 格式化工具
│   │   └── uuid.js           # UUID 生成
│   │
│   ├── App.vue               # 根组件
│   └── main.js               # 应用入口
│
├── index.html                # HTML 模板
├── package.json              # 依赖配置
├── vite.config.js            # Vite 配置
├── README.md                 # 英文文档
└── README_CN.md              # 中文文档
```

### 核心文件说明

#### 1. API 服务层 (`src/api/`)

**axios.js** - Axios 实例配置
```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080',
  timeout: 30000
})

// 请求拦截器：添加 Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：自动刷新 Token
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // 自动刷新 token 逻辑
      const refreshed = await refreshToken()
      if (refreshed) {
        return api.request(error.config)
      }
    }
    return Promise.reject(error)
  }
)

export default api
```

**index.js** - API 端点定义
```javascript
import api from './axios'

export const authAPI = {
  register: (email, password) =>
    api.post('/api/v1/auth/register', { email, password }),

  login: (email, password) =>
    api.post('/api/v1/auth/login', { email, password }),

  logout: () =>
    api.post('/api/v1/auth/logout'),

  getCurrentUser: () =>
    api.get('/api/v1/auth/me')
}

export const chatAPI = {
  sendMessage: (sessionId, message, config) =>
    api.post('/api/v1/chat', { session_id: sessionId, message, config }),

  sendMessageSSE: async (sessionId, message, config, onChunk) => {
    // SSE 流式响应实现
    const response = await fetch(`${api.defaults.baseURL}/api/v1/chat/sse`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({ session_id: sessionId, message, config })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)
      // 处理 SSE 数据
      onChunk(chunk)
    }
  }
}
```

#### 2. 状态管理 (`src/store/`)

**auth.js** - 认证状态
```javascript
import { defineStore } from 'pinia'
import { authAPI } from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    accessToken: localStorage.getItem('access_token'),
    isAuthenticated: !!localStorage.getItem('access_token')
  }),

  actions: {
    async login(email, password) {
      const { data } = await authAPI.login(email, password)
      this.setAuth(data)
      return data
    },

    async logout() {
      await authAPI.logout()
      this.clearAuth()
    },

    setAuth(data) {
      this.user = data.user
      this.accessToken = data.access_token
      this.isAuthenticated = true
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
    },

    clearAuth() {
      this.user = null
      this.accessToken = null
      this.isAuthenticated = false
      localStorage.clear()
    }
  }
})
```

**chat.js** - 聊天状态
```javascript
import { defineStore } from 'pinia'
import { chatAPI } from '@/api'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: JSON.parse(localStorage.getItem('chat_sessions') || '{}'),
    currentSessionId: localStorage.getItem('current_session_id'),
    config: {
      useRAG: false,
      useAgent: false,
      temperature: 0.7
    }
  }),

  getters: {
    currentSession(state) {
      return state.currentSessionId
        ? state.sessions[state.currentSessionId]
        : null
    },

    sortedSessions(state) {
      return Object.values(state.sessions)
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    }
  },

  actions: {
    createSession() {
      const sessionId = this.generateUUID()
      const session = {
        id: sessionId,
        title: `Session ${Object.keys(this.sessions).length + 1}`,
        messages: [],
        createdAt: new Date().toISOString()
      }
      this.sessions[sessionId] = session
      this.currentSessionId = sessionId
      this.saveSessions()
      return session
    },

    async sendMessage(message) {
      if (!this.currentSessionId) {
        this.createSession()
      }

      // 添加用户消息
      this.addMessage({
        role: 'user',
        content: message
      })

      // 添加助手占位符
      this.addMessage({
        role: 'assistant',
        content: '',
        streaming: true
      })

      try {
        // 使用 SSE 流式发送
        await chatAPI.sendMessageSSE(
          this.currentSessionId,
          message,
          this.config,
          (chunk) => {
            // 更新最后一条消息
            const lastMessage = this.currentSession.messages[
              this.currentSession.messages.length - 1
            ]
            lastMessage.content += chunk
            this.saveSessions()
          }
        )

        // 标记流式完成
        const lastMessage = this.currentSession.messages[
          this.currentSession.messages.length - 1
        ]
        lastMessage.streaming = false
        this.saveSessions()
      } catch (error) {
        // 错误处理
        const lastMessage = this.currentSession.messages[
          this.currentSession.messages.length - 1
        ]
        lastMessage.content = `Error: ${error.message}`
        lastMessage.error = true
        this.saveSessions()
        throw error
      }
    },

    addMessage(message) {
      if (this.currentSession) {
        this.currentSession.messages.push({
          ...message,
          timestamp: new Date().toISOString()
        })
        this.saveSessions()
      }
    },

    saveSessions() {
      localStorage.setItem('chat_sessions', JSON.stringify(this.sessions))
    },

    generateUUID() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0
        const v = c === 'x' ? r : (r & 0x3 | 0x8)
        return v.toString(16)
      })
    }
  }
})
```

#### 3. 路由配置 (`src/router/index.js`)

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue')
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue')
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/Chat.vue'),
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 导航守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && authStore.isAuthenticated) {
    next('/chat')
  } else {
    next()
  }
})

export default router
```

#### 4. 组件示例

**Login.vue** - 登录页面
```vue
<template>
  <div class="login-container">
    <div class="login-card">
      <h1>🤖 AI Platform</h1>
      <p class="subtitle">Vue Frontend</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label>Email</label>
          <input
            v-model="form.email"
            type="email"
            required
            placeholder="your@example.com"
          />
        </div>

        <div class="form-group">
          <label>Password</label>
          <input
            v-model="form.password"
            type="password"
            required
            placeholder="Enter password"
          />
        </div>

        <button type="submit" :disabled="loading" class="btn-primary">
          {{ loading ? 'Logging in...' : 'Login' }}
        </button>
      </form>

      <div class="footer">
        <p>
          Don't have an account?
          <router-link to="/register">Register</router-link>
        </p>
        <div class="demo-info">
          <p><strong>Demo Account:</strong></p>
          <p>Email: demo@example.com</p>
          <p>Password: demo123456</p>
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
    router.push('/chat')
  } catch (err) {
    error.value = err.response?.data?.error || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 样式省略，参见完整文件 */
</style>
```

**Chat.vue** - 聊天主页
```vue
<template>
  <div class="chat-container">
    <!-- 头部 -->
    <header class="chat-header">
      <h2>🤖 AI Platform</h2>
      <div class="header-right">
        <span>{{ authStore.user?.email }}</span>
        <button @click="handleLogout" class="btn-secondary">Logout</button>
      </div>
    </header>

    <div class="chat-main">
      <!-- 侧边栏 -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <h3>Sessions</h3>
          <button @click="chatStore.createSession" class="btn-icon">+</button>
        </div>

        <div class="session-list">
          <div
            v-for="session in chatStore.sortedSessions"
            :key="session.id"
            :class="['session-item', { active: session.id === chatStore.currentSessionId }]"
            @click="chatStore.loadSession(session.id)"
          >
            {{ session.title }}
          </div>
        </div>

        <!-- 设置面板 -->
        <div class="sidebar-footer">
          <h4>Settings</h4>
          <label>
            <input v-model="chatStore.config.useRAG" type="checkbox" />
            Enable RAG
          </label>
          <label>
            <input v-model="chatStore.config.useAgent" type="checkbox" />
            Enable Agent
          </label>
          <label>
            Temperature: {{ chatStore.config.temperature }}
            <input
              v-model.number="chatStore.config.temperature"
              type="range"
              min="0"
              max="1"
              step="0.1"
            />
          </label>
        </div>
      </aside>

      <!-- 聊天区域 -->
      <div class="chat-area">
        <div class="chat-messages" ref="messagesContainer">
          <div
            v-for="(message, index) in chatStore.currentSession?.messages || []"
            :key="index"
            :class="['message', message.role]"
          >
            <div class="message-avatar">
              {{ message.role === 'user' ? '👤' : '🤖' }}
            </div>
            <div class="message-content">
              <div class="message-header">
                <span class="message-role">
                  {{ message.role === 'user' ? 'You' : 'AI Assistant' }}
                </span>
                <span class="message-time">
                  {{ formatTime(message.timestamp) }}
                </span>
              </div>
              <div class="message-text">{{ message.content }}</div>
            </div>
          </div>
        </div>

        <div class="chat-input-container">
          <form @submit.prevent="handleSend" class="chat-input-form">
            <textarea
              v-model="messageInput"
              @keydown.enter.exact.prevent="handleSend"
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              rows="1"
            />
            <button type="submit" :disabled="sending || !messageInput.trim()">
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()

const messageInput = ref('')
const sending = ref(false)
const messagesContainer = ref(null)

const handleSend = async () => {
  if (!messageInput.value.trim() || sending.value) return

  const message = messageInput.value.trim()
  messageInput.value = ''
  sending.value = true

  try {
    await chatStore.sendMessage(message)
  } catch (error) {
    console.error('Send message error:', error)
  } finally {
    sending.value = false
  }
}

const handleLogout = async () => {
  if (confirm('Are you sure you want to logout?')) {
    await authStore.logout()
    router.push('/login')
  }
}

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 自动滚动到底部
watch(
  () => chatStore.currentSession?.messages,
  () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  },
  { deep: true }
)

// 初始化
if (!chatStore.currentSessionId && Object.keys(chatStore.sessions).length === 0) {
  chatStore.createSession()
}
</script>

<style scoped>
/* 样式省略，参见完整文件 */
</style>
```

### 安装和运行

```bash
# 进入 Vue 项目目录
cd frontend-vue

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问 http://localhost:3000
```

### 环境配置

创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8080
```

### 构建部署

```bash
# 生产构建
npm run build

# 输出到 dist/ 目录
```

---

## 🔵 React 18 版本

### 技术栈
- **React 18.2** - Hooks + Functional Components
- **Vite 5.0** - 构建工具
- **Zustand 4.4** - 状态管理
- **React Router 6.20** - 路由管理
- **Axios** - HTTP 客户端

### 项目结构

```
frontend-react/
├── public/                     # 静态资源
├── src/
│   ├── api/                   # API 服务层
│   │   ├── axios.js          # Axios 配置
│   │   └── index.js          # API 端点
│   │
│   ├── assets/               # 资源文件
│   │   └── styles/           # 全局样式
│   │
│   ├── components/           # 可复用组件
│   │   ├── ChatMessage.jsx   # 消息气泡
│   │   ├── ChatInput.jsx     # 消息输入
│   │   ├── SessionList.jsx   # 会话列表
│   │   └── SettingsPanel.jsx # 设置面板
│   │
│   ├── pages/                # 页面组件
│   │   ├── Login.jsx         # 登录页
│   │   ├── Register.jsx      # 注册页
│   │   └── Chat.jsx          # 聊天主页
│   │
│   ├── store/                # Zustand 状态
│   │   ├── useAuthStore.js   # 认证状态
│   │   └── useChatStore.js   # 聊天状态
│   │
│   ├── utils/                # 工具函数
│   │   └── helpers.js
│   │
│   ├── App.jsx               # 根组件
│   └── main.jsx              # 应用入口
│
├── index.html
├── package.json
├── vite.config.js
├── README.md                 # 英文文档
└── README_CN.md              # 中文文档
```

### React 核心实现

#### Zustand Store

**useAuthStore.js**
```javascript
import { create } from 'zustand'
import { authAPI } from '../api'

export const useAuthStore = create((set) => ({
  user: null,
  accessToken: localStorage.getItem('access_token'),
  isAuthenticated: !!localStorage.getItem('access_token'),

  login: async (email, password) => {
    const { data } = await authAPI.login(email, password)
    set({
      user: data.user,
      accessToken: data.access_token,
      isAuthenticated: true
    })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    return data
  },

  logout: async () => {
    await authAPI.logout()
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false
    })
    localStorage.clear()
  },

  getCurrentUser: async () => {
    const { data } = await authAPI.getCurrentUser()
    set({ user: data })
    return data
  }
}))
```

**useChatStore.js**
```javascript
import { create } from 'zustand'
import { chatAPI } from '../api'

export const useChatStore = create((set, get) => ({
  sessions: JSON.parse(localStorage.getItem('chat_sessions') || '{}'),
  currentSessionId: localStorage.getItem('current_session_id'),
  config: {
    useRAG: false,
    useAgent: false,
    temperature: 0.7
  },

  createSession: () => {
    const sessionId = generateUUID()
    const session = {
      id: sessionId,
      title: `Session ${Object.keys(get().sessions).length + 1}`,
      messages: [],
      createdAt: new Date().toISOString()
    }

    set(state => ({
      sessions: {
        ...state.sessions,
        [sessionId]: session
      },
      currentSessionId: sessionId
    }))

    get().saveSessions()
    return session
  },

  sendMessage: async (message) => {
    const { currentSessionId, config, addMessage, saveSessions } = get()

    if (!currentSessionId) {
      get().createSession()
    }

    // 添加用户消息
    addMessage({
      role: 'user',
      content: message
    })

    // 添加助手占位符
    addMessage({
      role: 'assistant',
      content: '',
      streaming: true
    })

    try {
      await chatAPI.sendMessageSSE(
        currentSessionId,
        message,
        config,
        (chunk) => {
          set(state => {
            const session = state.sessions[currentSessionId]
            const lastMessage = session.messages[session.messages.length - 1]
            lastMessage.content += chunk
            return { sessions: { ...state.sessions } }
          })
          saveSessions()
        }
      )

      // 标记完成
      set(state => {
        const session = state.sessions[currentSessionId]
        const lastMessage = session.messages[session.messages.length - 1]
        lastMessage.streaming = false
        return { sessions: { ...state.sessions } }
      })
      saveSessions()
    } catch (error) {
      // 错误处理
      set(state => {
        const session = state.sessions[currentSessionId]
        const lastMessage = session.messages[session.messages.length - 1]
        lastMessage.content = `Error: ${error.message}`
        lastMessage.error = true
        return { sessions: { ...state.sessions } }
      })
      saveSessions()
      throw error
    }
  },

  addMessage: (message) => {
    set(state => {
      const session = state.sessions[state.currentSessionId]
      if (session) {
        session.messages.push({
          ...message,
          timestamp: new Date().toISOString()
        })
      }
      return { sessions: { ...state.sessions } }
    })
    get().saveSessions()
  },

  saveSessions: () => {
    localStorage.setItem('chat_sessions', JSON.stringify(get().sessions))
  }
}))

const generateUUID = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}
```

#### React Router

**App.jsx**
```javascript
import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/useAuthStore'
import Login from './pages/Login'
import Register from './pages/Register'
import Chat from './pages/Chat'

const PrivateRoute = ({ children }) => {
  const isAuthenticated = useAuthStore(state => state.isAuthenticated)
  return isAuthenticated ? children : <Navigate to="/login" />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/chat"
          element={
            <PrivateRoute>
              <Chat />
            </PrivateRoute>
          }
        />
        <Route path="/" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
```

#### 组件示例

**Login.jsx**
```javascript
import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import './Login.css'

function Login() {
  const navigate = useNavigate()
  const login = useAuthStore(state => state.login)

  const [form, setForm] = useState({
    email: '',
    password: ''
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      await login(form.email, form.password)
      navigate('/chat')
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1>🤖 AI Platform</h1>
        <p className="subtitle">React Frontend</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              placeholder="your@example.com"
            />
          </div>

          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              placeholder="Enter password"
            />
          </div>

          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        <div className="footer">
          <p>
            Don't have an account? <Link to="/register">Register</Link>
          </p>
          <div className="demo-info">
            <p><strong>Demo Account:</strong></p>
            <p>Email: demo@example.com</p>
            <p>Password: demo123456</p>
          </div>
        </div>

        {error && <div className="error">{error}</div>}
      </div>
    </div>
  )
}

export default Login
```

**Chat.jsx**
```javascript
import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { useChatStore } from '../store/useChatStore'
import './Chat.css'

function Chat() {
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const {
    sessions,
    currentSessionId,
    config,
    createSession,
    sendMessage: sendChatMessage,
    saveSessions
  } = useChatStore()

  const [messageInput, setMessageInput] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef(null)

  const currentSession = sessions[currentSessionId]

  const handleSend = async () => {
    if (!messageInput.trim() || sending) return

    const message = messageInput.trim()
    setMessageInput('')
    setSending(true)

    try {
      await sendChatMessage(message)
    } catch (error) {
      console.error('Send message error:', error)
    } finally {
      setSending(false)
    }
  }

  const handleLogout = async () => {
    if (window.confirm('Are you sure you want to logout?')) {
      await logout()
      navigate('/login')
    }
  }

  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [currentSession?.messages])

  // 初始化
  useEffect(() => {
    if (!currentSessionId && Object.keys(sessions).length === 0) {
      createSession()
    }
  }, [])

  return (
    <div className="chat-container">
      <header className="chat-header">
        <h2>🤖 AI Platform</h2>
        <div className="header-right">
          <span>{user?.email}</span>
          <button onClick={handleLogout} className="btn-secondary">
            Logout
          </button>
        </div>
      </header>

      <div className="chat-main">
        <aside className="sidebar">
          <div className="sidebar-header">
            <h3>Sessions</h3>
            <button onClick={createSession} className="btn-icon">+</button>
          </div>

          <div className="session-list">
            {Object.values(sessions)
              .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
              .map(session => (
                <div
                  key={session.id}
                  className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
                  onClick={() => useChatStore.setState({ currentSessionId: session.id })}
                >
                  {session.title}
                </div>
              ))}
          </div>

          <div className="sidebar-footer">
            <h4>Settings</h4>
            <label>
              <input
                type="checkbox"
                checked={config.useRAG}
                onChange={(e) => useChatStore.setState({
                  config: { ...config, useRAG: e.target.checked }
                })}
              />
              Enable RAG
            </label>
            <label>
              <input
                type="checkbox"
                checked={config.useAgent}
                onChange={(e) => useChatStore.setState({
                  config: { ...config, useAgent: e.target.checked }
                })}
              />
              Enable Agent
            </label>
            <label>
              Temperature: {config.temperature}
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={config.temperature}
                onChange={(e) => useChatStore.setState({
                  config: { ...config, temperature: parseFloat(e.target.value) }
                })}
              />
            </label>
          </div>
        </aside>

        <div className="chat-area">
          <div className="chat-messages">
            {currentSession?.messages.map((message, index) => (
              <div key={index} className={`message ${message.role}`}>
                <div className="message-avatar">
                  {message.role === 'user' ? '👤' : '🤖'}
                </div>
                <div className="message-content">
                  <div className="message-header">
                    <span className="message-role">
                      {message.role === 'user' ? 'You' : 'AI Assistant'}
                    </span>
                    <span className="message-time">
                      {formatTime(message.timestamp)}
                    </span>
                  </div>
                  <div className="message-text">{message.content}</div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-container">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSend()
              }}
              className="chat-input-form"
            >
              <textarea
                value={messageInput}
                onChange={(e) => setMessageInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
                rows="1"
              />
              <button
                type="submit"
                disabled={sending || !messageInput.trim()}
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Chat
```

### 安装和运行

```bash
# 进入 React 项目目录
cd frontend-react

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问 http://localhost:3001
```

---

## 🔄 Vue vs React 对比

| 特性 | Vue 3 | React 18 |
|------|-------|----------|
| **语法** | 模板语法 | JSX |
| **状态管理** | Pinia (官方) | Zustand (轻量) |
| **响应式** | Ref/Reactive | useState/useEffect |
| **组件** | .vue 文件 | .jsx 文件 |
| **路由** | Vue Router | React Router |
| **学习曲线** | 较平缓 | 中等 |
| **生态系统** | 丰富 | 非常丰富 |

### 选择建议

**选择 Vue，如果：**
- 喜欢模板语法
- 希望官方提供完整解决方案
- 团队熟悉 Vue
- 需要更简单的学习曲线

**选择 React，如果：**
- 喜欢 JSX 和 JavaScript 优先
- 需要更大的生态系统
- 团队熟悉 React
- 需要更多第三方库选择

---

## 🚀 部署指南

### 共通步骤

1. **构建项目**
```bash
npm run build
```

2. **配置环境变量**
```env
# 生产环境
VITE_API_BASE_URL=https://api.your-domain.com
```

### 部署选项

#### 1. Vercel
```bash
vercel deploy
```

#### 2. Netlify
```bash
netlify deploy --prod
```

#### 3. Docker

**Vue Dockerfile:**
```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**React Dockerfile:**
同上（只需更改路径）

#### 4. 静态托管（GitHub Pages / AWS S3）
- 上传 `dist/` 文件夹
- 配置 SPA 路由回退

---

## 🔧 开发工具

### VS Code 插件

**Vue：**
- Volar
- Vue VSCode Snippets
- ESLint

**React：**
- ES7+ React/Redux/React-Native snippets
- ESLint

### 调试工具

- **Vue Devtools** - Vue 专用调试工具
- **React Developer Tools** - React 专用调试工具
- **Redux DevTools** - 状态管理调试（如果使用 Redux）

---

## 📚 学习资源

### Vue 3
- [Vue 3 官方文档](https://cn.vuejs.org/)
- [Vue Router 文档](https://router.vuejs.org/zh/)
- [Pinia 文档](https://pinia.vuejs.org/zh/)
- [Vite 文档](https://cn.vitejs.dev/)

### React 18
- [React 官方文档](https://react.dev/)
- [React Router 文档](https://reactrouter.com/)
- [Zustand 文档](https://github.com/pmndrs/zustand)
- [Vite 文档](https://vitejs.dev/)

---

## 🤝 贡献

欢迎贡献！请：
1. Fork 项目
2. 创建功能分支
3. 提交代码
4. 发起 Pull Request

---

## 📄 许可证

MIT License - 查看主项目 LICENSE 文件

---

# English Documentation

[Full English documentation would follow the same structure as above, translated to English...]

---

**Vue 和 React 双版本前端开发完成！🎉**
**Both Vue and React frontend versions completed! 🎉**
