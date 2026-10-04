<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, roles } from '../api'
import { useAuth } from '../store'
import Icon from '../components/Icon.vue'
interface Member { user_id: string; email: string; name: string; role: string; is_active: boolean }
const wid = String(useRoute().params.wid), auth = useAuth()
const members = ref<Member[]>([]), error = ref(''), success = ref(''), busy = ref(false), loading = ref(true)
const form = reactive({ email: '', role: 'requester', is_active: true })
const editor = ref<HTMLElement | null>(null)
function edit(member: Member) {
  Object.assign(form, { email: member.email, role: member.role, is_active: member.is_active })
  success.value = ''
  editor.value?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  editor.value?.querySelector('input')?.focus({ preventScroll: true })
}
async function load() { try { members.value = await api(`/workspaces/${wid}/members`) } catch (e) { error.value = (e as Error).message } finally { loading.value = false } }
async function submit() { busy.value = true; error.value = ''; success.value = ''; try { await api(`/workspaces/${wid}/members`, 'PUT', form); await auth.load(); await load(); success.value = '成员权限已保存' } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
onMounted(load)
</script>
<template><div class="eyebrow"><span class="eyebrow-line"></span>BETTER TOGETHER / 03</div><div class="page-heading"><div><h1>成员设置<span class="greeting-dot">.</span></h1><p>让合适的人，拥有合适的权限。</p></div><span class="count-badge">{{ members.length }} 位协作成员</span></div><el-alert v-if="error" :title="error" type="error" show-icon :closable="false" /><el-alert v-if="success" :title="success" type="success" />
  <section v-loading="loading" class="panel members-panel" aria-label="空间成员"><div class="member-columns" aria-hidden="true"><span>团队成员</span><span>空间角色</span><span>权限状态</span><span></span></div><div v-for="member in members" :key="member.user_id" class="member-entry"><div class="member-person"><span class="member-avatar">{{ member.name.slice(0, 1) }}</span><div><strong>{{ member.name }}<span v-if="member.user_id === auth.me?.id" class="self-label">你</span></strong><span class="member-email">{{ member.email }}</span></div></div><span class="member-role">{{ roles[member.role] }}</span><span :class="['member-state', { revoked: !member.is_active }]"><i></i>{{ member.is_active ? '有效' : '已撤销' }}</span><button class="member-edit text-button" :aria-label="`编辑${member.name}`" @click="edit(member)">编辑<Icon name="diagonal" :size="14" /></button></div><el-empty v-if="!loading && !members.length" description="暂无可显示的成员" /></section>
  <div class="editor-grid member-editor-grid"><section ref="editor" class="panel form-panel member-form"><div class="form-section-title"><span class="section-index">01 /</span><h2>添加或更新成员</h2></div><p class="muted">输入已存在的账户邮箱，为成员设置合适的协作角色。</p><form @submit.prevent="submit"><label for="member-email">账户邮箱</label><el-input id="member-email" v-model="form.email" type="email" placeholder="name@your-team.com" required /><div class="form-row"><div><label for="member-role">空间角色</label><el-select id="member-role" v-model="form.role" aria-label="空间角色"><el-option v-for="(label, key) in roles" :key="key" :label="label" :value="key" /></el-select></div><div><label for="member-active">成员权限</label><el-switch id="member-active" v-model="form.is_active" aria-label="成员权限" active-text="有效" inactive-text="撤销" /></div></div><div class="form-actions"><el-button type="primary" native-type="submit" :loading="busy">保存成员权限<Icon name="check" :size="16" /></el-button></div></form></section><aside class="help-card"><div class="eyebrow">THE RIGHT ACCESS</div><h2>清晰的边界，<br/>安心的协作。</h2><p>管理员 · 管理本空间与成员</p><p>处理人员 · 查看本空间全部工单</p><p>提交人 · 查看自己创建的工单</p><hr/><p>撤销权限后，成员将无法继续访问本空间。历史工单仍会保留。</p></aside></div>
</template>
