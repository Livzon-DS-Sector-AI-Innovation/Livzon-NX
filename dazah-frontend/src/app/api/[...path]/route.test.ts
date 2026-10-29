import { afterEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/server-api', () => ({ getBackendFallbackUrls: () => ['http://backend.test', 'http://fallback.test'] }))

import { GET, POST } from './route'

afterEach(() => vi.unstubAllGlobals())

describe('API proxy user feedback', () => {
  it('translates an English backend error without changing its code or status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: 403, message: 'Forbidden' }),
      { status: 403, headers: { 'content-type': 'application/json' } },
    )))

    const response = await GET(new NextRequest('http://localhost/api/v1/example'))
    expect(response.status).toBe(403)
    expect(await response.json()).toEqual({ code: 403, message: '没有执行此操作的权限，请联系管理员' })
  })

  it('returns a Chinese service error when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('fetch failed')))
    const response = await GET(new NextRequest('http://localhost/api/v1/example'))
    expect(response.status).toBe(502)
    expect((await response.json()).message).toBe('服务暂时不可用，请稍后重试')
  })

  it('never retries a write on another backend after a lost acknowledgement', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('fixture lost response after commit'))
    vi.stubGlobal('fetch', fetcher)
    const response = await POST(new NextRequest('http://localhost/api/v1/equipment/work-orders', {
      method: 'POST', body: '{}', headers: { 'X-Dazah-Operation-ID': 'fixture-operation' },
    }))
    expect(response.status).toBe(502)
    const data = await response.json()
    expect(data.message).toContain('不要重复提交')
    expect(data.message).not.toContain('查询操作结果')
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(new Headers(fetcher.mock.calls[0][1].headers).get('X-Dazah-Operation-ID')).toBe('fixture-operation')
  })

  it('can still use a fallback backend for safe reads', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error('fixture unavailable')).mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [] }), { headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetcher)
    expect((await GET(new NextRequest('http://localhost/api/v1/example'))).status).toBe(200)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('translates validation details while keeping field locations', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }] }),
      { status: 422, headers: { 'content-type': 'application/json' } },
    )))
    const response = await GET(new NextRequest('http://localhost/api/v1/example'))
    expect(await response.json()).toEqual({
      detail: [{ loc: ['body', 'name'], msg: '填写内容有误，请检查后重试', type: 'missing' }],
    })
  })

  it('forwards only allowlisted request headers to the backend', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ data: [] }),
      { headers: { 'content-type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetcher)

    await GET(new NextRequest('http://localhost/api/v1/example', {
      headers: {
        cookie: 'auth_token=secret',
        'x-forwarded-host': 'evil.example',
        'x-dazah-operation-id': 'operation-1',
      },
    }))

    const forwarded = new Headers(fetcher.mock.calls[0][1].headers)
    expect(forwarded.get('cookie')).toBe('auth_token=secret')
    expect(forwarded.get('x-dazah-operation-id')).toBe('operation-1')
    expect(forwarded.get('x-forwarded-host')).toBeNull()
  })

  it('preserves browser source evidence for backend cookie and CSRF checks', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', {
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetcher)
    await POST(new NextRequest('https://factory.test/api/v1/example', {
      method: 'POST', body: '{}', headers: {
        cookie: 'auth_token=synthetic', origin: 'https://factory.test',
        referer: 'https://factory.test/production', 'sec-fetch-site': 'same-origin',
      },
    }))
    const headers = new Headers(fetcher.mock.calls[0][1].headers)
    expect(headers.get('origin')).toBe('https://factory.test')
    expect(headers.get('referer')).toBe('https://factory.test/production')
    expect(headers.get('sec-fetch-site')).toBe('same-origin')
  })
})
