import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

it.each([
  ['development', false],
  ['production', true],
] as const)('uses the intended HTTP compression policy for %s', async (mode, compression) => {
  vi.stubEnv('NODE_ENV', mode)
  vi.resetModules()
  const { default: config } = await import('../../next.config')
  expect(config.compress).toBe(compression)
})
