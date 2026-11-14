import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  auth: vi.fn(),
  fetch: vi.fn(),
  revalidate: vi.fn(),
}))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.auth }))
vi.mock('@/lib/server-api', () => ({
  getServerApiBaseUrl: () => 'http://backend.test:8000',
  serverApiUrl: () => 'http://backend.test:8000',
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidate }))

import {
  createGuardianRoster,
  deleteGuardianRoster,
  exportGuardianRoster,
  exportWorkCertificates,
  getGuardianRoster,
  importGuardianRoster,
  parseGuardianRosterImport,
  updateGuardianRoster,
} from './safety'

beforeEach(() => {
  vi.resetAllMocks()
  mocks.auth.mockResolvedValue({
    Authorization: 'Bearer synthetic',
    'Content-Type': 'application/json',
  })
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

const pageKey = 'safety:ops-safety:guardian-roster'

describe('guardian roster actions', () => {
  it('getGuardianRoster 携带分页与筛选参数', async () => {
    const data = { items: [], total: 0, page: 1, page_size: 20, workshops: [] }
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'ok', data }))
    )
    const res = await getGuardianRoster({
      pageKey,
      page: 2,
      pageSize: 50,
      workshop: '103车间',
      keyword: '张',
    })
    expect(res.code).toBe(0)
    const [url] = mocks.fetch.mock.calls[0]
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=50')
    expect(url).toContain('workshop=103')
    expect(url).toContain('keyword=')
  })

  it('createGuardianRoster / updateGuardianRoster / deleteGuardianRoster 走对应方法', async () => {
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'ok', data: { id: 'g1' } }))
    )
    await createGuardianRoster({ person_name: '张三', workshop: '103' } as never, pageKey)
    expect(mocks.fetch.mock.calls[0][1].method).toBe('POST')

    await updateGuardianRoster('g1', { person_name: '李四' } as never, pageKey)
    expect(mocks.fetch.mock.calls[1][0]).toContain('/safety/guardian-roster/g1')
    expect(mocks.fetch.mock.calls[1][1].method).toBe('PUT')

    await deleteGuardianRoster('g1', pageKey)
    expect(mocks.fetch.mock.calls[2][1].method).toBe('DELETE')
  })

  it('parseGuardianRosterImport 成功/网络失败', async () => {
    const data = { sheets: [{ name: '监护人', rows: 3 }], current_total: 5 }
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'ok', data }))
    )
    const file = new File(['sheet'], 'guardian.xlsx')
    const ok = await parseGuardianRosterImport(file, pageKey)
    expect(ok.code).toBe(0)
    // multipart：Content-Type 由 fetch 生成
    const headers = mocks.fetch.mock.calls[0][1].headers
    expect(headers['Content-Type']).toBeUndefined()
    expect(headers['X-Dazah-Page-Key']).toBe(pageKey)

    mocks.fetch.mockRejectedValue(new TypeError('network down'))
    const fail = await parseGuardianRosterImport(file, pageKey)
    expect(fail.code).toBe(-1)
    expect(fail.message).toContain('网络请求失败')
  })

  it('importGuardianRoster 成功后 revalidate；HTTP 错误解析 message；网络失败兜底', async () => {
    const file = new File(['sheet'], 'guardian.xlsx')
    const data = { imported: 3, replaced: 5 }
    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'ok', data }))
    )
    const ok = await importGuardianRoster(file, ['监护人'], pageKey)
    expect(ok.code).toBe(0)
    expect(mocks.revalidate).toHaveBeenCalledWith('/safety/guardian-roster')

    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ message: '子表名无效' }), { status: 422 })
    )
    const bad = await importGuardianRoster(file, ['不存在'], pageKey)
    expect(bad.code).toBe(422)
    expect(bad.message).toBe('子表名无效')

    mocks.fetch.mockResolvedValue(new Response('oops', { status: 502 }))
    const nonJson = await importGuardianRoster(file, ['监护人'], pageKey)
    expect(nonJson.code).toBe(502)
    expect(nonJson.message).toBe('HTTP 502')

    mocks.fetch.mockRejectedValue(new TypeError('network down'))
    const down = await importGuardianRoster(file, ['监护人'], pageKey)
    expect(down.code).toBe(-1)
  })

  it('exportGuardianRoster 返回 base64；HTTP 错误/网络失败兜底', async () => {
    mocks.fetch.mockResolvedValue(new Response(new Uint8Array([1, 2, 3])))
    const ok = await exportGuardianRoster({ workshop: '103', keyword: '张' }, pageKey)
    expect(ok.code).toBe(0)
    expect(ok.data).toBe(Buffer.from([1, 2, 3]).toString('base64'))
    const [url] = mocks.fetch.mock.calls[0]
    expect(url).toContain('workshop=103')
    expect(url).toContain('keyword=')

    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ message: '无可导出数据' }), { status: 404 })
    )
    const missing = await exportGuardianRoster({}, pageKey)
    expect(missing.code).toBe(404)
    expect(missing.message).toBe('无可导出数据')

    mocks.fetch.mockResolvedValue(new Response('plain', { status: 500 }))
    const nonJson = await exportGuardianRoster({}, pageKey)
    expect(nonJson.message).toBe('HTTP 500')

    mocks.fetch.mockRejectedValue(new TypeError('network down'))
    const down = await exportGuardianRoster({}, pageKey)
    expect(down.code).toBe(-1)
  })

  it('exportWorkCertificates 返回 base64；HTTP 错误/网络失败兜底', async () => {
    mocks.fetch.mockResolvedValue(new Response(new Uint8Array([9, 9])))
    const ok = await exportWorkCertificates('safety:work-certificates')
    expect(ok.code).toBe(0)
    expect(ok.data).toBe(Buffer.from([9, 9]).toString('base64'))

    mocks.fetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: '没有持证人员' }), { status: 404 })
    )
    const missing = await exportWorkCertificates()
    expect(missing.code).toBe(404)
    expect(missing.message).toBe('没有持证人员')

    mocks.fetch.mockResolvedValue(new Response('plain', { status: 500 }))
    const nonJson = await exportWorkCertificates()
    expect(nonJson.message).toBe('HTTP 500')

    mocks.fetch.mockRejectedValue(new TypeError('network down'))
    const down = await exportWorkCertificates()
    expect(down.code).toBe(-1)
  })
})
