<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, date } from '../api'
import Icon from '../components/Icon.vue'
const wid = String(useRoute().params.wid), base = `/workspaces/${wid}`
interface Job {id: string; status: string; generation: number; attempts: number; run_attempts: number; error_code: string | null; created_at: string; expires_at: string}
interface JobDetail extends Job {delivery_attempts: number; delivery_run_attempts: number; events: {kind: string; generation: number; detail: {reason?: string; error_code?: string}; created_at: string}[]}
const rows = ref<Job[]>([]), total = ref(0), page = ref(1), error = ref(''), loading = ref(false), busy = ref(false), notice = ref('')
const selected = ref<JobDetail | null>(null), retrying = ref<Job | null>(null), reason = ref('')
const labels: Record<string, string> = {queued:'等待处理',running:'正在导出',succeeded:'导出完成',failed:'导出失败',expired:'已过期'}
const errors: Record<string,string> = {PERMISSION_REVOKED:'空间权限已变化，请检查当前权限后重试。', DELIVERY_EXHAUSTED:'队列投递重试已耗尽，请联系管理员检查任务服务。', TEMPORARY_FAILURE:'暂时无法生成文件，系统将有限重试。', TEMPORARY_FAILURE_EXHAUSTED:'执行重试已耗尽，请检查文件存储后重试。', EXECUTION_EXHAUSTED:'执行次数已达上限。', LEASE_EXPIRED_EXHAUSTED:'处理进程多次失联，请检查任务服务。', EXPORT_ROW_LIMIT:'可见工单超过 10,000 条，超出单次导出上限。', EXPORT_ERROR:'文件生成失败，请查看任务记录。',LEASE_EXPIRED:'处理进程失联，正在安排恢复。'}
const eventLabels: Record<string,string> = {created:'创建任务',delivery_started:'开始投递',delivery_failed:'投递失败',delivered:'已送入队列',execution_started:'开始执行',retry_scheduled:'安排自动重试',failed:'任务失败',manual_retry:'人工重试',succeeded:'文件已生成',expired:'文件已过期'}
let timer: ReturnType<typeof setTimeout> | undefined, stopped = false
async function load() {
  if (loading.value || stopped) return
  loading.value = true; error.value = ''
  try { const data = await api<{items: Job[]; total: number}>(`${base}/jobs?page=${page.value}`); if (!stopped) { rows.value = data.items; total.value = data.total } }
  catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
async function poll() { await load(); if (!stopped) timer = setTimeout(poll, 5000) }
async function createExport() {
  busy.value = true; error.value = ''; notice.value = ''
  try { await api(base + '/exports', 'POST'); notice.value = '导出任务已提交，可在这里查看进度。'; page.value = 1; await load() } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function inspect(job: Job) { try { selected.value = await api(`${base}/jobs/${job.id}`) } catch (e) { error.value = (e as Error).message } }
async function retry() {
  if (!retrying.value) return
  busy.value = true
  try { await api(`${base}/jobs/${retrying.value.id}/retry`, 'POST', {reason: reason.value}); retrying.value = null; reason.value = ''; notice.value = '已开启新一轮尝试，历史记录已保留。'; await load() } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
onMounted(poll)
onBeforeUnmount(() => { stopped = true; clearTimeout(timer) })
</script>
<template>
  <div class="eyebrow"><span class="eyebrow-line"></span>WORK IN THE BACKGROUND / 04</div>
  <div class="page-heading"><div><h1>把等待，交给后台<span class="greeting-dot">.</span></h1><p>导出你的可见工单，进展与结果都留在这里。</p></div><el-button type="primary" size="large" :loading="busy" @click="createExport"><Icon name="plus" :size="17" />导出工单 CSV</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
  <p v-if="notice" class="success-note" role="status">{{ notice }}</p>
  <div class="info-strip"><Icon name="shield" :size="25" /><div><strong>只导出你有权查看的内容</strong><p>文件保留 24 小时，每次最多 10,000 条。权限变化后需要重新导出。</p></div></div>
  <div class="section-heading jobs-heading"><div class="section-title"><span class="section-index">01 /</span><h2>我的导出</h2><span class="pill">{{ total }}</span></div><button class="icon-button" aria-label="刷新任务" :disabled="loading" @click="load"><Icon name="refresh" :class="{spinning:loading}" :size="18" /></button></div>
  <div v-if="!rows.length && !loading && !error" class="empty-state panel"><div class="empty-symbol"><Icon name="clock" :size="28" /></div><h3>还没有后台任务</h3><p>创建一次导出，让数据带着清晰的上下文离开。</p></div>
  <div class="job-list"><article v-for="job in rows" :key="job.id" class="panel job-card"><div class="job-glyph"><Icon :name="job.status === 'succeeded' ? 'check' : 'clock'" :size="22" /></div><div class="job-content"><div class="job-title"><h3>工单清单导出</h3><span class="status-chip" :data-status="job.status === 'failed' ? 'review' : job.status === 'succeeded' ? 'closed' : 'new'">{{ labels[job.status] }}</span></div><p class="ticket-id">{{ job.id.slice(0, 8).toUpperCase() }} · {{ date(job.created_at) }}</p><p v-if="job.error_code" class="job-error">{{ errors[job.error_code] || job.error_code }}</p><span class="muted">第 {{ job.generation }} 轮 · 累计执行 {{ job.attempts }} 次</span></div><div class="job-actions"><a v-if="job.status === 'succeeded' && new Date(job.expires_at).getTime() > Date.now()" class="download-button" :href="`/api/v1${base}/jobs/${job.id}/download`" download>下载 CSV <Icon name="arrow" :size="15" /></a><el-button v-if="['failed','expired'].includes(job.status)" :disabled="busy" @click="retrying = job">人工重试</el-button><button class="text-button" @click="inspect(job)">查看记录</button></div></article></div>
  <div class="table-footer"><span>每 5 秒更新 · 文件过期后可重新导出</span><el-pagination v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load" /></div>
  <el-dialog :model-value="!!retrying" title="重新尝试这次导出" width="min(500px, calc(100vw - 32px))" @close="retrying = null"><form class="detail-edit" @submit.prevent="retry"><p class="muted">请先确认故障已处理。新一轮尝试会保留此前的失败记录。</p><label for="retry-reason">重试原因</label><textarea id="retry-reason" v-model="reason" rows="3" maxlength="500" required /><div class="form-actions"><el-button :disabled="busy" @click="retrying = null">取消</el-button><el-button type="primary" native-type="submit" :loading="busy">确认重试</el-button></div></form></el-dialog>
  <el-dialog :model-value="!!selected" title="任务记录" width="min(620px, calc(100vw - 32px))" @close="selected = null"><template v-if="selected"><p class="muted">累计投递 {{ selected.delivery_attempts }} 次 · 累计执行 {{ selected.attempts }} 次</p><ol class="activity-list"><li v-for="(event, index) in selected.events" :key="index"><span class="activity-mark"><Icon name="clock" :size="14" /></span><div><div class="activity-heading"><strong>{{ eventLabels[event.kind] || event.kind }}</strong><span>第 {{ event.generation }} 轮</span><time>{{ date(event.created_at) }}</time></div><p v-if="event.detail.reason || event.detail.error_code" class="activity-body">{{ event.detail.reason || errors[event.detail.error_code || ''] || event.detail.error_code }}</p></div></li></ol></template></el-dialog>
</template>
