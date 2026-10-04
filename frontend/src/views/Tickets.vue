<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, date, priorities, statuses, type Ticket } from '../api'
import Icon from '../components/Icon.vue'
import FlowArt from '../components/FlowArt.vue'
const route = useRoute(), router = useRouter(), wid = String(route.params.wid)
const rows = ref<Ticket[]>([]), total = ref(0), page = ref(1), loading = ref(true), error = ref('')
const query = ref(''), priority = ref('all'), layout = ref<'list' | 'grid'>('list'), reverse = ref(false), updated = ref(false)
const status = ref(String(route.query.status || '')), assignee = ref(''), from = ref(''), to = ref('')
const assignees = ref<{id: string; name: string}[]>([])
const filtered = computed(() => rows.value)
const hasFilter = computed(() => !!(query.value.trim() || priority.value !== 'all' || status.value || assignee.value || from.value || to.value))
let generation = 0
async function load() {
  const request = ++generation
  loading.value = true; error.value = ''; updated.value = false
  const params = new URLSearchParams({page: String(page.value), sort: reverse.value ? 'oldest' : 'newest'})
  if (query.value.trim()) params.set('q', query.value.trim())
  if (priority.value !== 'all') params.set('priority', priority.value)
  if (status.value) params.set('status', status.value)
  if (assignee.value === 'none') params.set('unassigned', 'true')
  else if (assignee.value) params.set('assignee_id', assignee.value)
  if (from.value) params.set('created_from', new Date(from.value + 'T00:00:00').toISOString())
  if (to.value) { const end = new Date(to.value + 'T00:00:00'); end.setDate(end.getDate() + 1); params.set('created_to', end.toISOString()) }
  try { const data = await api<{items: Ticket[]; total: number}>(`/workspaces/${wid}/tickets?${params}`); if (request === generation) { rows.value = data.items; total.value = data.total; updated.value = true } }
  catch (e) { if (request === generation) error.value = (e as Error).message } finally { if (request === generation) loading.value = false }
}
function search() { page.value = 1; void load() }
function resetFilters() { query.value = ''; priority.value = 'all'; status.value = ''; assignee.value = ''; from.value = ''; to.value = ''; search() }
onMounted(async () => { void load(); try { assignees.value = await api(`/workspaces/${wid}/assignees`) } catch (e) { error.value = (e as Error).message } })
</script>
<template>
  <section class="ticket-hero">
    <div class="hero-copy"><div class="eyebrow"><span class="eyebrow-line"></span>TEAM SERVICE, IN FLOW <span class="edition">/ 02</span></div><h1>工单中心<span class="greeting-dot">.</span></h1><p>让每一个请求，<br class="mobile-break"/>都有清晰的下一步。</p><el-button class="create-button" type="primary" size="large" @click="router.push(`/w/${wid}/tickets/new`)"><Icon name="plus" :size="18" />创建工单<Icon name="diagonal" :size="17" /></el-button></div>
    <div class="hero-visual"><FlowArt compact /><div class="hero-label"><span class="live-dot"></span>连接需求与行动</div></div>
    <div class="hero-bottom"><span><Icon name="shield" :size="14" />空间内协作 · 按权限可见</span><span class="hero-bottom-right">LESS FRICTION. MORE FLOW.</span></div>
  </section>
  <section class="ticket-section" aria-label="工单列表">
    <div class="section-heading"><div class="section-title"><span class="section-index">01 /</span><h2>全部可见工单</h2><span class="pill">{{ loading && !rows.length ? '—' : total.toString().padStart(2, '0') }}</span></div><div class="section-tools"><span v-if="updated && !loading" class="sync-label" role="status"><span class="sync-dot"></span>已同步</span><button class="icon-button" :disabled="loading" aria-label="刷新列表" title="刷新列表" @click="load"><Icon name="refresh" :class="{ spinning: loading }" :size="18" /></button><div class="view-switch" aria-label="列表显示方式"><button :class="{ selected: layout === 'list' }" :aria-pressed="layout === 'list'" aria-label="列表视图" @click="layout = 'list'"><Icon name="list" :size="17" /></button><button :class="{ selected: layout === 'grid' }" :aria-pressed="layout === 'grid'" aria-label="卡片视图" @click="layout = 'grid'"><Icon name="grid" :size="16" /></button></div></div></div>
    <form class="filter-form" @submit.prevent="search"><div class="ticket-toolbar"><div class="search-field"><Icon name="search" :size="18" /><input v-model="query" aria-label="搜索全部工单" placeholder="搜索标题或编号…" /><button v-if="query" type="button" class="clear-search" aria-label="清除搜索" @click="query = ''; search()"><Icon name="close" :size="15" /></button><span v-else class="search-caption">全部工单</span></div><div class="toolbar-right"><label class="priority-select"><span>优先级</span><select v-model="priority" aria-label="筛选优先级" @change="search"><option value="all">全部</option><option v-for="(label, key) in priorities" :key="key" :value="key">{{ label }}</option></select></label><button type="button" class="sort-button" aria-label="切换更新时间排序" :aria-pressed="reverse" @click="reverse = !reverse; search()"><Icon name="sort" :size="16" /><span>{{ reverse ? '最早更新' : '最近更新' }}</span></button><el-button native-type="submit" :loading="loading">搜索</el-button></div></div>
    <div class="filter-extra"><label>状态<select v-model="status" aria-label="筛选状态" @change="search"><option value="">全部状态</option><option v-for="(label, key) in statuses" :key="key" :value="key">{{ label }}</option></select></label><label>负责人<select v-model="assignee" aria-label="筛选负责人" @change="search"><option value="">所有人</option><option value="none">未分派</option><option v-for="a in assignees" :key="a.id" :value="a.id">{{ a.name }}</option></select></label><label>创建日期起<input v-model="from" type="date" aria-label="创建日期起" @change="search" /></label><label>创建日期止<input v-model="to" type="date" aria-label="创建日期止" @change="search" /></label><button v-if="hasFilter" type="button" class="text-button" @click="resetFilters">重置筛选</button></div></form>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false"><button class="text-button" @click="load">重新加载</button></el-alert>
    <div v-if="loading && !rows.length" class="ticket-skeleton" aria-label="正在加载工单" role="status"><div v-for="i in 3" :key="i"><span></span><i></i><i></i></div></div>
    <div v-else-if="!filtered.length && !error" class="empty-state"><div class="empty-symbol"><Icon :name="hasFilter ? 'search' : 'ticket'" :size="28" /></div><h3>{{ hasFilter ? '暂时没有匹配的工单' : '把第一个请求，交给 FlowDesk。' }}</h3><p>{{ hasFilter ? '试试其他关键词，或清除筛选条件。' : '从一个清晰的描述开始，让团队知道你需要什么。' }}</p><button v-if="hasFilter" class="text-button" @click="resetFilters">清除筛选 <Icon name="arrow" :size="16" /></button><el-button v-else type="primary" @click="router.push(`/w/${wid}/tickets/new`)">创建第一张工单</el-button></div>
    <div v-else :class="['ticket-collection', layout, { 'is-refreshing': loading }]" :aria-busy="loading">
      <div class="ticket-columns" aria-hidden="true"><span>工单 / 请求内容</span><span>状态</span><span>优先级</span><span>最近更新</span><span></span></div>
      <RouterLink v-for="(ticket, i) in filtered" :key="ticket.id" class="ticket-row" :to="`/w/${wid}/tickets/${ticket.id}`" :style="{ '--row-index': i }" :aria-label="ticket.title">
        <div class="ticket-primary"><span class="ticket-glyph"><Icon name="ticket" :size="19" /></span><div class="ticket-text"><span class="ticket-title">{{ ticket.title }}</span><span class="ticket-id">FD–{{ ticket.id.slice(0, 8).toUpperCase() }}<span class="ticket-mobile-date">{{ date(ticket.updated_at) }}</span></span></div></div>
        <span class="status-chip" :data-status="ticket.status"><i></i>{{ statuses[ticket.status] }}</span>
        <span :class="['priority', ticket.priority]"><span class="priority-bars" aria-hidden="true"><i></i><i></i><i></i></span>{{ priorities[ticket.priority] }}</span>
        <time class="ticket-date" :datetime="ticket.updated_at">{{ date(ticket.updated_at) }}</time><span class="row-arrow"><Icon name="diagonal" :size="18" /></span>
      </RouterLink>
    </div>
    <div class="table-footer"><span>{{ hasFilter ? `共匹配 ${total} 条` : `共 ${total} 条工单，每页 20 条` }}<span class="footer-separator">/</span>按权限呈现</span><el-pagination :disabled="loading" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" /></div>
  </section>
  <div class="work-note"><span class="note-star">✳</span><p>好的协作，从清晰的表达开始。<span>写下背景、目标与期待，让下一步更简单。</span></p><RouterLink :to="`/w/${wid}/tickets/new`">记录一个新请求<Icon name="arrow" :size="17" /></RouterLink></div>
</template>
