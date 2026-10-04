import {test, expect, type Page} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {readFileSync, mkdirSync, writeFileSync} from 'node:fs'

const password = process.env.SEED_PASSWORD || JSON.parse(readFileSync('../.local/credentials.json','utf8')).seed
const base = '/w/f441fe89-3299-51c1-ab7b-1a23105e255f'
async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('邮箱',{exact:true}).fill('admin@flowdesk.example')
  await page.getByLabel('密码',{exact:true}).fill(password)
  await page.getByRole('button',{name:'登录 FlowDesk'}).click()
  await expect(page.getByRole('heading',{name:/你好/})).toBeVisible()
}
async function audit(page: Page, name: string) {
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']).analyze()
  const evidence = `../docs/evidence/accessibility/${test.info().project.name}`
  mkdirSync(evidence,{recursive:true})
  // Store selectors and rule IDs, never DOM HTML or form values (tokens/passwords).
  const compact = (rules: typeof result.violations) => rules.map(r => ({id:r.id,impact:r.impact,help:r.help,targets:r.nodes.map(n => n.target)}))
  writeFileSync(`${evidence}/${name}.json`,JSON.stringify({url:new URL(page.url()).pathname,engine:result.testEngine,browser:page.context().browser()?.version(),
    violations:compact(result.violations),incomplete:compact(result.incomplete),passedRules:result.passes.length},null,2))
  expect.soft(result.violations.map(r => ({id:r.id,targets:r.nodes.map(n => n.target)})),name).toEqual([])
}

test('WCAG audit of every view and interactive form states', async ({page}) => {
  test.setTimeout(180000)
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.goto('/login')
  await audit(page,'login')
  await login(page)
  await audit(page,'workspaces')
  for (const route of ['tickets','board','jobs','integrations','members','tickets/new']) {
    await page.goto(`${base}/${route}`)
    await expect(page.locator('h1')).toBeVisible()
    await audit(page,route.replace('/','-'))
    if (route === 'members' || route === 'tickets/new') {
      const label = route === 'members' ? '空间角色' : '优先级'
      const select = page.locator(route === 'members' ? '#member-role' : '#priority')
      await expect(select).toHaveAccessibleName(new RegExp(label))
      await select.focus()
      await page.keyboard.press('ArrowDown')
      await expect(page.getByRole('listbox')).toBeVisible()
      await audit(page,route.replace('/','-')+'-options')
      await page.keyboard.press('Escape')
    }
  }
  await page.getByLabel('工单标题').fill(`无障碍验收 ${test.info().project.name} ${Date.now()}`)
  await page.getByLabel('详细描述').fill('验证表单、编辑、附件与协作操作的可访问性。')
  await page.getByRole('button',{name:'提交工单'}).click()
  await expect(page.getByRole('heading',{name:'请求详情',exact:true})).toBeVisible()
  // Keyboard users use the visible upload button, never a transparent 1px file input.
  await expect(page.getByLabel('选择附件')).toHaveAttribute('tabindex','-1')
  await expect(page.getByRole('button',{name:'添加附件'})).toBeVisible()
  await audit(page,'ticket-detail')
  await page.getByRole('button',{name:'编辑详情'}).click()
  await audit(page,'ticket-edit')
  await page.getByRole('button',{name:'取消编辑'}).click()
  await page.getByRole('button',{name:'使用指南'}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await audit(page,'help-dialog')
  await page.getByRole('dialog').press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.setViewportSize({width:320,height:900})
  await page.getByRole('button',{name:'打开导航',exact:true}).click()
  await expect(page.getByRole('button',{name:'使用指南'})).toBeInViewport()
  await expect(page.getByRole('navigation',{name:'主导航'}).getByRole('link',{name:/协作看板/})).toBeVisible()
  await audit(page,'mobile-navigation')
})

test('keyboard navigation, focus return, reduced motion and 320px reflow', async ({page}) => {
  const focusEvents: string[] = []
  await page.exposeFunction('recordKeyboardFocus', (value: string) => focusEvents.push(value))
  await page.addInitScript(() => {
    const record = (value: string) => (window as unknown as {recordKeyboardFocus:(value:string)=>void}).recordKeyboardFocus(value)
    document.addEventListener('focusin', event => record('focus '+(event.target as HTMLElement).className))
    document.addEventListener('keydown', event => { if (event.key==='Tab') record(`tab shift=${event.shiftKey} prevented=${event.defaultPrevented} active=${(document.activeElement as HTMLElement)?.className}`) })
  })
  await page.emulateMedia({reducedMotion:'reduce'})
  await login(page)
  await page.goto(`${base}/tickets`)
  await expect(page.getByRole('heading',{name:'工单中心.'})).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link',{name:'跳到主要内容'})).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
  await page.getByRole('button',{name:'使用指南'}).focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  for (let i=0;i<5;i++) {
    await page.keyboard.press('Tab')
    expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBeTruthy()
  }
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button',{name:'使用指南'})).toBeFocused()
  await page.setViewportSize({width:320,height:900})
  await expect(page.getByRole('button',{name:'打开导航',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'打开导航',exact:true}).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.main-area')).toHaveAttribute('inert','')
  await expect(page.getByRole('button',{name:'使用指南'})).toBeInViewport()
  await expect(page.getByRole('button',{name:'关闭导航',exact:true}).first()).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button',{name:'使用指南'}),focusEvents.slice(-12).join('\n')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button',{name:'关闭导航',exact:true}).first()).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button',{name:'打开导航',exact:true})).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  expect(await page.locator('.ribbon-lines').evaluate(el => parseFloat(getComputedStyle(el).animationDuration) <= 0.01)).toBeTruthy()
})

