import { afterEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/server-api', () => ({ getBackendFallbackUrls: () => ['http://backend.test'] }))

import { GET } from './route'

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
})
