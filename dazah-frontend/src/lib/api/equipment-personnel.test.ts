import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchCandidates, fetchPersonnelList } from './equipment-personnel'

const revalidatePathSpy = vi.hoisted(() => vi.fn())
vi.mock('next/cache', () => ({ revalidatePath: revalidatePathSpy }))
vi.mock('@/lib/auth', () => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer t' }),
}))

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function lastUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls.at(-1)?.[0] ?? '')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('equipment-personnel workshop scoping', () => {
  it('fetches personnel list with workshop filter and maps pagination meta', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({
        code: 200,
        data: [{ id: 'p1', name: '张三', workshop_code: '101-2' }],
        meta: { total: 1, page: 1, page_size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchPersonnelList({ workshop: '101-2', keyword: '张' })
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/personnel?')).toBe(true)
    expect(url).toContain('workshop=101-2')
    expect(url).toContain('keyword=')
    expect(result).toMatchObject({ total: 1 })
  })

  it('omits workshop when not provided (跨车间查询)', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchPersonnelList({ page: 1 })
    expect(lastUrl(fetchMock)).not.toContain('workshop')
  })

  it('fetches candidates with workshop filter', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [{ personnel_id: 'p1', name: '李四', roles: [] }] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const candidates = await fetchCandidates(
      ['maintenance_tech'],
      undefined,
      '201-1',
    )
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/personnel/candidates?')).toBe(true)
    expect(url).toContain('role_codes=maintenance_tech')
    expect(url).toContain('workshop=201-1')
    expect(candidates).toHaveLength(1)
  })

  it('surfaces a readable error when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Response('Internal Server Error', { status: 500 })),
    )
    await expect(fetchPersonnelList({ workshop: '101-2' })).rejects.toThrow(
      '请求失败: 500',
    )
  })
})

describe('equipment-personnel actions', () => {
  it('createRole revalidates the real /equipment/personnel page route', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { id: 'r-1' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { createRole } = await import('@/actions/equipment-personnel')
    await expect(createRole({ name: '维修工', code: 'fixture' })).resolves.toEqual({ ok: true, data: { id: 'r-1' } })

    // 人员配置页收敛为真实路由后，写操作必须按页面路由失效缓存
    expect(revalidatePathSpy).toHaveBeenCalledWith('/equipment/personnel', 'page')
  })

  it.each([
    [409, 'EQUIPMENT_ROLE_CODE_EXISTS', '角色编码已存在，请换一个编码后重试'],
    [409, 'UNKNOWN', '数据已发生变化，请刷新后重试'],
    [403, 'EQUIPMENT_ROLE_CODE_EXISTS', '没有执行此操作的权限，请联系管理员'],
    [422, null, '填写内容有误，请检查后重试'],
  ])('uses the shared role-write feedback for HTTP %i', async (status, code, message) => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({
      message: '上游错误详情', detail: code ? { error_code: code } : null,
    }, status)))
    const { createRole } = await import('@/actions/equipment-personnel')
    await expect(createRole({ name: '维修工', code: 'fixture' })).resolves.toEqual({ ok: false, message })
    expect(revalidatePathSpy).not.toHaveBeenCalled()
  })
})