test('text spacing overrides and narrow reflow retain every view', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'})
  await login(page)
  await page.setViewportSize({width:320,height:900})
  for (const route of ['tickets','board','jobs','integrations','members','tickets/new']) {
    await page.goto(`${base}/${route}`)
    await expect(page.locator('h1')).toBeVisible()
    await page.addStyleTag({content:'* { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; } p { margin-bottom: 2em !important; }'})
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),route).toBeTruthy()
    await expect(page.getByRole('button',{name:'打开导航',exact:true})).toBeVisible()
  }
})

test('token, retry error and task history dialogs remain accessible', async ({page}) => {
  test.setTimeout(90000)
  await page.emulateMedia({reducedMotion:'reduce'})
  await login(page)
  // UI-only dialog audit: never create or record a real integration secret.
  await page.route('**/integration-tokens', route => route.request().method()==='POST'
    ? route.fulfill({status:201,json:{token:'fd_public-accessibility-fixture-not-a-real-secret'}}) : route.continue())
  await page.goto(`${base}/integrations`)
  await page.getByLabel('用途名称').fill('无障碍测试用占位令牌')
  await page.getByRole('button',{name:'创建令牌',exact:true}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await audit(page,'token-dialog')
  await page.getByRole('button',{name:'已保存，关闭'}).click()
  const job={id:'aaaaaaaa-accessibility',status:'failed',generation:1,attempts:1,run_attempts:1,error_code:'EXPORT_ERROR',created_at:'2026-10-05T00:00:00Z',expires_at:'2099-10-06T00:00:00Z'}
  await page.route('**/jobs?*',route => route.fulfill({json:{items:[job],total:1}}))
  await page.route('**/jobs/aaaaaaaa-accessibility',route => route.fulfill({json:{...job,delivery_attempts:1,delivery_run_attempts:1,events:[{kind:'failed',generation:1,detail:{error_code:'EXPORT_ERROR'},created_at:job.created_at}]}}))
  await page.route('**/jobs/*/retry',route => route.fulfill({status:429,json:{message:'最多同时保留 5 个待处理导出任务'}}))
  await page.goto(`${base}/jobs`)
  await page.getByRole('button',{name:'人工重试'}).click()
  await page.getByLabel('重试原因').fill('恢复后重试')
  await page.getByRole('button',{name:'确认重试'}).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible()
  await audit(page,'retry-error-dialog')
  await page.getByRole('button',{name:'取消',exact:true}).click()
  await page.getByRole('button',{name:'查看记录'}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await audit(page,'job-history-dialog')
})
