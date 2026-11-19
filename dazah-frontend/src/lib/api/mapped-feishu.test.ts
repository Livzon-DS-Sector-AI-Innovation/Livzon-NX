import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))

vi.mock('@/lib/server-api', () => ({
  serverApiUrl: (path: string) => `http://backend.test:8000${path}`,
}))

import { fetchPersonAvatars, mappedAttachmentUrl } from './mapped-feishu'

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

describe('mapped-feishu 领域 API', () => {
  it('fetchPersonAvatars 空邮箱直接返回空对象（不发请求）', async () => {
    const result = await fetchPersonAvatars('administration', [])
    expect(result).toEqual({})
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('fetchPersonAvatars 携带全部邮箱查询参数并返回映射', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          data: { 'zhang@plant.com': 'https://img/z.png', 'li@plant.com': '' },
        }),
      ),
    )
    const result = await fetchPersonAvatars('administration', [
      'zhang@plant.com',
      'li@plant.com',
    ])
    expect(result['zhang@plant.com']).toBe('https://img/z.png')
    const [url, init] = mocks.fetch.mock.calls[0]
    expect(String(url)).toContain(
      '/api/v1/administration/feishu-read/person-avatars',
    )
    expect(String(url)).toContain('emails=zhang%40plant.com')
    expect(String(url)).toContain('emails=li%40plant.com')
    expect(init.cache).toBe('no-store')
  })

  it('fetchPersonAvatars 非 2xx 时抛业务错误信息', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ message: '镜像未同步' }), { status: 503 }),
    )
    await expect(
      fetchPersonAvatars('administration', ['x@plant.com']),
    ).rejects.toThrow('镜像未同步')
  })

  it('mappedAttachmentUrl 编码页键/记录/字段/文件令牌', () => {
    const url = mappedAttachmentUrl(
      'administration',
      'seals:main',
      'bind-1',
      'rec/001',
      '照片',
      'tok#1',
    )
    expect(url).toBe(
      'http://backend.test:8000/api/v1/administration/page-data/' +
        'seals%3Amain/bind-1/record/rec%2F001' +
        '/attachments/%E7%85%A7%E7%89%87/tok%231',
    )
  })
})
