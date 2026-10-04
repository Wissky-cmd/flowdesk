import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { useAuth } from './store'

const app = createApp(App)
app.use(createPinia()).use(router).use(ElementPlus).mount('#app')
window.addEventListener('session-expired', () => {
  useAuth().clear()
  void router.replace({ path: '/login', query: { expired: '1', next: router.currentRoute.value.fullPath } })
})
