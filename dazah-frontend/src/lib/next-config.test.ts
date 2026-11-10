import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

it.each(['development', 'production'] as const)('compresses HTTP responses in %s', async (mode) => {
  vi.stubEnv('NODE_ENV', mode)
  vi.resetModules()
  const { default: config } = await import('../../next.config')
  expect(config.compress).toBe(true)
})
