import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './store'
import { ApiError } from './api'

export const router = createRouter({ history: createWebHistory(), scrollBehavior: () => ({ top: 0 }), routes: [
  { path: '/login', component: () => import('./views/Login.vue') }, { path: '/', component: () => import('./views/Workspaces.vue') },
  { path: '/w/:wid/tickets', component: () => import('./views/Tickets.vue') },
  { path: '/w/:wid/board', component: () => import('./views/Board.vue') },
  { path: '/w/:wid/jobs', component: () => import('./views/Jobs.vue') },
  { path: '/w/:wid/integrations', component: () => import('./views/Integrations.vue') },
  { path: '/w/:wid/tickets/new', component: () => import('./views/CreateTicket.vue') },
  { path: '/w/:wid/tickets/:id', component: () => import('./views/TicketDetail.vue') },
  { path: '/w/:wid/members', component: () => import('./views/Members.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.beforeEach(async to => {
  const auth = useAuth()
  if (to.path === '/login') return
  if (!auth.me) {
    try { await auth.load() } catch (e) {
      if (e instanceof ApiError && e.status === 401) return { path: '/login', query: { next: to.fullPath } }
      return { path: '/login', query: { error: '服务连接失败，请稍后重试' } }
    }
  }
})
