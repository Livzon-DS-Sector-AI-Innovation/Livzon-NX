import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { GET } from './route'

describe('authentication callback route', () => {
  it('rejects a login token supplied in the URL', async () => {
    const request = new NextRequest(
      'https://factory.test/auth/callback?token=test-token&next=%2Fquality',
    )

    const response = await GET(request)

    expect(response.status).toBe(303)
    expect(response.headers.get('location')).toBe('https://factory.test/login?error=invalid_login_link')
    expect(response.headers.get('set-cookie')).toBeNull()
  })
})
