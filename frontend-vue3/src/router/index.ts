import { createRouter, createWebHistory } from 'vue-router'

import { useAuthState } from '../composables/useAuthState'
import AuthPage from '../views/AuthPage.vue'
import SessionWorkspacePage from '../views/SessionWorkspacePage.vue'
import SessionsPage from '../views/SessionsPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/sessions',
    },
    {
      path: '/auth',
      component: AuthPage,
      meta: { requiresGuest: true },
    },
    {
      path: '/sessions',
      component: SessionsPage,
      meta: { requiresAuth: true },
    },
    {
      path: '/sessions/:sessionId',
      component: SessionWorkspacePage,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthState()
  await auth.initializeAuth()

  if (to.meta.requiresAuth && !auth.isAuthenticated.value) {
    return '/auth'
  }

  if (to.meta.requiresGuest && auth.isAuthenticated.value) {
    return '/sessions'
  }

  return true
})

export default router
