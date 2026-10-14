import { afterEach, describe, expect, it, vi } from 'vitest'
const auth = vi.hoisted(() => ({ getAuthHeaders: vi.fn() }))
vi.mock('@/lib/auth', () => auth)
vi.mock('@/lib/server-api', () => ({ serverApiUrl: (path: string) => `http://test/api/v1${path}` }))
import { processFeedback, submitFeedback } from './feedback'

afterEach(() => { vi.unstubAllGlobals(); vi.resetAllMocks() })

describe('feedback server actions', () => {
  it('forwards multipart screenshots with server authentication', async () => {
    auth.getAuthHeaders.mockResolvedValue({ Authorization: 'Bearer test-session', 'Content-Type': 'application/json' })
    const fetcher = vi.fn().mockResolvedValue(Response.json({ id: 'test-feedback' }))
    vi.stubGlobal('fetch', fetcher)
    const body = new FormData()
    body.set('description', '页面发生保存错误，无法保存。')
    expect((await submitFeedback(body)).success).toBe(true)
    expect(fetcher.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
    expect(fetcher.mock.calls[0][1].body).toBe(body)
  })

  it('returns validation errors without losing user input', async () => {
    auth.getAuthHeaders.mockResolvedValue({ Authorization: 'Bearer test-session' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: '请上传有效截图' }, { status: 422 })))
    expect(await submitFeedback(new FormData())).toEqual({ success: false, error: '请上传有效截图' })
  })

  it('handles unavailable service and missing authentication', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('network failure'))
    vi.stubGlobal('fetch', fetcher)
    auth.getAuthHeaders.mockResolvedValue({})
    expect((await submitFeedback(new FormData())).success).toBe(false)
    expect(fetcher).not.toHaveBeenCalled()
    auth.getAuthHeaders.mockResolvedValue({ Authorization: 'Bearer test-session' })
    expect(await submitFeedback(new FormData())).toEqual({ success: false, error: '反馈服务暂不可用，已保留填写内容，请稍后重试' })
  })

  it('sends the version with administrator processing and preserves conflict errors', async () => {
    auth.getAuthHeaders.mockResolvedValue({ Authorization: 'Bearer test-session', 'Content-Type': 'application/json' })
    const fetcher = vi.fn().mockResolvedValue(Response.json({ detail: '反馈已被其他管理员更新，请刷新后重试' }, { status: 409 }))
    vi.stubGlobal('fetch', fetcher)
    const payload = { status: 'resolved' as const, reply: '已修复', version: 1 }
    const result = await processFeedback('12345678-1234-1234-1234-123456789abc', payload)
    expect(result.success).toBe(false)
    expect(fetcher.mock.calls[0][1].body).toBe(JSON.stringify(payload))
  })
})
