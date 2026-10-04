<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, date, priorities, statuses, type Ticket } from '../api'
import Icon from '../components/Icon.vue'
const wid = String(useRoute().params.wid), loading = ref(true), error = ref('')
const summary = ref<{total: number; statuses: Record<string, number>; priorities: Record<string, number>; assignees: {id: string | null; name: string; count: number}[]}>({total: 0, statuses: {}, priorities: {}, assignees: []})
const columns = ref<{status: string; items: Ticket[]; total: number}[]>([])
const active = computed(() => summary.value.total - (summary.value.statuses.closed || 0) - (summary.value.statuses.cancelled || 0))
async function load() {
  loading.value = true; error.value = ''
  try {
    const [totals, ...lanes] = await Promise.all([api<typeof summary.value>(`/workspaces/${wid}/tickets/summary`), ...Object.keys(statuses).map(async status => ({status, ...await api<{items: Ticket[]; total: number}>(`/workspaces/${wid}/tickets?status=${status}&page_size=20`)}))])
    summary.value = totals; columns.value = lanes
  } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <div class="eyebrow"><span class="eyebrow-line"></span>A SHARED VIEW / 03</div>
  <div class="page-heading"><div><h1>协作，一目了然<span class="greeting-dot">.</span></h1><p>从请求到完成，看见每一步的进展。</p></div><button class="icon-button" aria-label="刷新看板" :disabled="loading" @click="load"><Icon name="refresh" :class="{spinning: loading}" /></button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
  <div class="board-metrics" :aria-busy="loading"><article class="metric-card featured"><span>正在流转</span><strong>{{ loading ? '—' : active }}</strong><small>每一个请求，都在向前。</small><Icon name="spark" :size="70" /></article><article class="metric-card"><span>等待验收</span><strong>{{ loading ? '—' : summary.statuses.review || 0 }}</strong><small>最后一步，确认成果</small></article><article class="metric-card"><span>已完成</span><strong>{{ loading ? '—' : summary.statuses.closed || 0 }}</strong><small>已验收关闭的工单</small></article><article class="metric-card"><span>可见工单总数</span><strong>{{ loading ? '—' : summary.total }}</strong><small>其中紧急 {{ summary.priorities.urgent || 0 }} 项</small></article></div>
  <div class="board-distribution"><div><span class="muted">待办分工</span><span v-for="person in summary.assignees" :key="person.id || 'none'" class="distribution-chip">{{ person.name }} <strong>{{ person.count }}</strong></span><span v-if="!summary.assignees.length" class="muted">暂无待办</span></div><div><span class="muted">优先级分布</span><span v-for="(label, key) in priorities" :key="key" class="distribution-chip">{{ label }} <strong>{{ summary.priorities[key] || 0 }}</strong></span></div></div>
  <div class="section-heading board-heading"><div class="section-title"><span class="section-index">01 /</span><h2>流转看板</h2></div><span class="muted">按权限呈现 · 每列最近 20 条</span></div>
  <p v-if="loading && !columns.length" class="panel detail-loading" role="status">正在加载团队进展…</p>
  <div class="board-grid" :aria-busy="loading"><section v-for="column in columns" :key="column.status" class="board-column"><header><span class="status-chip" :data-status="column.status"><i></i>{{ statuses[column.status] }}</span><span class="pill">{{ column.total }}</span></header><RouterLink v-for="ticket in column.items" :key="ticket.id" class="board-ticket" :to="`/w/${wid}/tickets/${ticket.id}`"><div><span class="ticket-id">FD–{{ ticket.id.slice(0, 8).toUpperCase() }}</span><Icon name="diagonal" :size="14" /></div><h3>{{ ticket.title }}</h3><footer><span :class="['priority', ticket.priority]">{{ priorities[ticket.priority] }}</span><time>{{ date(ticket.updated_at) }}</time></footer></RouterLink><div v-if="!column.total" class="board-empty"><span>—</span><p>这一列，暂时留白。</p></div><RouterLink v-if="column.total" class="board-more" :to="`/w/${wid}/tickets?status=${column.status}`">查看全部 {{ column.total }} 条 <Icon name="arrow" :size="14" /></RouterLink></section></div>
  <div class="work-note"><span class="note-star">✳</span><p>看见进展，也看见彼此。<span>打开工单即可分派、推进状态或补充评论。</span></p><RouterLink :to="`/w/${wid}/tickets/new`">记录一个新请求<Icon name="arrow" :size="17" /></RouterLink></div>
</template>
