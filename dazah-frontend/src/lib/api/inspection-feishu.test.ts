import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchInspectionFeishuConfig,
  fetchInspectionFeishuDevices,
  fetchInspectionFeishuRecords,
  fetchInspectionFeishuSyncStatus,
  fetchInspectionFeishuTodaySummary,
  testInspectionFeishuConfig,
  triggerInspectionFeishuSync,
  updateInspectionFeishuConfig,
} from './inspection-feishu'

const BASE = '/api/v1/equipment/inspection/feishu'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('inspection-feishu api', () => {
  it('fetches records with filters and maps pagination meta', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({
        code: 200,
        data: [{ id: 'r1' }],
        meta: { total: 41, page: 2, page_size: 20 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchInspectionFeishuRecords({
      workshop: '201-1',
      source: 'history',
      date_from: '2026-10-01',
      date_to: '2026-10-10',
      keyword: '混合机',
      abnormal_only: true,
      process_status: '已拆分',
      page: 2,
      page_size: 20,
    })
    const url = fetchMock.mock.calls[0][0] as unknown as string
    expect(url.startsWith(`${BASE}/records?`)).toBe(true)
    for (const fragment of [
      'workshop=201-1',
      'source=history',
      'date_from=2026-10-01',
      'date_to=2026-10-10',
      'keyword=%E6%B7%B7%E5%90%88%E6%9C%BA',
      'abnormal_only=true',
      'process_status=',
      'page=2',
      'page_size=20',
    ]) {
      expect(url).toContain(fragment)
    }
    expect(result).toEqual({ items: [{ id: 'r1' }], total: 41, page: 2, page_size: 20 })
  })

  it('fetches devices with an encoded keyword and parses {date, items}', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({
        code: 200,
        data: {
          date: '2026-10-13',
          items: [
            {
              record_id: 'dev-1',
              equipment_no: 'XT-A',
              today_status: 'inspected',
              last_inspected_date: '2026-10-13',
            },
          ],
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchInspectionFeishuDevices('101-2', '萃取罐')).resolves.toEqual({
      date: '2026-10-13',
      items: [expect.objectContaining({ equipment_no: 'XT-A' })],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE}/devices?workshop=101-2&keyword=${encodeURIComponent('萃取罐')}`,
    )
  })

  it('fetches the today summary and the sync status', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({
        code: 200,
        data: { date: '2026-10-10', total_devices: 49, inspected: 46, abnormal: 0 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchInspectionFeishuTodaySummary('201-1')).resolves.toMatchObject({
      total_devices: 49,
    })
    fetchMock.mockResolvedValue(
      jsonResponse({ code: 200, data: { enabled: true, tables: [] } }),
    )
    await expect(fetchInspectionFeishuSyncStatus('201-1')).resolves.toMatchObject({
      enabled: true,
    })
  })

  it('gets, saves and tests the mirror config', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({ code: 200, data: { app_id: 'cli_x', source: 'database' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchInspectionFeishuConfig('101-1')).resolves.toMatchObject({
      source: 'database',
    })
    expect(fetchMock).toHaveBeenLastCalledWith(`${BASE}/config?workshop=101-1`)

    await updateInspectionFeishuConfig('101-1', {
      app_id: 'cli_x',
      app_secret: null,
      app_token: 'bascn_x',
      today_table_id: 'tbl_a',
      history_table_id: 'tbl_b',
      device_table_id: 'tbl_c',
      is_enabled: true,
    })
    const put = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit]
    expect(put[0]).toBe(`${BASE}/config?workshop=101-1`)
    expect(put[1]).toMatchObject({ method: 'PUT' })
    expect(JSON.parse(String(put[1].body))).toMatchObject({ app_token: 'bascn_x' })

    await testInspectionFeishuConfig('101-1')
    const post = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit]
    expect(post[0]).toBe(`${BASE}/config/test?workshop=101-1`)
    expect(post[1]).toMatchObject({ method: 'POST' })
  })

  it('surfaces backend messages on config errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: unknown) => jsonResponse({ code: 400, message: '首次保存需填写 App ID 与 App Secret' }, 400)),
    )
    await expect(updateInspectionFeishuConfig('101-1', {} as never)).rejects.toThrow(
      '首次保存需填写 App ID 与 App Secret',
    )
  })

  it('surfaces a readable error when the sync status request fails', async () => {
    vi.stubGlobal('fetch', vi.fn((_url: unknown) => new Response('Internal Server Error', { status: 500 })))
    await expect(fetchInspectionFeishuSyncStatus('201-1')).rejects.toThrow('请求失败: 500')
  })
})

describe('triggerInspectionFeishuSync', () => {
  it('returns per-table data on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: unknown) => jsonResponse({ code: 200, data: { today: { synced: 1, total: 48 } } })),
    )
    await expect(triggerInspectionFeishuSync('201-1')).resolves.toEqual({
      today: { synced: 1, total: 48 },
    })
  })

  it('reports readable error when server returns plain-text 500', async () => {
    // 服务端未处理异常时返回纯文本 body，不得当 JSON 解析后抛语法错误
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: unknown) => new Response('Internal Server Error', { status: 500 })),
    )
    await expect(triggerInspectionFeishuSync('201-1')).rejects.toThrow(
      '同步失败（HTTP 500）',
    )
  })

  it('surfaces backend business message on envelope error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: unknown) => jsonResponse({ code: 400, message: '巡检飞书镜像同步未配置' }, 400)),
    )
    await expect(triggerInspectionFeishuSync('201-1')).rejects.toThrow(
      '巡检飞书镜像同步未配置',
    )
  })
})
