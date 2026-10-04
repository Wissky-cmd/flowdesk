<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from './store'
import { roles } from './api'
const route = useRoute(), router = useRouter(), auth = useAuth()
const workspace = computed(() => auth.me?.workspaces.find(w => w.id === route.params.wid))
const error = ref('')
async function logout() { try { await auth.logout(); await router.push('/login') } catch (e) { error.value = (e as Error).message } }
</script>
<template>
  <RouterView v-if="route.path === '/login'" />
  <div v-else class="shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/"><span class="brand-mark">F</span>FlowDesk<span class="brand-dot">●</span></RouterLink>
      <div class="nav-caption">团队服务工作台</div>
      <RouterLink class="nav-link" to="/">▦ <span>工作空间</span></RouterLink>
      <template v-if="workspace">
        <div class="nav-caption space-caption">{{ workspace.name }}</div>
        <RouterLink class="nav-link" :to="`/w/${workspace.id}/tickets`">▤ <span>工单中心</span></RouterLink>
        <RouterLink v-if="workspace.role === 'admin'" class="nav-link" :to="`/w/${workspace.id}/members`">♧ <span>成员设置</span></RouterLink>
      </template>
      <div class="sidebar-foot"><span class="live-dot"></span>让每一个请求都有回应<div>FLOWDESK / WORK TOGETHER</div></div>
    </aside>
    <div class="main-area">
      <header class="topbar"><span>{{ workspace?.name || '我的工作空间' }} <span class="slash">/</span> 团队协作</span><div class="account"><span class="avatar">{{ auth.me?.name.slice(0, 1) }}</span><span>{{ auth.me?.name }}<small>{{ workspace ? roles[workspace.role] : '团队成员' }}</small></span><button class="text-button" @click="logout">退出</button></div></header>
      <main><el-alert v-if="error" :title="error" type="error" show-icon /><RouterView :key="route.fullPath" /></main>
    </div>
  </div>
</template>
