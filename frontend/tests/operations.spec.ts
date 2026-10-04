import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const wid = 'f441fe89-3299-51c1-ab7b-1a23105e255f', evidence = '../docs/evidence/phase-three'
const password: string = process.env.SEED_PASSWORD || JSON.parse(readFileSync('../.local/credentials.json','utf8')).seed
mkdirSync(evidence,{recursive:true})
async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('邮箱',{exact:true}).fill('admin@flowdesk.example')
  await page.getByLabel('密码',{exact:true}).fill(password)
  await page.getByRole('button',{name:'登录 FlowDesk'}).click()
  await expect(page.getByRole('heading',{name:/你好/})).toBeVisible()
}
test('task center executes real database export and exposes downloadable result', async ({page}) => {
  await login(page)
  await page.goto(`/w/${wid}/jobs`)
  const created = page.waitForResponse(r => r.url().endsWith('/exports') && r.request().method() === 'POST')
  await page.getByRole('button',{name:'导出工单 CSV'}).click()
  const response = await created
  expect(response.status()).toBe(202)
  const job = await response.json() as {id:string}
  // Execute the production job function against the development DB, not a fake result.
  // Linux Celery/Redis transport is separately verified by scripts/queue_smoke.py in CI.
  const python = process.platform === 'win32' ? resolve('../.venv/Scripts/python.exe') : 'python'
  execFileSync(python,['-c','import sys; from app.job_runtime import execute_job; execute_job(sys.argv[1])', job.id],{cwd:resolve('..'),env:{...process.env,PYTHONPATH:resolve('../backend')},timeout:15000,stdio:'pipe'})
  await page.getByRole('button',{name:'刷新任务'}).click()
  const card = page.locator('.job-card').filter({hasText:job.id.slice(0,8).toUpperCase()})
  await expect(card.getByText('导出完成')).toBeVisible()
  const downloadEvent = page.waitForEvent('download')
  await card.getByRole('link',{name:'下载 CSV'}).click()
  const download = await downloadEvent
  expect(readFileSync((await download.path())!,'utf8')).toContain('编号,标题,状态')
  await card.getByRole('button',{name:'查看记录'}).click()
  await expect(page.getByText('文件已生成')).toBeVisible()
  await page.getByRole('dialog').press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.screenshot({path:`${evidence}/jobs-desktop.png`,fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByRole('navigation',{name:'主导航'})).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({path:`${evidence}/jobs-mobile.png`,fullPage:true})
})
test('token shown once, scope limited, revoked; mobile settings layout', async ({page}) => {
  await login(page)
  await page.goto(`/w/${wid}/integrations`)
  const name = `浏览器验收只读集成 ${Date.now()}`
  await page.getByLabel('用途名称').fill(name)
  await page.getByRole('button',{name:'创建令牌',exact:true}).click()
  await expect(page.getByRole('heading',{name:'保存你的集成令牌'})).toBeVisible()
  // Never screenshot, log or save the one-time token.
  await expect(page.getByLabel('集成令牌',{exact:true})).toHaveValue(/^fd_/)
  await page.getByRole('button',{name:'已保存，关闭'}).click()
  const card = page.locator('.job-card').filter({hasText:name})
  await expect(card).toBeVisible()
  await card.getByRole('button',{name:'撤销令牌'}).click()
  await expect(card.getByText('已撤销',{exact:true})).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading',{name:/连接你的工作流/})).toBeVisible()
  await expect(page.locator('.job-card').filter({hasText:name}).getByText('已撤销',{exact:true})).toBeVisible()
  await expect(page.getByLabel('集成令牌',{exact:true})).toHaveCount(0)
  await page.screenshot({path:`${evidence}/integrations-desktop.png`,fullPage:true})
  await page.setViewportSize({width:320,height:844})
  await expect(page.getByRole('navigation',{name:'主导航'})).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({path:`${evidence}/integrations-mobile.png`,fullPage:true})
})
