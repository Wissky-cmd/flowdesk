<script setup lang="ts">
import { useAuth } from '../store'
import { roles } from '../api'
const auth = useAuth()
</script>
<template><div class="eyebrow">YOUR WORK, CONNECTED</div><div class="page-heading"><div><h1>你好，{{ auth.me?.name }}<span class="greeting-dot">。</span></h1><p>选择一个工作空间，开始今天的协作。</p></div><span class="count-badge">{{ auth.me?.workspaces.length }} 个工作空间</span></div>
  <div class="workspace-grid"><RouterLink v-for="(w, i) in auth.me?.workspaces" :key="w.id" :to="`/w/${w.id}/tickets`" class="workspace-card"><div class="workspace-icon">{{ String(i + 1).padStart(2, '0') }}</div><span class="role-chip">{{ roles[w.role] }}</span><h2>{{ w.name }}</h2><p>查看请求、提交工单，与团队保持同步。</p><div class="card-bottom">进入工作空间 <span>↗</span></div></RouterLink></div>
  <el-empty v-if="!auth.me?.workspaces.length" description="暂未加入工作空间，请联系管理员" />
  <div class="info-strip"><span>◎</span><div><strong>专注当下，让协作更清晰</strong><p>各空间的数据独立管理，你可以随时返回这里切换空间。</p></div></div>
</template>
