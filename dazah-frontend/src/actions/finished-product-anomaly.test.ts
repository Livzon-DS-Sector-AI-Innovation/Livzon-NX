import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth', () => ({
  getAuthHeaders: async () => ({ Authorization: 'Bearer anomaly-token' }),
}))

import { uploadAnomalyAttachment } from './finished-product-anomaly'

describe('finished product anomaly server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('uploads an attachment with the year query and returns the file ref', async () => {
    const ref = { file_token: 'ft-new', name: '证据.png' }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: ref }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    )
    const file = new File(['x'], '证据.png', { type: 'image/png' })

    await expect(uploadAnomalyAttachment(2026, file)).resolves.toEqual(ref)
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [
      string,
      RequestInit & { body: FormData },
    ]
    expect(url).toContain(
      '/api/v1/quality/finished-product-anomaly/attachments?year=2026',
    )
    expect(init.method).toBe('POST')
    expect(init.body.get('file')).toBe(file)
    expect((init.headers as Record<string, string>).Authorization).toBe(
      'Bearer anomaly-token',
    )
  })

  it('returns null when the upload responds with empty body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(
      uploadAnomalyAttachment(2025, new File(['x'], 'a.jpg', { type: 'image/jpeg' })),
    ).rejects.toThrow('未收到附件上传结果')
  })
})