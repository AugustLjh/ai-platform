import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import Chat from '../views/Chat.vue'
import History from '../views/History.vue'
import ModelsManage from '../views/ModelsManage.vue'
import Profile from '../views/Profile.vue'
import Settings from '../views/Settings.vue'
import AgentPlaceholder from '../views/AgentPlaceholder.vue'
import KnowledgeBaseList from '../views/KnowledgeBaseList.vue'
import KnowledgeBaseCreate from '../views/KnowledgeBaseCreate.vue'
import KnowledgeBaseDetail from '../views/KnowledgeBaseDetail.vue'
import KnowledgeBaseEdit from '../views/KnowledgeBaseEdit.vue'
import KnowledgeBaseSettings from '../views/KnowledgeBaseSettings.vue'
import KnowledgeBaseRetrievalTest from '../views/KnowledgeBaseRetrievalTest.vue'

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
    path: '/history',
    name: 'History',
    component: History,
    meta: { requiresAuth: true }
  },
  {
    path: '/models',
    name: 'ModelsManage',
    component: ModelsManage,
    meta: { requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: Profile,
    meta: { requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings,
    meta: { requiresAuth: true }
  },
  {
    path: '/agents/:agent',
    name: 'AgentPlaceholder',
    component: AgentPlaceholder,
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
  },
  {
    path: '/knowledge/:id/settings',
    name: 'KnowledgeBaseSettings',
    component: KnowledgeBaseSettings,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id/retrieval-test',
    name: 'KnowledgeBaseRetrievalTest',
    component: KnowledgeBaseRetrievalTest,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id/indexing',
    redirect: (to) => `/knowledge/${to.params.id}/settings`
  },
  {
    path: '/knowledge/:id/retrieval',
    redirect: (to) => `/knowledge/${to.params.id}/settings`
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
