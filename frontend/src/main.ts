import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElAlert, ElButton, ElConfigProvider, ElDialog, ElEmpty, ElInput, ElLoading, ElOption, ElPagination, ElSelect, ElSwitch } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/switch/style/css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { useAuth } from './store'

const app = createApp(App)
app.use(createPinia()).use(router)
for (const component of [ElAlert, ElButton, ElConfigProvider, ElDialog, ElEmpty, ElInput, ElLoading, ElOption, ElPagination, ElSelect, ElSwitch]) app.use(component)
app.mount('#app')
window.addEventListener('session-expired', () => {
  useAuth().clear()
  void router.replace({ path: '/login', query: { expired: '1', next: router.currentRoute.value.fullPath } })
})
