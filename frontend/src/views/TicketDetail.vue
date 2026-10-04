<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, ApiError, date, priorities, statuses, type Ticket } from '../api'
import { useAuth } from '../store'
import Icon from '../components/Icon.vue'
const route = useRoute(), auth = useAuth(), wid = String(route.params.wid)
const base = `/workspaces/${wid}/tickets/${route.params.id}`
const ticket = ref<Ticket | null>(null), error = ref(''), loading = ref(true), busy = ref(false), notice = ref(''), conflict = ref(false)
const actions = ref<{transitions: string[]; can_edit: boolean}>({transitions: [], can_edit: false})
const assignees = ref<{id: string; name: string}[]>([]), editing = ref(false)
const draft = reactive({title: '', body: '', priority: 'normal', assignee_id: null as string | null})
const staff = computed(() => auth.me?.workspaces.find(w => w.id === wid)?.role !== 'requester')
const comment = ref(''), reason = ref(''), target = ref(''), fileInput = ref<HTMLInputElement | null>(null)
const files = ref<{id: string; filename: string; size: number}[]>([])
interface Activity { id: string; kind: string; actor: string; created_at: string; detail: {body?: string; reason?: string; filename?: string; before?: Ticket; after?: Ticket} }
const activity = ref<Activity[]>([]), activityPage = ref(1), activityTotal = ref(0)
const steps = ['new', 'accepted', 'in_progress', 'review', 'closed']
const labels: Record<string, string> = {accepted: '受理工单', in_progress: '开始处理', review: '提交验收', closed: '验收通过', cancelled: '取消工单'}
function actionLabel(status: string) { return status === 'in_progress' && ticket.value?.status === 'review' ? '退回处理' : status === 'in_progress' && ticket.value?.status === 'closed' ? '重新打开' : labels[status] }
const needsReason = computed(() => target.value === 'cancelled' || (target.value === 'in_progress' && ['review', 'closed'].includes(ticket.value?.status || '')))
async function loadActivity() {
  const result = await api<{items: Activity[]; total: number}>(`${base}/activity?page=${activityPage.value}`)
  activity.value = result.items; activityTotal.value = result.total
}
async function changeActivity(page: number) { activityPage.value = page; try { await loadActivity() } catch (e) { error.value = (e as Error).message } }
async function load(preserve = false) {
  loading.value = true; error.value = ''
  try {
    const [current, available, attachments, people] = await Promise.all([api<Ticket>(base), api<typeof actions.value>(base + '/actions'), api<typeof files.value>(base + '/attachments'), api<typeof assignees.value>(`/workspaces/${wid}/assignees`)])
    ticket.value = current; actions.value = available; files.value = attachments; assignees.value = people
    await loadActivity(); conflict.value = false; target.value = ''
    if (preserve) notice.value = '已加载最新版本，你的编辑草稿已保留。请核对后再保存。'
  } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
function edit() { if (ticket.value) Object.assign(draft, {title: ticket.value.title, body: ticket.value.body, priority: ticket.value.priority, assignee_id: ticket.value.assignee_id}); editing.value = true; notice.value = '' }
async function run(operation: () => Promise<unknown>, success: string, done: () => void = () => {}) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await operation(); done(); notice.value = success; activityPage.value = 1; await load() }
  catch (e) { error.value = (e as Error).message; conflict.value = e instanceof ApiError && e.status === 409 }
  finally { busy.value = false }
}
async function save() { await run(() => api(base, 'PUT', {...draft, version: ticket.value?.version}), '修改已保存', () => { editing.value = false }) }
async function transition() { await run(() => api(base + '/transitions', 'POST', {version: ticket.value?.version, status: target.value, reason: reason.value}), '工单状态已更新', () => { reason.value = ''; target.value = '' }) }
async function sendComment() { await run(() => api(base + '/comments', 'POST', {body: comment.value}), '评论已发布', () => { comment.value = '' }) }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  if (file.size > 5242880 || !file.size) { error.value = '请选择非空且不超过 5 MB 的文件'; input.value = ''; return }
  await run(() => api(`${base}/attachments?filename=${encodeURIComponent(file.name)}`, 'POST', file), '附件已上传')
  input.value = ''
}
function activityLabel(item: Activity) {
  if (item.kind === 'transition') return `${statuses[item.detail.before?.status || '']} → ${statuses[item.detail.after?.status || '']}`
  return ({created: '创建了工单', updated: '更新了工单', comment: '发表了评论', attachment: '上传了附件'} as Record<string, string>)[item.kind]
}
function changes(item: Activity) {
  const before = item.detail.before, after = item.detail.after
  if (!before || !after) return ''
  return (['title', 'body', 'priority', 'assignee_id'] as const).filter(key => before[key] !== after[key]).map(key => ({title: '标题', body: '描述', priority: '优先级', assignee_id: '负责人'})[key]).join('、')
}
onMounted(() => load())
</script>
<template>
  <RouterLink class="back-link" :to="`/w/${wid}/tickets`"><Icon name="back" :size="16" />返回工单中心</RouterLink>
  <div class="detail-wrap" :aria-busy="loading">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon><button class="text-button" :disabled="busy || loading" @click="load(editing)">{{ conflict ? '加载最新版本，保留草稿' : '重新加载' }}</button></el-alert>
    <p v-if="notice" class="success-note" role="status"><Icon name="check" :size="16" />{{ notice }}</p>
    <div v-if="loading && !ticket" class="panel detail-loading" role="status">正在载入工单…</div>
    <template v-if="ticket">
      <div class="ticket-id detail-id">工单 #{{ ticket.id.slice(0, 8).toUpperCase() }} <span> / v{{ ticket.version }}</span></div>
      <div class="page-heading"><div><h1>{{ ticket.title }}</h1><p>创建于 {{ date(ticket.created_at) }} · 最近更新 {{ date(ticket.updated_at) }}</p></div><span class="status-chip" :data-status="ticket.status"><i></i>{{ statuses[ticket.status] }}</span></div>
      <ol class="workflow-track" aria-label="工单进度"><li v-for="(step, i) in steps" :key="step" :class="{current: ticket.status === step, complete: steps.indexOf(ticket.status) > i}" :aria-current="ticket.status === step ? 'step' : undefined"><span>{{ String(i + 1).padStart(2, '0') }}</span>{{ statuses[step] }}<Icon v-if="steps.indexOf(ticket.status) > i" name="check" :size="14" /></li></ol>
      <div class="detail-grid">
        <div class="detail-main">
          <section class="panel detail-section"><div class="section-heading"><h2>请求详情</h2><button v-if="actions.can_edit && !editing" class="text-button" :disabled="busy || loading" @click="edit">编辑详情 <Icon name="diagonal" :size="15" /></button></div>
            <p v-if="!editing" class="ticket-body">{{ ticket.body }}</p>
            <form v-else class="detail-edit" @submit.prevent="save"><fieldset :disabled="busy || loading || conflict"><label for="edit-title">工单标题</label><input id="edit-title" v-model="draft.title" maxlength="200" required /><label for="edit-body">详细描述</label><textarea id="edit-body" v-model="draft.body" rows="6" maxlength="20000" required /><div v-if="staff" class="form-row"><div><label for="edit-priority">优先级</label><select id="edit-priority" v-model="draft.priority"><option v-for="(label, key) in priorities" :key="key" :value="key">{{ label }}</option></select></div><div><label for="edit-assignee">负责人</label><select id="edit-assignee" v-model="draft.assignee_id"><option :value="null">暂未分派</option><option v-for="a in assignees" :key="a.id" :value="a.id">{{ a.name }}</option></select></div></div></fieldset><div class="form-actions"><el-button :disabled="busy" @click="editing = false">取消编辑</el-button><el-button type="primary" native-type="submit" :loading="busy" :disabled="loading || conflict">保存修改</el-button></div></form>
          </section>
          <section class="panel detail-section"><div class="section-heading"><h2>附件 <span class="muted">{{ files.length }} / 10</span></h2><button class="text-button" :disabled="busy || files.length >= 10" @click="fileInput?.click()"><Icon name="plus" :size="15" />添加附件</button><input ref="fileInput" class="file-input" type="file" tabindex="-1" aria-label="选择附件" accept=".png,.jpg,.jpeg,.pdf,.txt" :disabled="busy || files.length >= 10" @change="upload" /></div><p class="muted">PNG、JPEG、PDF 或 UTF-8 文本 · 每个文件最大 5 MB</p><div v-if="files.length" class="attachment-list"><a v-for="file in files" :key="file.id" :href="`/api/v1${base}/attachments/${file.id}`" download><Icon name="ticket" :size="18" /><span>{{ file.filename }}<small>{{ (file.size / 1024).toFixed(1) }} KB</small></span><Icon name="arrow" :size="16" /></a></div><p v-else class="attachment-empty">补充一张截图或说明，让问题更清晰。</p></section>
          <section class="panel detail-section"><div class="section-heading"><h2>协作记录</h2><span class="eyebrow">KEEP THE CONTEXT</span></div>
            <form class="comment-form" @submit.prevent="sendComment"><label for="comment">补充进展或反馈</label><textarea id="comment" v-model="comment" rows="3" maxlength="5000" placeholder="让团队知道最新进展…" required :disabled="busy" /><div class="comment-footer"><span>所有可见成员均可参与讨论</span><el-button type="primary" native-type="submit" :loading="busy" :disabled="!comment.trim()">发布评论</el-button></div></form>
            <ol class="activity-list"><li v-for="item in activity" :key="item.id"><span class="activity-mark"><Icon :name="item.kind === 'comment' ? 'people' : item.kind === 'transition' ? 'arrow' : 'check'" :size="14" /></span><div><div class="activity-heading"><strong>{{ item.actor }}</strong><span>{{ activityLabel(item) }}</span><time>{{ date(item.created_at) }}</time></div><p v-if="item.detail.body || item.detail.reason || item.detail.filename" class="activity-body">{{ item.detail.body || item.detail.reason || item.detail.filename }}</p><p v-if="item.kind === 'updated'" class="muted">修改了：{{ changes(item) || '内容已确认' }}</p></div></li></ol><p v-if="!activity.length" class="muted">还没有协作记录，从一条评论开始。</p><el-pagination v-if="activityTotal > 30" :current-page="activityPage" :page-size="30" :total="activityTotal" layout="prev, pager, next" @current-change="changeActivity" />
          </section>
        </div>
        <aside class="detail-aside"><section class="panel metadata"><div class="eyebrow">AT A GLANCE</div><h3>工单信息</h3><dl><dt>优先级</dt><dd :class="['priority', ticket.priority]">{{ priorities[ticket.priority] }}</dd><dt>负责人</dt><dd>{{ assignees.find(a => a.id === ticket?.assignee_id)?.name || (ticket.assignee_id ? '成员已停用' : '暂未分派') }}</dd><dt>当前状态</dt><dd>{{ statuses[ticket.status] }}</dd><dt>记录版本</dt><dd>v{{ ticket.version }}</dd></dl></section>
          <section class="action-panel"><div class="eyebrow">THE NEXT STEP</div><h2>推进一步<span class="greeting-dot">.</span></h2><p>{{ actions.transitions.length ? '选择下一步，让协作持续向前。' : '当前没有你可以执行的状态操作。你仍可补充评论与附件。' }}</p><form v-if="actions.transitions.length" @submit.prevent="transition"><fieldset :disabled="busy || loading || conflict || editing"><label for="next-state">下一步操作</label><select id="next-state" v-model="target" required><option value="" disabled>选择操作</option><option v-for="state in actions.transitions" :key="state" :value="state">{{ actionLabel(state) }}</option></select><label for="transition-reason">{{ needsReason ? '原因（必填）' : '补充说明（选填）' }}</label><textarea id="transition-reason" v-model="reason" rows="3" :required="needsReason" maxlength="2000" placeholder="记录决定背后的原因" /><el-button type="primary" native-type="submit" :loading="busy" :disabled="!target || conflict || editing || loading">确认{{ target ? actionLabel(target) : '操作' }} <Icon name="arrow" :size="16" /></el-button></fieldset></form><small v-if="editing">请先保存或取消编辑，再推进状态。</small><small v-else-if="!ticket.assignee_id && actions.transitions.length">受理前，请在详情中分派负责人。</small></section>
        </aside>
      </div>
    </template>
  </div>
</template>
