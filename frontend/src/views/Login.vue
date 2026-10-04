<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../store'
import FlowArt from '../components/FlowArt.vue'
const email = ref(''), password = ref(''), busy = ref(false), error = ref('')
const auth = useAuth(), route = useRoute(), router = useRouter()
async function submit() {
  error.value = ''; busy.value = true
  try {
    await auth.login(email.value, password.value)
    const next = String(route.query.next || '/')
    await router.push(next.startsWith('/') && !next.startsWith('//') ? next : '/')
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template>
  <div class="login-page">
    <section class="login-story"><div class="brand"><span class="brand-mark">f.</span>FlowDesk</div><div><div class="eyebrow"><span class="eyebrow-line"></span>A LITTLE MORE FLOW.</div><h1>从一个请求，<br/>到一次<em>更好的协作。</em></h1><p>把需求、问题与服务连接起来。<br/>清晰记录，安心交付。</p><div class="story-card"><span class="live-dot"></span>每件事，都有它的下一步。</div></div><div class="login-art"><FlowArt /></div><small>FLOWDESK / 团队服务工作台</small></section>
    <section class="login-form"><div class="form-inner"><div class="eyebrow">WELCOME BACK</div><h2>登录工作台</h2><p class="muted">与你的团队一起，把事情向前推进。</p>
      <el-alert v-if="route.query.expired" title="会话已过期，请重新登录" type="warning" :closable="false" />
      <el-alert v-if="error || route.query.error" :title="error || String(route.query.error)" type="error" :closable="false" show-icon />
      <form @submit.prevent="submit"><label for="email">邮箱</label><el-input id="email" v-model="email" type="email" autocomplete="username" placeholder="请输入工作邮箱" size="large" required />
      <label for="password">密码</label><el-input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" size="large" show-password required />
      <el-button class="login-submit" type="primary" size="large" native-type="submit" :loading="busy">登录 FlowDesk →</el-button></form>
      <div class="login-note">账户由团队管理员提供。<br/>登录后仅可访问已加入的工作空间。</div></div></section>
  </div>
</template>
