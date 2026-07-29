import { defineConfig } from 'vitest/config'

export default defineConfig({
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
        // Initial full-src baseline. Keep these floors monotonic while changed
        // executable lines are held to the stricter PR gate.
        lines: 0.15,
        functions: 0.14,
        branches: 0.17,
        statements: 0.15,
      },
    },
  },
})
