import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, setCsrf, type Me } from './api'

export const useAuth = defineStore('auth', () => {
  const me = ref<Me | null>(null)
  async function load() { me.value = await api<Me>('/me'); setCsrf(me.value.csrf_token) }
  async function login(email: string, password: string) {
    const data = await api<{ csrf_token: string }>('/auth/login', 'POST', { email, password })
    setCsrf(data.csrf_token); await load()
  }
  async function logout() { await api('/auth/logout', 'POST'); clear() }
  function clear() { me.value = null; setCsrf('') }
  return { me, load, login, logout, clear }
})
