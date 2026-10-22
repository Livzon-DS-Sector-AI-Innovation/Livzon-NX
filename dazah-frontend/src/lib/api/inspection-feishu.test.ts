import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createFeishuApp,
  deleteFeishuApp,
  fetchFeishuApps,
  fetchInspectionFeishuConfig,
  fetchInspectionFeishuConfigList,
  fetchInspectionFeishuDevices,
  fetchInspectionFeishuRecords,
  fetchInspectionFeishuSyncStatus,
  fetchInspectionFeishuTodaySummary,
  testInspectionFeishuConfig,
  triggerInspectionFeishuSync,
  updateInspectionFeishuConfig,
  updateFeishuApp,
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
      base_url: '',
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

describe('fetchInspectionFeishuConfigList', () => {
  it('requests the config-list endpoint and returns masked details', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({
        code: 200,
        data: [
          {
            workshop_code: '101-2',
            app_id: 'cli_ws',
            app_secret_masked: 'cli_ws****',
            app_secret_configured: true,
            app_token: 'bascn_1012',
            base_url: 'https://example.feishu.cn/base/bascn_1012',
            today_table_id: 'tbl_today',
            history_table_id: 'tbl_history',
            device_table_id: 'tbl_devices',
            is_enabled: true,
            source: 'database',
            enabled: true,
            last_test_status: 'success',
            last_test_error: null,
            last_tested_at: null,
          },
        ],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const details = await fetchInspectionFeishuConfigList()
    expect(fetchMock).toHaveBeenCalledWith(`${BASE}/config-list`)
    expect(details).toHaveLength(1)
    expect(details[0].workshop_code).toBe('101-2')
    expect(details[0].base_url).toBe('https://example.feishu.cn/base/bascn_1012')
    // Secret 只回掩码状态
    expect(details[0].app_secret_configured).toBe(true)
    expect(details[0].app_secret_masked).toBe('cli_ws****')
  })

  it('falls back to an empty list when the endpoint returns no data', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, data: null })))
    const details = await fetchInspectionFeishuConfigList()
    expect(details).toEqual([])
  })
})

describe('feishu apps api', () => {
  it('lists self-hosted apps and falls back to an empty list', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({
        code: 200,
        data: [{ id: 'app-1', app_id: 'cli_a', name: '巡检应用' }],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchFeishuApps()).resolves.toEqual([
      { id: 'app-1', app_id: 'cli_a', name: '巡检应用' },
    ])
    expect(fetchMock).toHaveBeenCalledWith(`${BASE}/apps`)

    fetchMock.mockResolvedValue(jsonResponse({ code: 200, data: null }))
    await expect(fetchFeishuApps()).resolves.toEqual([])
  })

  it('creates, updates and deletes an app with the expected method and body', async () => {
    const fetchMock = vi.fn((_url: unknown) =>
      jsonResponse({ code: 200, data: { id: 'app-1', app_id: 'cli_a' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      createFeishuApp({ name: '巡检应用', app_id: 'cli_a', app_secret: 's1' }),
    ).resolves.toMatchObject({ id: 'app-1' })
    const post = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(post[0]).toBe(`${BASE}/apps`)
    expect(post[1]).toMatchObject({ method: 'POST' })
    expect(JSON.parse(String(post[1].body))).toMatchObject({ app_id: 'cli_a' })

    await expect(
      updateFeishuApp('app-1', { name: '巡检应用2', app_id: 'cli_a', app_secret: '' }),
    ).resolves.toMatchObject({ id: 'app-1' })
    const put = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(put[0]).toBe(`${BASE}/apps/app-1`)
    expect(put[1]).toMatchObject({ method: 'PUT' })

    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 200, data: null }))
    await expect(deleteFeishuApp('app-1')).resolves.toBeNull()
    const del = fetchMock.mock.calls[2] as unknown as [string, RequestInit]
    expect(del[0]).toBe(`${BASE}/apps/app-1`)
    expect(del[1]).toMatchObject({ method: 'DELETE' })
  })

  it('surfaces the backend rejection message on delete', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: unknown) =>
        jsonResponse({ code: 400, message: '应用仍被巡检配置引用，无法删除' }, 400),
      ),
    )
    await expect(deleteFeishuApp('app-1')).rejects.toThrow('应用仍被巡检配置引用，无法删除')
  })
})
