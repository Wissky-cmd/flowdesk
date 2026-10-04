<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, date } from '../api'
import Icon from '../components/Icon.vue'
const base = `/workspaces/${useRoute().params.wid}/integration-tokens`
interface Token {id: string; name: string; scopes: string[]; expires_at: string; revoked_at: string | null}
const tokens = ref<Token[]>([]), error = ref(''), busy = ref(false), secret = ref(''), reveal = ref(false), success = ref('')
const form = reactive({name:'',days:30,scopes:['tickets:read']})
const scopes: Record<string,string> = {'tickets:read':'读取可见工单','tickets:create':'创建工单','tickets:comment':'添加评论'}
async function load() { try { tokens.value = await api(base) } catch (e) { error.value = (e as Error).message } }
async function create() {
  busy.value = true; error.value = ''; success.value = ''
  try { const result = await api<{token:string}>(base,'POST',form); secret.value = result.token; reveal.value = true; form.name = ''; await load() } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function revoke(token: Token) { busy.value = true; try { await api(`${base}/${token.id}`,'DELETE'); success.value = `已撤销「${token.name}」`; await load() } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
async function copy() { try { await navigator.clipboard.writeText(secret.value); success.value = '令牌已复制，请妥善保存。' } catch { success.value = '请选中令牌并手动复制。' } }
onMounted(load)
</script>
<template>
  <div class="eyebrow"><span class="eyebrow-line"></span>CONNECTED, WITH CARE / 05</div><div class="page-heading"><div><h1>连接你的工作流<span class="greeting-dot">.</span></h1><p>为可信应用签发有限权限，让协作有清晰边界。</p></div></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon /><p v-if="success" class="success-note" role="status">{{ success }}</p>
  <div class="editor-grid"><section class="panel detail-section"><h2>创建集成令牌</h2><form class="detail-edit" @submit.prevent="create"><fieldset :disabled="busy"><label for="token-name">用途名称</label><input id="token-name" v-model="form.name" required maxlength="80" placeholder="例如：DocPilot 工单助手" /><label for="token-days">有效期</label><select id="token-days" v-model="form.days"><option :value="7">7 天</option><option :value="30">30 天</option><option :value="90">90 天</option></select><span class="scope-label">允许的操作（至少选择一项）</span><label v-for="(label,key) in scopes" :key="key" class="scope-option"><input v-model="form.scopes" type="checkbox" :value="key" /><span>{{ label }}</span><code>{{ key }}</code></label><div class="form-actions"><el-button type="primary" native-type="submit" :loading="busy" :disabled="!form.scopes.length">创建令牌</el-button></div></fieldset></form></section><aside class="help-card"><div class="eyebrow">A CLEAR BOUNDARY</div><h3>权限始终属于你。</h3><p>令牌仅限当前空间，权限不会超过你的当前角色。</p><p>令牌不能管理成员、签发新令牌或代替你验收工单。</p><hr/><p>明文只显示一次。权限收回、过期或撤销后，访问立即失效。</p></aside></div>
  <div class="section-heading jobs-heading"><div class="section-title"><span class="section-index">01 /</span><h2>我的令牌</h2></div></div><div class="job-list"><article v-for="token in tokens" :key="token.id" class="panel job-card"><div class="job-glyph"><Icon name="shield" /></div><div class="job-content"><h3>{{ token.name }}</h3><p class="muted">{{ token.scopes.map(scope => scopes[scope]).join(' · ') }}</p><span class="muted">{{ token.revoked_at ? '已撤销' : new Date(token.expires_at).getTime() < Date.now() ? '已过期' : `有效至 ${date(token.expires_at)}` }}</span></div><el-button v-if="!token.revoked_at" :disabled="busy" @click="revoke(token)">撤销令牌</el-button></article><p v-if="!tokens.length" class="muted">尚未签发令牌。只有需要连接其他应用时才创建。</p></div>
  <el-dialog v-model="reveal" title="保存你的集成令牌" width="min(600px, calc(100vw - 32px))" :close-on-click-modal="false" @closed="secret = ''"><p>这是唯一一次显示明文。请保存到可信应用的密钥配置中。</p><label for="new-token" class="muted">集成令牌</label><textarea id="new-token" class="token-secret" readonly :value="secret" rows="3" spellcheck="false" /><p class="muted">请勿公开分享或提交到代码仓库。</p><template #footer><el-button @click="copy">复制令牌</el-button><el-button type="primary" @click="reveal = false">已保存，关闭</el-button></template></el-dialog>
</template>
