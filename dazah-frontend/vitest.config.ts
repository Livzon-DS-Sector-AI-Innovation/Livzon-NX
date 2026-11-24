import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

const coverageThresholds = {
  // Vitest thresholds are percentage points, not ratios.
  lines: 4.7,
  functions: 4.8,
  branches: 3.6,
  statements: 4.5,
} as const

const isShardedRun = process.argv.some(arg => arg === '--shard' || arg.startsWith('--shard='))

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    // 全局 setup：补齐 happy-dom 缺失的 localStorage 并声明 React 19 act 环境
    setupFiles: ['./vitest.setup.ts'],
    // The merged production page tests exercise Ant Design portals and
    // React 19 effects; under the full coverage worker fan-out they can
    // legitimately exceed Vitest's 5s default even though they are fast in
    // isolation. Keep a bounded suite-wide timeout instead of flaky failures.
    testTimeout: 15000,
    // Vitest forwards worker console output over RPC. Under the coverage run the
    // heavy Ant Design warning burst can race with worker teardown and fail the
    // job with EnvironmentTeardownError even though every test passed. Printing
    // worker console output directly removes that RPC hop without hiding results.
    disableConsoleIntercept: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.d.ts',
        'src/types/generated/**',
      ],
      // Shards emit coverage maps via the blob reporter. Apply the full-src
      // floors and write reports when the maps are merged or the suite runs whole.
      reporter: isShardedRun ? [] : ['text-summary', 'json-summary', 'cobertura'],
      thresholds: isShardedRun ? undefined : coverageThresholds,
    },
  },
})
