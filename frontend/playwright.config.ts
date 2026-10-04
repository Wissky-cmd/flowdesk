import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const matrix = process.env.CROSS_BROWSER === '1'
const localBrowsers = resolve('../.local/playwright')
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && existsSync(localBrowsers)) process.env.PLAYWRIGHT_BROWSERS_PATH = localBrowsers
export default defineConfig({
  testDir: './tests', workers: 1, timeout: 30000,
  reporter: [['list'], ['json', { outputFile: process.env.PLAYWRIGHT_REPORT || '../docs/evidence/playwright.json' }]],
  projects: matrix ? ['chromium', 'firefox', 'webkit'].map(name => ({name, use:{browserName:name as 'chromium' | 'firefox' | 'webkit'}}))
    : [{name:'chromium', use:{browserName:'chromium', launchOptions:{executablePath:existsSync(chrome) ? chrome : existsSync(edge) ? edge : undefined}}}],
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
  },
})
