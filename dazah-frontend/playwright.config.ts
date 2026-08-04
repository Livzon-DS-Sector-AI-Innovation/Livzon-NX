import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'html',
  webServer: [
    {
      command: 'node e2e/mock-api-server.mjs',
      url: 'http://127.0.0.1:4100/health',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: process.env.CI
        ? 'node scripts/start-standalone.mjs'
        : 'pnpm dev --port 3200',
      url: 'http://127.0.0.1:3200',
      env: {
        API_BASE_URL: 'http://127.0.0.1:4100',
        HOSTNAME: '127.0.0.1',
        PORT: '3200',
      },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:3200',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chromium' },
    },
  ],
})
