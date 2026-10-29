import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(), setCookie: vi.fn(),
  redirect: vi.fn(() => { throw new Error('NEXT_REDIRECT') }),
}))
vi.mock('next/headers', () => ({ cookies: async () => ({ set: mocks.setCookie }) }))
vi.mock('next/navigation', () => ({ redirect: mocks.redirect }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ Authorization: 'Bearer synthetic' }) }))

import { getCurrentUser, loginWithPassword } from './auth'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('API_BASE_URL', 'http://trusted.test:8000')
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('never retries a password against another host after a connection failure', async () => {
  mocks.fetch.mockRejectedValue(new Error('connection failed'))
  const form = new FormData()
  form.set('username', 'audit-user')
  form.set('password', 'synthetic-password')
  const result = await loginWithPassword({}, form)
  expect(result.error).toBeTruthy()
  expect(mocks.fetch).toHaveBeenCalledTimes(1)
  expect(mocks.fetch).toHaveBeenCalledWith(
    'http://trusted.test:8000/api/v1/identity/auth/local/login',
    expect.objectContaining({ redirect: 'error', method: 'POST' }),
  )
  expect(mocks.setCookie).not.toHaveBeenCalled()
})

it('never retries a bearer against another host after a connection failure', async () => {
  mocks.fetch.mockRejectedValue(new Error('connection failed'))
  expect(await getCurrentUser()).toBeNull()
  expect(mocks.fetch).toHaveBeenCalledTimes(1)
  expect(mocks.fetch).toHaveBeenCalledWith(
    'http://trusted.test:8000/api/v1/identity/me',
    expect.objectContaining({ redirect: 'error', headers: { Authorization: 'Bearer synthetic' } }),
  )
})

it('still stores the session after successful authentication', async () => {
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ data: { access_token: 'synthetic' } })))
  const form = new FormData()
  form.set('username', 'audit-user')
  form.set('password', 'synthetic-password')
  await expect(loginWithPassword({}, form)).rejects.toThrow('NEXT_REDIRECT')
  expect(mocks.setCookie).toHaveBeenCalledWith('auth_token', 'synthetic', expect.objectContaining({ httpOnly: true }))
})
