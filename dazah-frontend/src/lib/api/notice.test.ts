import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

import {
  deleteNotice,
  fetchNoticeContent,
  fetchNoticeDetail,
  fetchNoticeList,
  noticeFileUrl,
  updateNotice,
} from './notice'

describe('notice 台账领域 API', () => {
  it('fetchNoticeList 携带分页/关键词/分类查询参数', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data: { items: [], total: 0 } })),
    )
    await fetchNoticeList({ page: 2, page_size: 50, keyword: '安全', category: '通知' })
    const [url] = mocks.fetch.mock.calls[0]
    expect(String(url)).toContain('/api/v1/administration/notices?')
    expect(String(url)).toContain('page=2')
    expect(String(url)).toContain('page_size=50')
    expect(String(url)).toContain('keyword=')
    expect(String(url)).toContain('category=')
  })

  it('fetchNoticeDetail / fetchNoticeContent 编码 id', async () => {
    mocks.fetch.mockImplementation(async () =>
      new Response(JSON.stringify({ data: { id: 'n-1' } })),
    )
    await fetchNoticeDetail('n/1')
    expect(mocks.fetch.mock.calls[0][0]).toContain('/api/v1/administration/notices/n%2F1')

    await fetchNoticeContent('n-1')
    expect(mocks.fetch.mock.calls[1][0]).toContain('/n-1/content')
  })

  it('noticeFileUrl 返回 operate 专用原文直链', () => {
    expect(noticeFileUrl('n-1')).toBe('/api/v1/administration/notices/n-1/file')
  })

  it('updateNotice 走 PUT 携带 JSON 体', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data: { id: 'n-1' } })),
    )
    await updateNotice('n-1', { title: '新标题' } as never)
    const [url, init] = mocks.fetch.mock.calls[0]
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ title: '新标题' })
  })

  it('deleteNotice 走 DELETE 且不抛错', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data: { deleted: true } })),
    )
    await expect(deleteNotice('n-1')).resolves.toBeUndefined()
    expect(mocks.fetch.mock.calls[0][1].method).toBe('DELETE')
  })

  it('响应 detail 为对象时取 detail.message；纯网络错误带状态码', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { message: '无 operate 权限' } }),
        { status: 403 },
      ),
    )
    await expect(fetchNoticeDetail('n-1')).rejects.toThrow('无 operate 权限')

    mocks.fetch.mockResolvedValue(new Response(null, { status: 502 }))
    await expect(fetchNoticeDetail('n-1')).rejects.toThrow('请求失败（502）')
  })
})
