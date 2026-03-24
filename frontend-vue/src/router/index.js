import { createRouter, createWebHistory } from 'vue-router'

const Login = () => import('../views/Login.vue')
const Register = () => import('../views/Register.vue')
const Chat = () => import('../views/Chat.vue')
const History = () => import('../views/History.vue')
const CostStats = () => import('../views/CostStats.vue')
const ModelsManage = () => import('../views/ModelsManage.vue')
const Profile = () => import('../views/Profile.vue')
const Settings = () => import('../views/Settings.vue')
const AgentsList = () => import('../views/AgentsList.vue')
const AgentWorkspace = () => import('../views/AgentWorkspace.vue')
const AgentRunDetail = () => import('../views/AgentRunDetail.vue')
const KnowledgeBaseList = () => import('../views/KnowledgeBaseList.vue')
const KnowledgeBaseCreate = () => import('../views/KnowledgeBaseCreate.vue')
const KnowledgeBaseDetail = () => import('../views/KnowledgeBaseDetail.vue')
const KnowledgeBaseEdit = () => import('../views/KnowledgeBaseEdit.vue')
const KnowledgeBaseSettings = () => import('../views/KnowledgeBaseSettings.vue')
const KnowledgeBaseRetrievalTest = () => import('../views/KnowledgeBaseRetrievalTest.vue')

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
    path: '/costs',
    name: 'CostStats',
    component: CostStats,
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
    path: '/agents',
    name: 'AgentsList',
    component: AgentsList,
    meta: { requiresAuth: true }
  },
  {
    path: '/agents/runs/:run_id',
    name: 'AgentRunDetail',
    component: AgentRunDetail,
    meta: { requiresAuth: true }
  },
  {
    path: '/agents/:id',
    name: 'AgentWorkspace',
    component: AgentWorkspace,
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
