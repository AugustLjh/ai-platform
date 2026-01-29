import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import KnowledgeList from '../views/KnowledgeList.vue'
import KnowledgeCreate from '../views/KnowledgeCreate.vue'
import KnowledgeDetail from '../views/KnowledgeDetail.vue'
import KnowledgeEdit from '../views/KnowledgeEdit.vue'

const routes = [
  {
    path: '/',
    redirect: '/knowledge'
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
    name: 'KnowledgeList',
    component: KnowledgeList,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/create',
    name: 'KnowledgeCreate',
    component: KnowledgeCreate,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id',
    name: 'KnowledgeDetail',
    component: KnowledgeDetail,
    meta: { requiresAuth: true }
  },
  {
    path: '/knowledge/:id/edit',
    name: 'KnowledgeEdit',
    component: KnowledgeEdit,
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
    next('/knowledge')
  } else {
    next()
  }
})

export default router