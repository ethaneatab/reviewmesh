import { defineConfig } from '@playwright/test'

// Needs the stack from scripts/demo.sh (frontend on 5189).
export default defineConfig({
  testDir: 'e2e',
  timeout: 90_000,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: process.env.RM_UI_URL || 'http://127.0.0.1:5189', headless: true, viewport: { width: 1400, height: 900 } },
})
