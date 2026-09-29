import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchQualityFeishuAppSettings,
  fetchQualityFeishuEntityFieldMappingBundle,
  fetchQualityFeishuEntitySettings,
  fetchQualityFeishuEntityTables,
} from './quality'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('quality Feishu settings through the production API proxy', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    '/quality/settings',
    '/quality/deviations/records',
    '/quality/deviations/investigations',
    '/quality/oos-oot/report-records',
    '/quality/oos-oot/investigation-push',
  ])('loads app settings with the actual caller page: %s', async pathname => {
    vi.stubGlobal('window', { location: { pathname } })
    const settings = { app_id: 'test-app', is_enabled: true }
    // Nginx forwards directly to FastAPI and does not synthesize page headers.
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (new Headers(init?.headers).get('X-Dazah-Page-Path') !== pathname) {
        return jsonResponse({ code: 400, message: '共享业务接口需要明确的页面上下文' }, 400)
      }
      return jsonResponse(settings)
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchQualityFeishuAppSettings()).resolves.toEqual(settings)
    // The same request runs again after saving and invalidating the query.
    await expect(fetchQualityFeishuAppSettings()).resolves.toEqual(settings)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/quality/feishu-settings/app', {
      cache: 'no-store',
      headers: { 'X-Dazah-Page-Path': pathname },
    })
  })

  it('sends page context for entity settings, table options, and field mappings', async () => {
    vi.stubGlobal('window', { location: { pathname: '/quality/settings' } })
    const bundle = { entity_code: 'inspection_records', field_mappings: [] }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
      .mockResolvedValueOnce(jsonResponse([{ table_id: 'test-table', table_name: '检验记录' }]))
      .mockResolvedValueOnce(jsonResponse({ data: bundle }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchQualityFeishuEntitySettings()).resolves.toEqual([])
    await expect(fetchQualityFeishuEntityTables('inspection_records', 'test-base')).resolves.toEqual([
      { table_id: 'test-table', table_name: '检验记录' },
    ])
    await expect(fetchQualityFeishuEntityFieldMappingBundle('inspection_records', {
      app_token: 'test-base', table_id: 'test-table',
    })).resolves.toEqual(bundle)

    const options = { cache: 'no-store', headers: { 'X-Dazah-Page-Path': '/quality/settings' } }
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/quality/feishu-settings/entities', options)
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      '/api/v1/quality/feishu-settings/entities/inspection_records/tables?app_token=test-base', options)
    expect(fetchMock).toHaveBeenNthCalledWith(3,
      '/api/v1/quality/feishu-settings/entities/inspection_records/field-mapping?app_token=test-base&table_id=test-table', options)
  })

  it.each([
    ['app', fetchQualityFeishuAppSettings],
    ['entities', fetchQualityFeishuEntitySettings],
    ['tables', () => fetchQualityFeishuEntityTables('inspection_records')],
    ['field mappings', () => fetchQualityFeishuEntityFieldMappingBundle('inspection_records')],
  ])('preserves the backend permission error when loading %s', async (_name, load) => {
    vi.stubGlobal('window', { location: { pathname: '/quality/settings' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ code: 403, message: '未获得当前页面的查询权限' }, 403),
    ))

    await expect(load()).rejects.toThrow('未获得当前页面的查询权限')
  })

  it('does not invent a settings page when no browser context exists', async () => {
    vi.stubGlobal('window', undefined)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ app_id: '' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchQualityFeishuAppSettings()).resolves.toEqual({ app_id: '' })
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('X-Dazah-Page-Path')).toBe(false)
  })
})
