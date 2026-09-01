import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

const coverageThresholds = {
  // Vitest thresholds are percentage points, not ratios.
  lines: 4.7,
  functions: 4.8,
  branches: 3.6,
  statements: 4.5,
} as const

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
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.d.ts',
        'src/types/generated/**',
      ],
      reporter: ['text-summary', 'json-summary', 'cobertura'],
      thresholds: {
        // Floors are rounded down from the current full-src baseline. Keep
        // them monotonic while changed executable lines remain under the
        // stricter PR gate.
        ...coverageThresholds,
      },
    },
  },
})
