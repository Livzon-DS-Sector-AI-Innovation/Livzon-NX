import { afterEach, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { POST } from './route'

function switchRequest(operation: 'start' | 'exit', origin = 'https://workspace.test') {
  return new NextRequest(`https://workspace.test/auth/impersonation/${operation}`, {
    method: 'POST',
    headers: { Origin: origin, Cookie: 'auth_token=synthetic-login; unrelated=ignored' },
    body: operation === 'start' ? JSON.stringify({ target_id: 'synthetic-target' }) : undefined,
  })
}

afterEach(() => vi.unstubAllGlobals())

it('rejects a cross-origin start before calling the identity API', async () => {
  const backend = vi.fn()
  vi.stubGlobal('fetch', backend)
  const result = await POST(switchRequest('start', 'https://other.test'), { params: Promise.resolve({ operation: 'start' }) })
  expect(result.status).toBe(403)
  expect(backend).not.toHaveBeenCalled()
})

it('forwards the upstream switch cookie without exposing it to JavaScript', async () => {
  const backend = vi.fn().mockResolvedValue(new Response('{"data":{"expires_at":"2030-01-01T00:00:00Z"}}', {
    headers: { 'Set-Cookie': 'impersonation_token=synthetic-switch; HttpOnly; Secure; Path=/' },
  }))
  vi.stubGlobal('fetch', backend)
  const result = await POST(switchRequest('start'), { params: Promise.resolve({ operation: 'start' }) })
  expect(result.status).toBe(200)
  expect(result.headers.getSetCookie()).toEqual(['impersonation_token=synthetic-switch; HttpOnly; Secure; Path=/'])
  expect(await result.text()).not.toContain('synthetic-switch')
  expect(backend).toHaveBeenCalledWith(expect.stringContaining('/identity/auth/impersonation/start'), expect.objectContaining({
    headers: expect.any(Headers),
    body: JSON.stringify({ target_id: 'synthetic-target' }),
  }))
  const sent = backend.mock.calls[0][1].headers
  expect(sent.get('cookie')).toBe('auth_token=synthetic-login')
})
