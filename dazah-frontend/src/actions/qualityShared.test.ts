import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'quality-shared-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))

import { actionFetch } from './quality-shared'

describe('quality shared action transport', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('handles JSON, no-content, form uploads and protected error bodies', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { id: 'record-1' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { reason: '范围不允许' } }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: '请求失败' }), { status: 400 }))
      .mockResolvedValueOnce(new Response('not-json', { status: 500 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(actionFetch('/quality/records')).resolves.toEqual({ id: 'record-1' })
    await expect(actionFetch('/quality/records/record-1', { method: 'DELETE' })).resolves.toBeNull()
    const upload = new FormData()
    upload.append('file', new File(['data'], 'quality.pdf'))
    await expect(actionFetch('/quality/records/import', { method: 'POST', body: upload })).rejects.toThrow('范围不允许')
    await expect(actionFetch('/quality/records/1', { method: 'PUT', body: '{}' })).rejects.toThrow('请求失败')
    await expect(actionFetch('/quality/records/2')).rejects.toThrow('500')

    const firstInit = fetchMock.mock.calls[0][1] as RequestInit
    expect(firstInit.headers).toMatchObject({ Authorization: 'Bearer quality-shared-token', 'Content-Type': 'application/json' })
    const uploadInit = fetchMock.mock.calls[2][1] as RequestInit
    expect(uploadInit.headers).toEqual({ Authorization: 'Bearer quality-shared-token' })
  })
})
