import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { isTrustedBrowserWriteRequest } from './public-origin'

describe('browser write source checks', () => {
  it.each([
    [{ origin: 'https://factory.test' }, true],
    [{ referer: 'https://factory.test/login?next=/production' }, true],
    [{ origin: 'https://attacker.test', referer: 'https://factory.test/login' }, false],
    [{ referer: 'https://factory.test.attacker.test/login' }, false],
    [{ referer: 'invalid' }, false],
    [{ origin: 'null' }, false],
    [{ origin: 'https://factory.test', 'sec-fetch-site': 'cross-site' }, false],
    [{}, false],
  ] as const)('checks explicit browser evidence %j', (headers, allowed) => {
    expect(isTrustedBrowserWriteRequest(new NextRequest('https://factory.test/auth/local-login', {
      method: 'POST', headers,
    }))).toBe(allowed)
  })

  it('uses the external origin supplied by the reverse proxy', () => {
    expect(isTrustedBrowserWriteRequest(new NextRequest('http://frontend:3000/auth/local-login', {
      method: 'POST', headers: {
        'x-forwarded-proto': 'https', 'x-forwarded-host': 'factory.test',
        origin: 'https://factory.test',
      },
    }))).toBe(true)
  })
})
