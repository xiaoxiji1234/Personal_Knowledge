import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './composables/useAuth'
import MainLayout from './layouts/MainLayout.vue'
import CategoryManagePage from './pages/CategoryManagePage.vue'
import KnowledgeManagePage from './pages/KnowledgeManagePage.vue'
import KnowledgeQaPage from './pages/KnowledgeQaPage.vue'
import LoginPage from './pages/LoginPage.vue'
import RegisterPage from './pages/RegisterPage.vue'

/**
 * Define application routes so each primary page lives in its own file.
 */
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginPage,
      meta: { title: '登录', guestOnly: true },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterPage,
      meta: { title: '注册', guestOnly: true },
    },
    {
      path: '/',
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: { name: 'qa' },
        },
        {
          path: 'qa',
          name: 'qa',
          component: KnowledgeQaPage,
          meta: { title: '知识库问答' },
        },
        {
          path: 'manage',
          name: 'manage',
          component: KnowledgeManagePage,
          meta: { title: '知识库管理' },
        },
        {
          path: 'categories',
          name: 'category-manage',
          component: CategoryManagePage,
          meta: { title: '分类管理' },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const { ensureAuthReady, isAuthenticated } = useAuth()
  await ensureAuthReady()

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return { name: 'login' }
  }

  if (to.meta.guestOnly && isAuthenticated.value) {
    return { name: 'qa' }
  }

  return true
})
