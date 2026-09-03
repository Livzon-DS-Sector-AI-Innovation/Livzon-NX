import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { GET } from './route'

describe('authentication callback route', () => {
  it('verifies the user before choosing the first visible module', async () => {
    const request = new NextRequest(
      'https://factory.test/auth/callback?token=test-token&next=%2Fquality',
    )

    const response = await GET(request)

    expect(response.status).toBe(303)
    expect(response.headers.get('location')).toBe(
      'https://factory.test/login/complete?next=%2Fquality',
    )
    expect(response.headers.get('set-cookie')).toContain('auth_token=test-token')
  })
})
