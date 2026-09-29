import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAllHrFeishuAppSettings,
  fetchEmailConfig,
  fetchHrFeishuAppSettings,
  fetchHrFeishuEntityFieldMappingBundle,
  fetchHrFeishuEntitySettings,
  fetchHrFeishuEntityTables,
} from './hr'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('HR settings through the production API proxy', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads both credential purposes again after saving with explicit page context', async () => {
    const pathname = '/hr/settings/feishu'
    vi.stubGlobal('window', { location: { pathname } })
    const apps = [
      { purpose: 'contact', app_id: 'test-contact', app_secret_masked: '****' },
      { purpose: 'bitable', app_id: 'test-bitable', app_secret_masked: '****' },
    ]
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (new Headers(init?.headers).get('X-Dazah-Page-Path') !== pathname) {
        return jsonResponse({ code: 400, message: '共享业务接口需要明确的页面上下文' }, 400)
      }
      return jsonResponse({ data: apps })
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAllHrFeishuAppSettings()).resolves.toEqual(apps)
    await expect(fetchAllHrFeishuAppSettings()).resolves.toEqual(apps)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/hr/feishu-settings/apps', {
      cache: 'no-store', headers: { 'X-Dazah-Page-Path': pathname },
    })
  })

  it.each(['contact', 'bitable'])('preserves the credential purpose: %s', async purpose => {
    vi.stubGlobal('window', { location: { pathname: '/hr/settings/feishu' } })
    const app = { purpose, app_id: `test-${purpose}` }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(app))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchHrFeishuAppSettings(purpose)).resolves.toEqual(app)
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/hr/feishu-settings/app?purpose=${purpose}`, {
      cache: 'no-store', headers: { 'X-Dazah-Page-Path': '/hr/settings/feishu' },
    })
  })

  it('sends page context for entity settings, tables, and field mappings', async () => {
    vi.stubGlobal('window', { location: { pathname: '/hr/settings/feishu' } })
    const bundle = { entity_code: 'onboarding', field_mappings: [] }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ data: [{ table_id: 'test-table', table_name: '入职台账' }] }))
      .mockResolvedValueOnce(jsonResponse({ data: bundle }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchHrFeishuEntitySettings()).resolves.toEqual([])
    await expect(fetchHrFeishuEntityTables('onboarding', ' test-base ')).resolves.toEqual([
      { table_id: 'test-table', table_name: '入职台账' },
    ])
    await expect(fetchHrFeishuEntityFieldMappingBundle('onboarding', {
      app_token: 'test-base', table_id: 'test-table',
    })).resolves.toEqual(bundle)

    const options = { cache: 'no-store', headers: { 'X-Dazah-Page-Path': '/hr/settings/feishu' } }
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/hr/feishu-settings/entities', options)
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      '/api/v1/hr/feishu-settings/entities/onboarding/tables?app_token=test-base', options)
    expect(fetchMock).toHaveBeenNthCalledWith(3,
      '/api/v1/hr/feishu-settings/entities/onboarding/field-mapping?app_token=test-base&table_id=test-table', options)
  })

  it.each(['/hr/feishu-contacts', '/hr/settings/dept-mapping'])(
    'keeps the actual caller for shared Feishu settings reads: %s', async pathname => {
      vi.stubGlobal('window', { location: { pathname } })
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
      vi.stubGlobal('fetch', fetchMock)

      await fetchAllHrFeishuAppSettings()
      expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('X-Dazah-Page-Path')).toBe(pathname)
    },
  )

  it.each(['/hr/settings/feishu', '/hr/recruitment'])(
    'loads email configuration with its original envelope and caller: %s', async pathname => {
      vi.stubGlobal('window', { location: { pathname } })
      const payload = { code: 200, data: { fetch_enabled: false } }
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload))
      vi.stubGlobal('fetch', fetchMock)

      await expect(fetchEmailConfig()).resolves.toEqual(payload)
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/hr/email/config', {
        cache: 'no-store', headers: { 'X-Dazah-Page-Path': pathname },
      })
    },
  )

  const readers = [
    ['app', () => fetchHrFeishuAppSettings()],
    ['apps', fetchAllHrFeishuAppSettings],
    ['entities', fetchHrFeishuEntitySettings],
    ['tables', () => fetchHrFeishuEntityTables('onboarding')],
    ['field mappings', () => fetchHrFeishuEntityFieldMappingBundle('onboarding')],
    ['email config', fetchEmailConfig],
  ] as const

  it.each(readers)('preserves backend permission errors for %s', async (_name, read) => {
    vi.stubGlobal('window', { location: { pathname: '/hr/settings/feishu' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ code: 403, message: '未获得当前页面的查询权限' }, 403),
    ))

    await expect(read()).rejects.toThrow('未获得当前页面的查询权限')
  })

  it('handles non-JSON errors without exposing the response body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('upstream failure', { status: 502 })))
    await expect(fetchAllHrFeishuAppSettings()).rejects.toThrow('请求失败: 502')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('upstream failure', { status: 502 })))
    await expect(fetchEmailConfig()).rejects.toThrow('获取邮箱配置失败')
  })

  it('supports string detail errors and does not invent a page outside the browser', async () => {
    vi.stubGlobal('window', undefined)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: '页面上下文无效' }, 400))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchHrFeishuAppSettings()).rejects.toThrow('页面上下文无效')
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('X-Dazah-Page-Path')).toBe(false)
  })
})
