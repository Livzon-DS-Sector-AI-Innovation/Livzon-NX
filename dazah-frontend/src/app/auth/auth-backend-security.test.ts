import { NextRequest } from 'next/server'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { POST as callback } from './callback/route'
import { POST as localLogin } from './local-login/route'
import { GET as logout } from './logout/route'

beforeEach(() => {
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('API_BASE_URL', 'http://trusted.test:8000')
  vi.stubEnv('LOCAL_LOGIN_MODE', 'enabled')
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

it.each([['local-login', localLogin], ['callback', callback]] as const)(
  '%s sends the password only once and disallows upstream redirects',
  async (path, handler) => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('connection failed'))
    vi.stubGlobal('fetch', fetchMock)
    const request = new NextRequest(`https://factory.test/auth/${path}`, {
      method: 'POST',
      headers: { origin: 'https://factory.test' },
      body: new URLSearchParams({ username: 'audit-user', password: 'synthetic-password' }),
    })
    const response = await handler(request)
    expect(response.status).toBe(303)
    expect(response.headers.get('location')).toContain('local_login_failed')
    expect(response.headers.get('set-cookie')).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://trusted.test:8000/api/v1/identity/auth/local/login',
      expect.objectContaining({ redirect: 'error', method: 'POST' }),
    )
  },
)

it.each([['local-login', localLogin], ['callback', callback]] as const)(
  '%s rejects cross-origin login forms before forwarding credentials',
  async (path, handler) => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const sourceHeaders: Record<string, string>[] = [
      { origin: 'https://attacker.test' },
      { origin: 'https://sibling.factory.test', 'sec-fetch-site': 'same-site' },
      { origin: 'null' },
      { 'sec-fetch-site': 'cross-site' },
      {},
    ]
    for (const headers of sourceHeaders) {
      const response = await handler(new NextRequest(`https://factory.test/auth/${path}`, {
        method: 'POST', headers,
        body: new URLSearchParams({ username: 'attacker', password: 'synthetic' }),
      }))
      expect(response.status).toBe(403)
      expect(response.headers.get('set-cookie')).toBeNull()
    }
    expect(fetchMock).not.toHaveBeenCalled()
  },
)

it('logout sends the bearer only once and retains the session on failure', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('connection failed'))
  vi.stubGlobal('fetch', fetchMock)
  const response = await logout(new NextRequest('https://factory.test/auth/logout', {
    headers: { cookie: 'auth_token=synthetic' },
  }))
  expect(response.status).toBe(503)
  expect(response.headers.get('set-cookie')).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(fetchMock).toHaveBeenCalledWith(
    'http://trusted.test:8000/api/v1/identity/auth/session/logout',
    expect.objectContaining({ redirect: 'error', headers: { Authorization: 'Bearer synthetic' } }),
  )
})
