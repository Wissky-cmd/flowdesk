<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, date, priorities, statuses, type Ticket } from '../api'
const route = useRoute(), router = useRouter(), wid = String(route.params.wid)
const rows = ref<Ticket[]>([]), total = ref(0), page = ref(1), loading = ref(true), error = ref('')
async function load() {
  loading.value = true; error.value = ''
  try { const data = await api<{items: Ticket[]; total: number}>(`/workspaces/${wid}/tickets?page=${page.value}`); rows.value = data.items; total.value = data.total }
  catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
onMounted(load)
</script>
<template><div class="eyebrow">WORKSPACE / TICKETS</div><div class="page-heading"><div><h1>工单中心<span class="greeting-dot">。</span></h1><p>记录每个请求，让进展有迹可循。</p></div><el-button type="primary" size="large" @click="router.push(`/w/${wid}/tickets/new`)">＋ 创建工单</el-button></div>
  <section class="panel"><div class="panel-heading"><div><strong>全部可见工单</strong><span class="pill">{{ total }}</span></div><button class="text-button" @click="load">↻ 刷新列表</button></div>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
  <el-table v-loading="loading" :data="rows" empty-text="还没有工单，创建第一条请求吧" @row-click="(row: Ticket) => router.push(`/w/${wid}/tickets/${row.id}`)" class="ticket-table">
    <el-table-column label="工单" min-width="320"><template #default="{row}"><RouterLink class="ticket-title" :to="`/w/${wid}/tickets/${row.id}`">{{ row.title }}</RouterLink><div class="ticket-id">#{{ row.id.slice(0, 8).toUpperCase() }}</div></template></el-table-column>
    <el-table-column label="状态" width="120"><template #default="{row}"><span class="status-chip"><i></i>{{ statuses[row.status] }}</span></template></el-table-column>
    <el-table-column label="优先级" width="110"><template #default="{row}"><span :class="['priority', row.priority]">{{ priorities[row.priority] }}</span></template></el-table-column>
    <el-table-column label="最近更新" width="155"><template #default="{row}">{{ date(row.updated_at) }}</template></el-table-column>
    <el-table-column width="45"><template #default>↗</template></el-table-column>
  </el-table><div class="table-footer"><span>仅显示你有权访问的工单</span><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" /></div></section>
</template>
