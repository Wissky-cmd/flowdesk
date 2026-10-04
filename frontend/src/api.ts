export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId = '') { super(message) }
}
export let csrf = ''
export const setCsrf = (value: string) => { csrf = value }
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api/v1' + path, {
    method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(response.status, data.message || '请求失败，请稍后重试', data.request_id)
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}
export interface Workspace { id: string; name: string; role: string }
export interface Me { id: string; name: string; email: string; csrf_token: string; workspaces: Workspace[] }
export interface Ticket { id: string; title: string; body: string; status: string; priority: string; version: number; created_at: string; updated_at: string; creator_id: string; assignee_id: string | null }
export const roles: Record<string, string> = { admin: '管理员', agent: '处理人员', requester: '提交人' }
export const priorities: Record<string, string> = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
export const statuses: Record<string, string> = { new: '新建', accepted: '已受理', in_progress: '处理中', review: '待验收', closed: '已关闭', cancelled: '已取消' }
export const date = (value: string) => new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
