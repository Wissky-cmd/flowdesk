<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, priorities, type Ticket } from '../api'
import { useAuth } from '../store'
const route = useRoute(), router = useRouter(), auth = useAuth(), wid = String(route.params.wid)
const form = reactive({ title: '', body: '', priority: 'normal', assignee_id: null as string | null })
const error = ref(''), busy = ref(false), assignees = ref<{id: string; name: string}[]>([])
const canAssign = computed(() => auth.me?.workspaces.find(w => w.id === wid)?.role !== 'requester')
onMounted(async () => { if (canAssign.value) { try { assignees.value = await api(`/workspaces/${wid}/assignees`) } catch (e) { error.value = (e as Error).message } } })
async function submit() {
  busy.value = true; error.value = ''
  try { const ticket = await api<Ticket>(`/workspaces/${wid}/tickets`, 'POST', form); await router.push(`/w/${wid}/tickets/${ticket.id}`) }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template><RouterLink class="back-link" :to="`/w/${wid}/tickets`">← 返回工单中心</RouterLink><div class="page-heading"><div><h1>创建工单</h1><p>描述清楚一点，协作就能更快一步。</p></div></div>
  <div class="editor-grid"><section class="panel form-panel"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon /><form @submit.prevent="submit">
    <label for="title">工单标题 <span>*</span></label><el-input id="title" v-model="form.title" placeholder="用一句话概括你需要的帮助" maxlength="200" show-word-limit size="large" required />
    <label for="body">详细描述 <span>*</span></label><el-input id="body" v-model="form.body" type="textarea" :rows="8" placeholder="背景是什么？希望达成什么结果？请补充必要的信息。" maxlength="20000" required />
    <div class="form-row"><div><label for="priority">优先级</label><el-select id="priority" v-model="form.priority" aria-label="优先级"><el-option v-for="(label, key) in priorities" :key="key" :label="label" :value="key" /></el-select></div><div v-if="canAssign"><label for="assignee">负责人</label><el-select id="assignee" v-model="form.assignee_id" clearable placeholder="暂不分派" aria-label="负责人" @clear="form.assignee_id = null"><el-option v-for="a in assignees" :key="a.id" :label="a.name" :value="a.id" /></el-select></div></div>
    <div class="form-actions"><el-button @click="router.back()">取消</el-button><el-button type="primary" native-type="submit" :loading="busy">提交工单 →</el-button></div></form></section>
    <aside class="help-card"><div class="eyebrow">A GOOD REQUEST</div><h3>好的描述，让沟通少绕路。</h3><p>01 / 说明问题发生的场景</p><p>02 / 写下你期待的结果</p><p>03 / 根据影响范围设置优先级</p><hr/><p>提交后，你可以在工单中心查看详情。</p></aside></div>
</template>
