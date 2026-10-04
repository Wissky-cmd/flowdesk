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
  writeFileSync(`${evidence}/${name}.json`,JSON.stringify({url:new URL(page.url()).pathname,engine:result.testEngine,
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
  }
  await page.getByLabel('工单标题').fill(`无障碍验收 ${test.info().project.name} ${Date.now()}`)
  await page.getByLabel('详细描述').fill('验证表单、编辑、附件与协作操作的可访问性。')
  await page.getByRole('button',{name:'提交工单'}).click()
  await expect(page.getByRole('heading',{name:'请求详情',exact:true})).toBeVisible()
  await audit(page,'ticket-detail')
  await page.getByRole('button',{name:'编辑详情'}).click()
  await audit(page,'ticket-edit')
  await page.getByRole('button',{name:'取消编辑'}).click()
  await page.getByRole('button',{name:'使用指南'}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await audit(page,'help-dialog')
  await page.getByRole('dialog').press('Escape')
  await page.setViewportSize({width:320,height:900})
  await page.getByRole('button',{name:'打开导航',exact:true}).click()
  await audit(page,'mobile-navigation')
})

test('keyboard navigation, focus return, reduced motion and 320px reflow', async ({page}) => {
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
  await expect(page.getByRole('button',{name:'使用指南'})).toBeFocused()
  await page.setViewportSize({width:320,height:900})
  await page.getByRole('button',{name:'打开导航',exact:true}).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.main-area')).toHaveAttribute('inert','')
  await expect(page.getByRole('button',{name:'使用指南'})).toBeInViewport()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button',{name:'使用指南'})).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button',{name:'关闭导航',exact:true}).first()).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button',{name:'打开导航',exact:true})).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  expect(await page.locator('.ribbon-lines').evaluate(el => parseFloat(getComputedStyle(el).animationDuration) <= 0.01)).toBeTruthy()
})
