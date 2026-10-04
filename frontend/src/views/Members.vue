<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, roles } from '../api'
import { useAuth } from '../store'
interface Member { user_id: string; email: string; name: string; role: string; is_active: boolean }
const wid = String(useRoute().params.wid), auth = useAuth()
const members = ref<Member[]>([]), error = ref(''), success = ref(''), busy = ref(false), loading = ref(true)
const form = reactive({ email: '', role: 'requester', is_active: true })
async function load() { try { members.value = await api(`/workspaces/${wid}/members`) } catch (e) { error.value = (e as Error).message } finally { loading.value = false } }
async function submit() { busy.value = true; error.value = ''; success.value = ''; try { await api(`/workspaces/${wid}/members`, 'PUT', form); await auth.load(); await load(); success.value = '成员权限已保存' } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
onMounted(load)
</script>
<template><div class="eyebrow">WORKSPACE / PEOPLE</div><div class="page-heading"><div><h1>成员设置</h1><p>让合适的人，拥有合适的权限。</p></div></div><el-alert v-if="error" :title="error" type="error" show-icon :closable="false" /><el-alert v-if="success" :title="success" type="success" />
  <section class="panel"><el-table v-loading="loading" :data="members"><el-table-column prop="name" label="成员"/><el-table-column prop="email" label="邮箱" min-width="210"/><el-table-column label="角色"><template #default="{row}">{{ roles[row.role] }}</template></el-table-column><el-table-column label="状态"><template #default="{row}">{{ row.is_active ? '有效' : '已撤销' }}</template></el-table-column><el-table-column width="90"><template #default="{row}"><el-button link @click="Object.assign(form, { email: row.email, role: row.role, is_active: row.is_active })">编辑</el-button></template></el-table-column></el-table></section>
  <section class="panel form-panel member-form"><h3>添加或更新成员</h3><p class="muted">输入已存在的账户邮箱。撤销权限后，该成员下次请求将无法访问本空间。</p><form @submit.prevent="submit"><label for="member-email">账户邮箱</label><el-input id="member-email" v-model="form.email" type="email" required /><div class="form-row"><div><label>空间角色</label><el-select v-model="form.role" aria-label="空间角色"><el-option v-for="(label, key) in roles" :key="key" :label="label" :value="key" /></el-select></div><div><label>成员权限</label><el-switch v-model="form.is_active" active-text="有效" inactive-text="撤销" /></div></div><div class="form-actions"><el-button type="primary" native-type="submit" :loading="busy">保存成员权限</el-button></div></form></section>
</template>
