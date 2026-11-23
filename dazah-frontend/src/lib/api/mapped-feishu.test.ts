import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))

vi.mock('@/lib/server-api', () => ({
  serverApiUrl: (path: string) => `http://backend.test:8000${path}`,
}))

import {
  fetchMappedPageExport,
  fetchPersonAvatars,
  mappedAttachmentUrl,
} from './mapped-feishu'

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

describe('fetchMappedPageExport 导出参数与错误', () => {
  it('携带 format/columns/sort/filters 全量查询参数并返回 Blob', async () => {
    const blob = new Blob(['xlsx-bytes'])
    mocks.fetch.mockResolvedValue(new Response(blob))
    const result = await fetchMappedPageExport('administration', 'seals:main', 'bind-1', {
      format: 'xlsx',
      columns: ['a', 'b'],
      sort_field: 'created_at',
      sort_direction: 'desc',
      filters: [{ field_id: 'f1', operator: 'is', value: '锅炉' }],
    })
    expect(result).toBeInstanceOf(Blob)
    const [url] = mocks.fetch.mock.calls[0]
    expect(String(url)).toContain('/export?')
    expect(String(url)).toContain('format=xlsx')
    expect(String(url)).toContain('columns=a%2Cb')
    expect(String(url)).toContain('sort_field=created_at')
    expect(String(url)).toContain('filter_field=f1')
    expect(String(url)).toContain('filter_value=')
  })

  it('导出失败抛业务错误信息', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ message: '镜像未同步' }), { status: 503 }),
    )
    await expect(
      fetchMappedPageExport('administration', 'seals:main', 'bind-1', { format: 'pdf' }),
    ).rejects.toThrow('镜像未同步')
  })

  it('无 message 时回退状态码文案', async () => {
    mocks.fetch.mockResolvedValue(new Response('oops', { status: 500 }))
    await expect(
      fetchMappedPageExport('administration', 'seals:main', 'bind-1', { format: 'xlsx' }),
    ).rejects.toThrow('导出失败（500）')
  })
})

describe('dormitory 镜像 API', () => {
  it('fetchDormitoryStats 走 dashboard-stats 端点', async () => {
    const data = { total_rooms: 12, occupied: 9, vacant: 3 }
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data }))
    )
    const { fetchDormitoryStats } = await import('./mapped-feishu')
    const result = await fetchDormitoryStats('administration')
    expect(result.total_rooms).toBe(12)
    expect(String(mocks.fetch.mock.calls[0][0])).toContain(
      '/api/v1/administration/dormitory/dashboard-stats'
    )
  })

  it('recommendDormitoryRooms 走 POST JSON', async () => {
    const data = {
      recommendations: [{ room_no: '301' }],
      message: '按住宿标准',
      source: 'rule',
    }
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data }))
    )
    const { recommendDormitoryRooms } = await import('./mapped-feishu')
    const result = await recommendDormitoryRooms('administration', {
      name: '张三',
    })
    expect(result.recommendations?.[0]?.room_no).toBe('301')
    const [url, init] = mocks.fetch.mock.calls[0]
    expect(String(url)).toContain('/dormitory/checkin-recommend')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ name: '张三' })
  })

  it('submitDormitoryCheckin 走 POST 且 detail 错误透出', async () => {
    const { submitDormitoryCheckin } = await import('./mapped-feishu')
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ data: { room_no: '301', synced: true } }))
    )
    const ok = await submitDormitoryCheckin('administration', {
      name: '张三',
      room_no: '301',
    } as never)
    expect(ok.synced).toBe(true)
    expect(String(mocks.fetch.mock.calls[0][0])).toContain(
      '/dormitory/checkin'
    )

    mocks.fetch.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { message: '床位已被占用' } }),
        { status: 409 },
      ),
    )
    await expect(
      submitDormitoryCheckin('administration', { name: '张三' } as never)
    ).rejects.toThrow('床位已被占用')
  })
})
