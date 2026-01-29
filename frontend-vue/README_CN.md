# AI Platform - Vue 3 前端

<div align="center">

![Vue](https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vue.js)
![Vite](https://img.shields.io/badge/Vite-5.0-646CFF?logo=vite)
![Pinia](https://img.shields.io/badge/Pinia-2.1-FFD859)

**AI Platform 的现代化、响应式 Vue 3 前端**

[English](./README.md) | [中文](./README_CN.md)

</div>

---

## ✨ 功能特性

- 🎨 **现代化 UI** - 简洁直观的界面
- 📱 **响应式设计** - 适配所有设备
- ⚡ **Vite** - 闪电般的热更新
- 🔐 **身份认证** - 基于 JWT 的认证，支持自动刷新
- 💬 **实时聊天** - SSE 流式响应
- 🎯 **状态管理** - 使用 Pinia 管理响应式状态
- 🚀 **Vue Router** - 单页应用路由
- 📦 **组件化** - 可复用的 Vue 组件

## 🚀 快速开始

### 前置要求

- Node.js 18+
- npm 或 yarn 或 pnpm

### 安装

```bash
# 安装依赖
npm install
# 或
yarn install
# 或
pnpm install
```

### 开发

```bash
# 启动开发服务器
npm run dev

# 访问 http://localhost:3000
```

### 构建

```bash
# 生产构建
npm run build

# 预览生产构建
npm run preview
```

## 📁 项目结构

```
frontend-vue/
├── public/                 # 静态资源
├── src/
│   ├── api/               # API 服务
│   │   ├── axios.js      # Axios 配置
│   │   └── index.js      # API 端点
│   ├── assets/           # 资源文件（样式、图片）
│   │   └── styles/       # 全局样式
│   ├── components/       # 可复用组件
│   │   ├── ChatMessage.vue
│   │   ├── ChatInput.vue
│   │   └── SessionList.vue
│   ├── views/            # 页面组件
│   │   ├── Login.vue
│   │   ├── Register.vue
│   │   └── Chat.vue
│   ├── router/           # Vue Router
│   │   └── index.js
│   ├── store/            # Pinia 状态管理
│   │   ├── auth.js
│   │   └── chat.js
│   ├── utils/            # 工具函数
│   ├── App.vue           # 根组件
│   └── main.js           # 入口文件
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

## 🔧 配置

### 环境变量

在根目录创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8080
```

生产环境：

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

### Vite 配置

编辑 `vite.config.js` 自定义配置：

```javascript
export default defineConfig({
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true
      }
    }
  }
})
```

## 📚 核心组件

### 身份认证

位于 `src/views/`：
- `Login.vue` - 用户登录页面
- `Register.vue` - 用户注册页面

**Store**：`src/store/auth.js`

```javascript
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()

// 登录
await authStore.login(email, password)

// 登出
await authStore.logout()

// 获取当前用户
await authStore.getCurrentUser()
```

### 聊天界面

位于 `src/views/Chat.vue`

**Store**：`src/store/chat.js`

```javascript
import { useChatStore } from '@/store/chat'

const chatStore = useChatStore()

// 创建新会话
chatStore.createSession()

// 发送消息
await chatStore.sendMessage('你好！')

// 访问当前会话
const session = chatStore.currentSession
```

### 组件

**ChatMessage.vue** - 消息气泡组件
```vue
<ChatMessage
  :message="message"
  :is-user="message.role === 'user'"
/>
```

**ChatInput.vue** - 带控制的消息输入框
```vue
<ChatInput
  @send="handleSend"
  :loading="isLoading"
/>
```

**SessionList.vue** - 会话侧边栏
```vue
<SessionList
  :sessions="sessions"
  :current-id="currentId"
  @select="handleSelect"
/>
```

## 🎨 样式

### 全局样式

位于 `src/assets/styles/`：
- `main.css` - 全局样式和 CSS 变量
- `variables.css` - CSS 自定义属性

### CSS 变量

```css
:root {
  --primary-color: #4F46E5;
  --success-color: #10B981;
  --error-color: #EF4444;
  --bg-color: #F9FAFB;
  /* ... 更多变量 */
}
```

### 局部样式

每个组件使用局部样式：

```vue
<style scoped>
.my-component {
  /* 组件特定样式 */
}
</style>
```

## 🔌 API 集成

### axios.js

配置的 axios 实例包含：
- 请求/响应拦截器
- 自动刷新 Token
- 错误处理

### API 服务

**authAPI** - 认证端点
```javascript
import { authAPI } from '@/api'

// 注册
await authAPI.register(email, password)

// 登录
await authAPI.login(email, password)

// 登出
await authAPI.logout()
```

**chatAPI** - 聊天端点
```javascript
import { chatAPI } from '@/api'

// 发送消息（同步）
await chatAPI.sendMessage(sessionId, message, config)

// 发送消息（SSE 流式）
await chatAPI.sendMessageSSE(sessionId, message, config, onChunk)
```

## 🛡️ 认证流程

1. 用户登录 → JWT tokens 存储在 localStorage
2. Axios 拦截器将 token 添加到请求
3. 收到 401 响应 → 自动刷新 token
4. 刷新失败 → 重定向到登录页

```javascript
// axios.js 中的自动 token 刷新
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // 尝试刷新 token
      const refreshed = await refreshToken()
      if (refreshed) {
        // 重试原始请求
        return api.request(error.config)
      }
    }
    return Promise.reject(error)
  }
)
```

## 🚦 路由

### 路由配置

```javascript
const routes = [
  {
    path: '/login',
    component: () => import('@/views/Login.vue')
  },
  {
    path: '/register',
    component: () => import('@/views/Register.vue')
  },
  {
    path: '/chat',
    component: () => import('@/views/Chat.vue'),
    meta: { requiresAuth: true }
  }
]
```

### 导航守卫

```javascript
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else {
    next()
  }
})
```

## 📱 响应式设计

### 断点

- **桌面端**：> 768px
- **平板端**：768px
- **移动端**：< 768px

### 媒体查询

```css
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: -280px;
    transition: left 0.3s;
  }

  .sidebar.show {
    left: 0;
  }
}
```

## 🚀 部署

### 生产构建

```bash
npm run build
```

输出到 `dist/` 目录。

### 部署选项

**Vercel：**
```bash
vercel deploy
```

**Netlify：**
```bash
netlify deploy --prod
```

**Docker：**
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

**静态托管：**
- 上传 `dist/` 文件夹到任何静态托管服务
- 配置 SPA 回退（所有路由 → index.html）

## 🔧 开发技巧

### 热模块替换

Vite 提供即时 HMR：
```javascript
if (import.meta.hot) {
  import.meta.hot.accept()
}
```

### Vue Devtools

安装 [Vue Devtools](https://devtools.vuejs.org/) 进行调试：
- 组件检查器
- Pinia 状态查看器
- 路由导航
- 性能追踪

### 代码分割

懒加载路由以提高性能：
```javascript
const Chat = () => import('@/views/Chat.vue')
```

## 🐛 故障排查

### CORS 错误

确保后端允许你的源：
```go
// Go 后端
r.Use(cors.Handler(cors.Options{
    AllowedOrigins: []string{"http://localhost:3000"},
}))
```

或在 `vite.config.js` 中使用 Vite 代理。

### 构建错误

清除缓存并重新安装：
```bash
rm -rf node_modules package-lock.json
npm install
```

### SSE 连接问题

检查：
1. 后端支持 SSE
2. 正确的 Content-Type 头
3. Token 有效
4. 没有代理阻止 EventSource

## 📖 了解更多

- [Vue 3 文档](https://cn.vuejs.org/)
- [Vite 文档](https://cn.vitejs.dev/)
- [Pinia 文档](https://pinia.vuejs.org/zh/)
- [Vue Router 文档](https://router.vuejs.org/zh/)

## 🤝 贡献

欢迎贡献！请：
1. Fork 仓库
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 打开 Pull Request

## 📄 许可证

MIT License - 查看主项目 LICENSE 文件

---

**使用 Vue 3 精心打造 ❤️**
