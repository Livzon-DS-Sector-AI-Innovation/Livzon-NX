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
