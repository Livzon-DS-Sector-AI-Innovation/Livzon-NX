import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
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
      command: 'pnpm dev --port 3200',
      url: 'http://127.0.0.1:3200',
      env: {
        API_BASE_URL: 'http://127.0.0.1:4100',
      },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:3200',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chromium' },
    },
  ],
})
