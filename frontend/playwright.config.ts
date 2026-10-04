import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'

const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
export default defineConfig({
  testDir: './tests', workers: 1, timeout: 30000,
  reporter: [['list'], ['json', { outputFile: '../docs/evidence/playwright.json' }]],
  use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 },
    launchOptions: { executablePath: existsSync(chrome) ? chrome : existsSync(edge) ? edge : undefined },
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
  },
})
