<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './store'
import { roles } from './api'
import Icon from './components/Icon.vue'
import { watch } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
const route = useRoute(), router = useRouter(), auth = useAuth()
const workspace = computed(() => auth.me?.workspaces.find(w => w.id === route.params.wid))
const error = ref('')
const menuOpen = ref(false), helpOpen = ref(false)
const initialOverflow = document.body.style.overflow
watch(menuOpen, open => { document.body.style.overflow = open ? 'hidden' : initialOverflow })
onBeforeUnmount(() => { if (menuOpen.value) document.body.style.overflow = initialOverflow })
const menuToggle = ref<HTMLButtonElement | null>(null), navigation = ref<HTMLElement | null>(null)
function handleNavigationKey(event: KeyboardEvent) {
  if (!menuOpen.value) return
  if (event.key === 'Escape') { menuOpen.value = false; menuToggle.value?.focus(); return }
  if (event.key !== 'Tab') return
  const controls = [menuToggle.value, ...Array.from(navigation.value?.querySelectorAll<HTMLElement>('a, button') || [])].filter((node): node is HTMLElement => !!node && node.getClientRects().length > 0)
  const first = controls[0], last = controls[controls.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const desktopQuery = window.matchMedia('(min-width: 701px)')
const closeMobileMenu = () => { if (desktopQuery.matches) menuOpen.value = false }
desktopQuery.addEventListener('change', closeMobileMenu)
onBeforeUnmount(() => desktopQuery.removeEventListener('change', closeMobileMenu))
const today = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
watch(() => route.fullPath, () => { menuOpen.value = false })
async function logout() { try { await auth.logout(); await router.push('/login') } catch (e) { error.value = (e as Error).message } }
</script>
<template>
  <el-config-provider :locale="zhCn">
  <RouterView v-if="route.path === '/login'" />
  <div v-else class="shell" @keydown="handleNavigationKey">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <div class="mobile-bar"><RouterLink class="brand" to="/" :tabindex="menuOpen ? -1 : undefined"><span class="brand-mark">f.</span>FlowDesk</RouterLink><button ref="menuToggle" class="icon-button" :aria-expanded="menuOpen" aria-controls="main-nav" :aria-label="menuOpen ? '关闭导航' : '打开导航'" @click="menuOpen = !menuOpen"><Icon :name="menuOpen ? 'close' : 'menu'" /></button></div>
    <button v-if="menuOpen" class="nav-scrim" aria-label="关闭导航" tabindex="-1" @click="menuOpen = false" />
    <aside ref="navigation" id="main-nav" :class="['sidebar', { 'is-open': menuOpen }]">
      <RouterLink class="brand" to="/" aria-label="FlowDesk 首页"><span class="brand-mark">f.</span>FlowDesk<span class="brand-dot"></span></RouterLink>
      <div class="nav-caption">让协作，自然发生。</div>
      <div class="nav-section-label">工作台 <span>WORKSPACE</span></div>
      <nav aria-label="主导航"><RouterLink class="nav-link" to="/"><Icon name="grid" /><span>工作空间</span><span class="nav-number">01</span></RouterLink>
      <template v-if="workspace">
        <RouterLink :class="['nav-link', { 'section-active': route.path.includes('/tickets') }]" :to="`/w/${workspace.id}/tickets`"><Icon name="ticket" /><span>工单中心</span><span class="nav-number">02</span></RouterLink>
        <RouterLink class="nav-link" :to="`/w/${workspace.id}/board`"><Icon name="grid" /><span>协作看板</span><span class="nav-number">03</span></RouterLink>
        <RouterLink class="nav-link" :to="`/w/${workspace.id}/jobs`"><Icon name="clock" /><span>任务中心</span><span class="nav-number">04</span></RouterLink>
        <RouterLink class="nav-link" :to="`/w/${workspace.id}/integrations`"><Icon name="shield" /><span>集成授权</span><span class="nav-number">05</span></RouterLink>
        <RouterLink v-if="workspace.role === 'admin'" class="nav-link" :to="`/w/${workspace.id}/members`"><Icon name="people" /><span>成员设置</span><span class="nav-number">06</span></RouterLink>
      </template>
      </nav>
      <div v-if="workspace" class="workspace-note"><span class="workspace-note-label">当前空间</span><span class="workspace-mini-icon">{{ workspace.name.slice(0, 1) }}</span><strong>{{ workspace.name }}</strong><span>{{ roles[workspace.role] }}权限</span><RouterLink to="/" aria-label="切换工作空间"><Icon name="diagonal" :size="17" /></RouterLink></div>
      <div class="sidebar-foot"><div class="sidebar-manifesto">Make room<br/>for <em>good work.</em><span class="manifesto-star">✳</span></div><button class="help-button" @click="menuOpen = false; helpOpen = true"><Icon name="help" :size="17" />使用指南<Icon name="diagonal" :size="16" /></button><div class="sidebar-edition">FLOWDESK <span>TEAM SERVICE / 01</span></div></div>
    </aside>
    <div class="main-area" :inert="menuOpen">
      <header class="topbar"><div class="breadcrumb"><span class="breadcrumb-dot"></span>{{ workspace?.name || '我的工作空间' }}<span class="slash">/</span><span class="breadcrumb-secondary">团队协作</span></div><div class="topbar-right"><span class="today">{{ today }}</span><div class="account"><span class="avatar">{{ auth.me?.name.slice(0, 1) }}</span><span class="account-name">{{ auth.me?.name }}<small>{{ workspace ? roles[workspace.role] : '团队成员' }}</small></span><button class="icon-button logout-button" aria-label="退出" title="退出登录" @click="logout"><Icon name="logout" :size="17" /></button></div></div></header>
      <main id="main-content" tabindex="-1"><el-alert v-if="error" :title="error" type="error" show-icon /><RouterView v-slot="{ Component }"><Transition name="page" mode="out-in"><div :key="route.fullPath" class="page-content"><component :is="Component" /></div></Transition></RouterView><footer class="page-footer"><span>少一点繁杂，多一点流畅。</span><span>DESIGNED FOR THE WAY YOU WORK <span class="footer-star">✳</span></span></footer></main>
    </div>
    <el-dialog v-model="helpOpen" title="从一个请求，开始协作" width="min(520px, calc(100vw - 32px))" class="guide-dialog"><ol class="guide-steps"><li><strong>选择你的空间</strong><p>每个空间独立管理成员与工单，只显示你有权访问的内容。</p></li><li><strong>清晰描述一个请求</strong><p>填写标题与背景，按影响范围选择优先级，再提交给团队。</p></li><li><strong>随时回到工单中心</strong><p>筛选全部可见工单、推进处理、补充评论与附件；在任务中心导出结果，在集成授权中管理应用访问。</p></li></ol><template #footer><el-button type="primary" @click="helpOpen = false">开始协作 <Icon name="arrow" :size="16" /></el-button></template></el-dialog>
  </div>
  </el-config-provider>
</template>
