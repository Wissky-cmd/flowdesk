<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, date, priorities, statuses, type Ticket } from '../api'
const route = useRoute(), ticket = ref<Ticket | null>(null), error = ref(''), loading = ref(true)
onMounted(async () => { try { ticket.value = await api(`/workspaces/${route.params.wid}/tickets/${route.params.id}`) } catch (e) { error.value = (e as Error).message } finally { loading.value = false } })
</script>
<template><RouterLink class="back-link" :to="`/w/${route.params.wid}/tickets`">← 返回工单中心</RouterLink><div v-loading="loading" class="detail-wrap"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon /><template v-if="ticket"><div class="ticket-id detail-id">工单 #{{ ticket.id.slice(0, 8).toUpperCase() }}</div><div class="page-heading"><div><h1>{{ ticket.title }}</h1><p>创建于 {{ date(ticket.created_at) }}</p></div><span class="status-chip"><i></i>{{ statuses[ticket.status] }}</span></div><div class="editor-grid"><section class="panel description-panel"><h3>详细描述</h3><p class="ticket-body">{{ ticket.body }}</p></section><aside class="panel metadata"><h3>工单信息</h3><dl><dt>优先级</dt><dd :class="['priority', ticket.priority]">{{ priorities[ticket.priority] }}</dd><dt>状态</dt><dd>{{ statuses[ticket.status] }}</dd><dt>负责人</dt><dd>{{ ticket.assignee_id ? '已分派' : '暂未分派' }}</dd><dt>最近更新</dt><dd>{{ date(ticket.updated_at) }}</dd><dt>版本</dt><dd>v{{ ticket.version }}</dd></dl></aside></div></template></div></template>
