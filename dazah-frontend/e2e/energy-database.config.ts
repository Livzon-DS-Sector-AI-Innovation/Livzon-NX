import { tmpdir } from 'node:os'
import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// Explicit opt-in: requires the dedicated DB fixture server, never the mock API.
export default defineConfig({
  testDir: './energy-database',
  workers: 1,
  retries: 0,
  timeout: 900_000,
  expect: { timeout: 20_000 },
  reporter: 'list',
  outputDir: '../../outputs/energy-audit-20261016/browser-results',
  use: {
    baseURL: 'http://127.0.0.1:3300',
    actionTimeout: 30_000,
    storageState: path.join(tmpdir(), 'dazah-energy-db-e2e', 'state.json'),
    // Authentication state is temporary; do not record it in traces/videos.
    trace: 'off', video: 'off', screenshot: 'only-on-failure',
  },
  projects: [{ name: 'energy-postgres', use: { ...devices['Desktop Chrome'], channel: 'chromium' } }],
})
