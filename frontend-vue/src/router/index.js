import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import Chat from '../views/Chat.vue'
import KnowledgeBaseList from '../views/KnowledgeBaseList.vue'
import KnowledgeBaseCreate from '../views/KnowledgeBaseCreate.vue'
import KnowledgeBaseDetail from '../views/KnowledgeBaseDetail.vue'
import KnowledgeBaseEdit from '../views/KnowledgeBaseEdit.vue'

const routes = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/chat',
    name: 'Chat',
    component: Chat,
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: Login
  },
  {
    path: '/register',
    name: 'Register',
    component: Register
  },
  {
    path: '/knowledge',
    name: 'KnowledgeBaseList',
    component: KnowledgeBaseList,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/create',
    name: 'KnowledgeBaseCreate',
    component: KnowledgeBaseCreate,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id',
    name: 'KnowledgeBaseDetail',
    component: KnowledgeBaseDetail,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id/edit',
    name: 'KnowledgeBaseEdit',
    component: KnowledgeBaseEdit,
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard for authentication
router.beforeEach((to, from, next) => {
  const isAuthenticated = !!localStorage.getItem('access_token')

  if (to.meta.requiresAuth && !isAuthenticated) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && isAuthenticated) {
    next('/chat')
  } else {
    next()
  }
})

export default router