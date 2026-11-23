import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchRepairConfig,
  fetchRepairFrequency,
  fetchRepairRecords,
  fetchRepairResults,
  fetchRepairSyncStatus,
  testRepairConfig,
  triggerRepairSync,
  updateRepairConfig,
} from './repair-ledger'

const BASE = '/api/v1/equipment/repair'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 固定返回给定响应的 fetch mock（带类型，便于断言请求地址与方法） */
const mockFetch = (body: unknown, status = 200) =>
  vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    jsonResponse(body, status),
  )

const calledUrls = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.map(([url]) => url)

const calledMethods = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.map(([, init]) => init?.method)

const queryParams = (fetchMock: ReturnType<typeof mockFetch>, index = 0) =>
  new URL(fetchMock.mock.calls[index][0], 'http://test').searchParams

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('repair-ledger api', () => {
  it('fetches records with every filter and maps pagination meta', async () => {
    const fetchMock = mockFetch({
      code: 200,
      data: [{ id: 'r1' }],
      meta: { total: 41, page: 2, page_size: 20 },
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchRepairRecords({
      workshop: '201-1',
      date_from: '2026-10-25',
      keyword: '离心泵',
      equipment: '薄膜蒸发器 4',
      result: '正常运行',
      page: 2,
      page_size: 20,
    })
    expect(calledUrls(fetchMock)[0].startsWith(`${BASE}/records?`)).toBe(true)
    const params = queryParams(fetchMock)
    expect(Object.fromEntries(params)).toEqual({
      workshop: '201-1',
      date_from: '2026-10-25',
      keyword: '离心泵',
      equipment: '薄膜蒸发器 4',
      result_status: '正常运行',
      page: '2',
      page_size: '20',
    })
    expect(result).toEqual({ items: [{ id: 'r1' }], total: 41, page: 2, page_size: 20 })
  })

  it('omits empty filters and defaults to the first page', async () => {
    const fetchMock = mockFetch({ code: 200, data: [], meta: { total: 0 } })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchRepairRecords()
    expect(calledUrls(fetchMock)).toEqual([`${BASE}/records?page=1&page_size=20`])
    expect(result).toEqual({ items: [], total: 0, page: 1, page_size: 20 })
  })

  it('surfaces the server error message on non-2xx responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ message: '当前账号无权查询该车间' }, 403))

    await expect(fetchRepairRecords({ workshop: '203' })).rejects.toThrow(
      '当前账号无权查询该车间',
    )
  })

  it('reads the frequency ranking with its limit and date range', async () => {
    const ranking = [
      { equipment_text: '离心泵A', times: 4, last_repaired_at: '2026-11-20' },
      { equipment_text: '薄膜蒸发器 4', times: 2, last_repaired_at: '2026-11-18' },
    ]
    const fetchMock = mockFetch({ code: 200, data: ranking })
    vi.stubGlobal('fetch', fetchMock)

    expect(await fetchRepairFrequency('201-1', '2026-10-25')).toEqual(ranking)
    expect(calledUrls(fetchMock)[0].startsWith(`${BASE}/frequency?`)).toBe(true)
    expect(Object.fromEntries(queryParams(fetchMock))).toEqual({
      workshop: '201-1',
      limit: '10',
      date_from: '2026-10-25',
    })
  })

  it('reads sync status, result options and config for one workshop', async () => {
    const state = {
      workshop_code: '201-1',
      total_rows: 8,
      last_synced_at: null,
      last_run_at: null,
      last_status: null,
      last_message: null,
      enabled: false,
    }
    const fetchMock = mockFetch({ code: 200, data: state })
    vi.stubGlobal('fetch', fetchMock)

    expect(await fetchRepairSyncStatus('201-1')).toEqual(state)
    expect(await fetchRepairConfig('201-1')).toEqual(state)
    expect(await fetchRepairResults('201-1')).toEqual(state)
    expect(calledUrls(fetchMock)).toEqual([
      `${BASE}/sync-status?workshop=201-1`,
      `${BASE}/config?workshop=201-1`,
      `${BASE}/results?workshop=201-1`,
    ])
  })

  it('triggers a manual sync and a connection test with POST', async () => {
    const fetchMock = mockFetch({ code: 200, data: { '201-1': { synced: 8, total: 8 } } })
    vi.stubGlobal('fetch', fetchMock)

    expect(await triggerRepairSync('201-1')).toEqual({ '201-1': { synced: 8, total: 8 } })
    expect(await testRepairConfig('201-1')).toEqual({ '201-1': { synced: 8, total: 8 } })
    expect(calledUrls(fetchMock)).toEqual([
      `${BASE}/sync?workshop=201-1`,
      `${BASE}/config/test?workshop=201-1`,
    ])
    expect(calledMethods(fetchMock)).toEqual(['POST', 'POST'])
    // 无请求体的 POST 不带 Content-Type
    expect(fetchMock.mock.calls.every(([, init]) => init?.body === undefined)).toBe(true)
  })

  it('rejects when the response envelope reports a business failure', async () => {
    vi.stubGlobal('fetch', mockFetch({ code: 500, message: '飞书多维表格访问失败' }))

    await expect(triggerRepairSync('201-1')).rejects.toThrow('飞书多维表格访问失败')
  })

  it('saves the config with PUT and a JSON body', async () => {
    const detail = {
      workshop_code: '201-1',
      feishu_app_id: 'app-1',
      app_name: '',
      app_id: '',
      app_secret_masked: '',
      app_secret_configured: true,
      app_token: 'bascn123',
      table_id: 'tblABC',
      base_url: '',
      is_enabled: true,
      enabled: true,
      last_test_status: null,
      last_test_error: null,
      last_tested_at: null,
    }
    const fetchMock = mockFetch({ code: 200, data: detail })
    vi.stubGlobal('fetch', fetchMock)

    const payload = {
      feishu_app_id: 'app-1',
      app_token: 'bascn123',
      table_id: 'tblABC',
      base_url: '',
      is_enabled: true,
    }
    expect(await updateRepairConfig('201-1', payload)).toEqual(detail)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${BASE}/config?workshop=201-1`)
    expect(init?.method).toBe('PUT')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init?.body as string)).toEqual(payload)
  })
})
