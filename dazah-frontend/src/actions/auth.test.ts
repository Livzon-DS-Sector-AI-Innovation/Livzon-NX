import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(), setCookie: vi.fn(), getCookie: vi.fn(), deleteCookie: vi.fn(),
  getAuthHeaders: vi.fn(),
  redirect: vi.fn(() => { throw new Error('NEXT_REDIRECT') }),
}))
vi.mock('next/headers', () => ({ cookies: async () => ({ set: mocks.setCookie, get: mocks.getCookie, delete: mocks.deleteCookie }) }))
vi.mock('next/navigation', () => ({ redirect: mocks.redirect }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))

import { getCurrentUser, loginWithPassword, logout } from './auth'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getAuthHeaders.mockResolvedValue({ Authorization: 'Bearer synthetic', 'X-Forwarded-For': '198.51.100.23' })
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('API_BASE_URL', 'http://trusted.test:8000')
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

it('skips the current-user request when the browser has no session credential', async () => {
  mocks.getAuthHeaders.mockResolvedValue({ 'X-Forwarded-For': '198.51.100.23' })
  expect(await getCurrentUser()).toBeNull()
  expect(mocks.fetch).not.toHaveBeenCalled()
})

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
    expect.objectContaining({ redirect: 'error', headers: { Authorization: 'Bearer synthetic', 'X-Forwarded-For': '198.51.100.23' } }),
  )
})

it('still stores the session after successful authentication', async () => {
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ data: { access_token: 'synthetic' } })))
  const form = new FormData()
  form.set('username', 'audit-user')
  form.set('password', 'synthetic-password')
  await expect(loginWithPassword({}, form)).rejects.toThrow('NEXT_REDIRECT')
  expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/identity/auth/local/login'), expect.objectContaining({
    headers: expect.objectContaining({ 'X-Forwarded-For': '198.51.100.23' }),
  }))
  expect(mocks.setCookie).toHaveBeenCalledWith('auth_token', 'synthetic', expect.objectContaining({ httpOnly: true }))
})

it('keeps the client IP when revoking a session', async () => {
  mocks.getCookie.mockReturnValueOnce({ value: 'synthetic' })
  mocks.fetch.mockResolvedValue(new Response('{}'))
  await expect(logout()).rejects.toThrow('NEXT_REDIRECT')
  expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/identity/auth/session/logout'), expect.objectContaining({
    headers: expect.objectContaining({ 'X-Forwarded-For': '198.51.100.23', Authorization: 'Bearer synthetic' }),
  }))
  expect(mocks.deleteCookie).toHaveBeenCalledWith('auth_token')
})
