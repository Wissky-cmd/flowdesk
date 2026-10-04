import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const password: string = process.env.SEED_PASSWORD || JSON.parse(readFileSync('../.local/credentials.json', 'utf8')).seed
async function login(page: Page, who: string) {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(`${who}@flowdesk.example`)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录 FlowDesk' }).click()
  await expect(page.getByRole('heading', { name: `你好，` })).toBeVisible()
}

test('browser login, create, list, refresh, and separate workspace isolation', async ({ page, browser }) => {
  await login(page, 'alice')
  await page.getByRole('link', { name: /产品与研发/ }).click()
  const listUrl = page.url()
  await page.getByRole('button', { name: '创建工单' }).click()
  const title = `浏览器验收：团队访问请求 ${Date.now()}`
  await page.getByLabel('工单标题').fill(title)
  await page.getByLabel('详细描述').fill('通过真实浏览器创建，刷新后仍应可见；另一空间用户不得读取。')
  await page.getByRole('button', { name: '提交工单' }).click()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  const detailUrl = page.url()
  await page.reload()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  await page.screenshot({ path: '../docs/evidence/ticket-detail.png', fullPage: true })
  await page.goto(listUrl)
  await expect(page.getByRole('link', { name: title })).toBeVisible()
  await page.screenshot({ path: '../docs/evidence/ticket-list.png', fullPage: true })
  const context = await browser.newContext()
  const other = await context.newPage()
  await login(other, 'other')
  const denied = other.waitForResponse(r => r.url().includes('/api/v1/workspaces/') && r.url().includes('/tickets/'))
  await other.goto(detailUrl)
  expect((await denied).status()).toBe(404)
  await expect(other.getByText('工作空间或资源不存在')).toBeVisible()
  await expect(other.getByRole('heading', { name: title })).toHaveCount(0)
  await other.screenshot({ path: '../docs/evidence/permission-denied.png', fullPage: true })
  await context.close()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录工作台' })).toBeVisible()
})

test('login errors and mobile layout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill('admin@flowdesk.example')
  await page.getByLabel('密码', { exact: true }).fill('wrong-password')
  await page.getByRole('button', { name: '登录 FlowDesk' }).click()
  await expect(page.getByText('邮箱或密码错误')).toBeVisible()
  await page.screenshot({ path: '../docs/evidence/login-mobile.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
})
