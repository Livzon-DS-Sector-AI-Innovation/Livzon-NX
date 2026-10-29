import { afterEach, expect, it, vi } from 'vitest'

import { getBackendFallbackUrls, getServerApiBaseUrl } from './server-api'

afterEach(() => vi.unstubAllEnvs())

it.each(['production', 'development', 'test'])('uses one configured backend in %s', (mode) => {
  vi.stubEnv('NODE_ENV', mode)
  vi.stubEnv('API_BASE_URL', 'http://trusted.test:8000/')
  expect(getBackendFallbackUrls()).toEqual(['http://trusted.test:8000'])
})

it('requires an explicit backend in production', () => {
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('API_BASE_URL', '')
  expect(() => getServerApiBaseUrl()).toThrow('API_BASE_URL')
})

it('uses only localhost for unconfigured development', () => {
  vi.stubEnv('NODE_ENV', 'development')
  vi.stubEnv('API_BASE_URL', '')
  expect(getBackendFallbackUrls()).toEqual(['http://localhost:8000'])
})
