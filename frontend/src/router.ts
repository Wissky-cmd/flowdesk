import { createRouter, createWebHistory } from 'vue-router'
import Login from './views/Login.vue'
import Workspaces from './views/Workspaces.vue'
import Tickets from './views/Tickets.vue'
import CreateTicket from './views/CreateTicket.vue'
import TicketDetail from './views/TicketDetail.vue'
import Members from './views/Members.vue'
import { useAuth } from './store'
import { ApiError } from './api'

export const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: Login }, { path: '/', component: Workspaces },
  { path: '/w/:wid/tickets', component: Tickets },
  { path: '/w/:wid/tickets/new', component: CreateTicket },
  { path: '/w/:wid/tickets/:id', component: TicketDetail },
  { path: '/w/:wid/members', component: Members },
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
