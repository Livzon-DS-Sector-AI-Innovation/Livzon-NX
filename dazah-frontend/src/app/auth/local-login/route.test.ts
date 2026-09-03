import { NextRequest } from 'next/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { POST } from './route'

describe('local login route', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('keeps the auth cookie usable when the public request uses HTTP', async () => {
    vi.stubEnv('LOCAL_LOGIN_MODE', 'enabled')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json({ data: { access_token: 'local-test-token' } }),
      ),
    )
    const request = new NextRequest('https://internal.test/auth/local-login', {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        host: 'factory.test',
        'x-forwarded-host': 'factory.test',
        'x-forwarded-proto': 'http',
      },
      body: new URLSearchParams({
        username: 'local-user',
        password: 'test-password',
        next: '/production',
      }),
    })

    const response = await POST(request)

    expect(response.status).toBe(303)
    expect(response.headers.get('location')).toBe(
      'http://factory.test/login/complete?next=%2Fproduction',
    )
    expect(response.headers.get('set-cookie')).toContain(
      'auth_token=local-test-token',
    )
    expect(response.headers.get('set-cookie')).not.toMatch(/;\s*Secure/i)
  })

  it('marks the auth cookie secure when the public request uses HTTPS', async () => {
    vi.stubEnv('LOCAL_LOGIN_MODE', 'enabled')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json({ data: { access_token: 'local-test-token' } }),
      ),
    )
    const request = new NextRequest('http://internal.test/auth/local-login', {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        host: 'factory.test',
        'x-forwarded-host': 'factory.test',
        'x-forwarded-proto': 'https',
      },
      body: new URLSearchParams({
        username: 'local-user',
        password: 'test-password',
        next: '/production',
      }),
    })

    const response = await POST(request)

    expect(response.status).toBe(303)
    expect(response.headers.get('location')).toBe(
      'https://factory.test/login/complete?next=%2Fproduction',
    )
    expect(response.headers.get('set-cookie')).toMatch(/;\s*Secure/i)
  })
})
