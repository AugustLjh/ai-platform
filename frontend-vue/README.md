# AI Platform - Vue 3 Frontend

<div align="center">

![Vue](https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vue.js)
![Vite](https://img.shields.io/badge/Vite-5.0-646CFF?logo=vite)
![Pinia](https://img.shields.io/badge/Pinia-2.1-FFD859)

**Modern, responsive Vue 3 frontend for AI Platform**

[English](./README.md) | [中文](./README_CN.md)

</div>

---

## ✨ Features

- 🎨 **Modern UI** - Clean and intuitive interface
- 📱 **Responsive Design** - Works on all devices
- ⚡ **Vite** - Lightning fast HMR
- 🔐 **Authentication** - JWT-based auth with auto-refresh
- 💬 **Real-time Chat** - SSE streaming responses
- 🎯 **State Management** - Pinia for reactive state
- 🚀 **Vue Router** - SPA navigation
- 📦 **Component-based** - Reusable Vue components

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- npm or yarn or pnpm

### Installation

```bash
# Install dependencies
npm install
# or
yarn install
# or
pnpm install
```

### Development

```bash
# Start dev server
npm run dev

# Access at http://localhost:3000
```

### Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## 📁 Project Structure

```
frontend-vue/
├── public/                 # Static assets
├── src/
│   ├── api/               # API services
│   │   ├── axios.js      # Axios configuration
│   │   └── index.js      # API endpoints
│   ├── assets/           # Assets (styles, images)
│   │   └── styles/       # Global styles
│   ├── components/       # Reusable components
│   │   ├── ChatMessage.vue
│   │   ├── ChatInput.vue
│   │   └── SessionList.vue
│   ├── views/            # Page components
│   │   ├── Login.vue
│   │   ├── Register.vue
│   │   └── Chat.vue
│   ├── router/           # Vue Router
│   │   └── index.js
│   ├── store/            # Pinia stores
│   │   ├── auth.js
│   │   └── chat.js
│   ├── utils/            # Utility functions
│   ├── App.vue           # Root component
│   └── main.js           # Entry point
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

## 🔧 Configuration

### Environment Variables

Create `.env` file in the root:

```env
VITE_API_BASE_URL=http://localhost:8080
```

For production:

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

### Vite Config

Edit `vite.config.js` to customize:

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

## 📚 Key Components

### Authentication

Located in `src/views/`:
- `Login.vue` - User login page
- `Register.vue` - User registration page

**Store**: `src/store/auth.js`

```javascript
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()

// Login
await authStore.login(email, password)

// Logout
await authStore.logout()

// Get current user
await authStore.getCurrentUser()
```

### Chat Interface

Located in `src/views/Chat.vue`

**Store**: `src/store/chat.js`

```javascript
import { useChatStore } from '@/store/chat'

const chatStore = useChatStore()

// Create new session
chatStore.createSession()

// Send message
await chatStore.sendMessage('Hello!')

// Access current session
const session = chatStore.currentSession
```

### Components

**ChatMessage.vue** - Message bubble component
```vue
<ChatMessage
  :message="message"
  :is-user="message.role === 'user'"
/>
```

**ChatInput.vue** - Message input with controls
```vue
<ChatInput
  @send="handleSend"
  :loading="isLoading"
/>
```

**SessionList.vue** - Session sidebar
```vue
<SessionList
  :sessions="sessions"
  :current-id="currentId"
  @select="handleSelect"
/>
```

## 🎨 Styling

### Global Styles

Located in `src/assets/styles/`:
- `main.css` - Global styles and CSS variables
- `variables.css` - CSS custom properties

### CSS Variables

```css
:root {
  --primary-color: #4F46E5;
  --success-color: #10B981;
  --error-color: #EF4444;
  --bg-color: #F9FAFB;
  /* ... more variables */
}
```

### Scoped Styles

Each component uses scoped styles:

```vue
<style scoped>
.my-component {
  /* Component-specific styles */
}
</style>
```

## 🔌 API Integration

### axios.js

Configured axios instance with:
- Request/response interceptors
- Auto token refresh
- Error handling

### API Services

**authAPI** - Authentication endpoints
```javascript
import { authAPI } from '@/api'

// Register
await authAPI.register(email, password)

// Login
await authAPI.login(email, password)

// Logout
await authAPI.logout()
```

**chatAPI** - Chat endpoints
```javascript
import { chatAPI } from '@/api'

// Send message (sync)
await chatAPI.sendMessage(sessionId, message, config)

// Send message with SSE (streaming)
await chatAPI.sendMessageSSE(sessionId, message, config, onChunk)
```

## 🛡️ Authentication Flow

1. User logs in → JWT tokens stored in localStorage
2. Axios interceptor adds token to requests
3. On 401 response → Auto refresh token
4. On refresh failure → Redirect to login

```javascript
// Automatic token refresh in axios.js
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      // Try to refresh token
      const refreshed = await refreshToken()
      if (refreshed) {
        // Retry original request
        return api.request(error.config)
      }
    }
    return Promise.reject(error)
  }
)
```

## 🚦 Routing

### Route Configuration

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

### Navigation Guards

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

## 📱 Responsive Design

### Breakpoints

- **Desktop**: > 768px
- **Tablet**: 768px
- **Mobile**: < 768px

### Media Queries

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

## 🚀 Deployment

### Build for Production

```bash
npm run build
```

Output in `dist/` directory.

### Deploy Options

**Vercel:**
```bash
vercel deploy
```

**Netlify:**
```bash
netlify deploy --prod
```

**Docker:**
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

**Static Hosting:**
- Upload `dist/` folder to any static host
- Configure SPA fallback (all routes → index.html)

## 🔧 Development Tips

### Hot Module Replacement

Vite provides instant HMR:
```javascript
if (import.meta.hot) {
  import.meta.hot.accept()
}
```

### Vue Devtools

Install [Vue Devtools](https://devtools.vuejs.org/) for debugging:
- Component inspector
- Pinia state viewer
- Router navigation
- Performance tracking

### Code Splitting

Lazy load routes for better performance:
```javascript
const Chat = () => import('@/views/Chat.vue')
```

## 🐛 Troubleshooting

### CORS Errors

Ensure backend allows your origin:
```go
// Go backend
r.Use(cors.Handler(cors.Options{
    AllowedOrigins: []string{"http://localhost:3000"},
}))
```

Or use Vite proxy in `vite.config.js`.

### Build Errors

Clear cache and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

### SSE Connection Issues

Check:
1. Backend supports SSE
2. Correct Content-Type header
3. Token is valid
4. No proxy blocking EventSource

## 📖 Learn More

- [Vue 3 Documentation](https://vuejs.org/)
- [Vite Documentation](https://vitejs.dev/)
- [Pinia Documentation](https://pinia.vuejs.org/)
- [Vue Router Documentation](https://router.vuejs.org/)

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📄 License

MIT License - See main project LICENSE file

---

**Built with ❤️ using Vue 3**
