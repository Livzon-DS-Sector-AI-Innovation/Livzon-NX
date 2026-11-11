import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'admin-action-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({
  cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers({ 'X-Dazah-Page-Path': '/admin/settings/feishu' })),
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createAdministrationFeishuRootAction,
  deleteAdministrationFeishuRootAction,
  discoverAdministrationFeishuRootAction,
  saveAdministrationFeishuConfigAction,
  saveAdministrationPageBindingsAction,
  syncAdministrationFeishuResourceAction,
  syncAdministrationFeishuResourcesAction,
  testAdministrationFeishuConfigAction,
} from './administration'

function response(data: unknown = { ok: true }, status = 200): Response {
  return new Response(JSON.stringify({ code: status, message: status === 200 ? 'ok' : '凭据未配置', data }), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const config = {
  config_name: '行政飞书',
  app_id: 'cli_test',
  app_secret: 'secret',
  is_active: true,
  timezone: 'Asia/Shanghai',
  daily_sync_time: '02:00',
  remark: null,
}

describe('administration server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('forwards settings writes with the Feishu settings page context', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response({ app_id: 'cli_test' }))
    vi.stubGlobal('fetch', fetchMock)

    const saved = await saveAdministrationFeishuConfigAction(config)
    expect(saved).toEqual({ app_id: 'cli_test' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/administration\/feishu-config$/)
    expect(init.method).toBe('PUT')
    expect(init.headers['X-Dazah-Page-Key']).toBe('admin:feishu-settings')
    expect(init.headers.Authorization).toBe('Bearer admin-action-token')
    expect(JSON.parse(init.body)).toMatchObject({ app_id: 'cli_test' })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/admin/settings/feishu')

    await testAdministrationFeishuConfigAction(config)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/feishu-config\/test$/)
    expect(fetchMock.mock.calls[1][1].method).toBe('POST')
  })

  it('maintains roots, syncs resources sequentially and saves bindings', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await createAdministrationFeishuRootAction({
      name: '烟酒礼品',
      source_type: 'base',
      source_url: 'https://example.feishu.cn/base/abc',
    })
    await deleteAdministrationFeishuRootAction('root/1')
    await discoverAdministrationFeishuRootAction('root-2')
    await syncAdministrationFeishuResourceAction('res-1')
    await syncAdministrationFeishuResourcesAction(['res-2', 'res-3'])
    await saveAdministrationPageBindingsAction('admin:tobacco-gift:items', [
      {
        resource_id: 'res-1',
        tab_name: '物品清单',
        sort_order: 0,
        is_default: true,
        is_enabled: true,
        visible_field_ids: [],
      },
    ])

    const calls = fetchMock.mock.calls.map(([url, init]) => `${init.method} ${String(url)}`)
    expect(calls[0]).toMatch(/^POST .*\/administration\/feishu-read\/roots$/)
    expect(calls[1]).toMatch(/^DELETE .*\/feishu-read\/roots\/root%2F1$/)
    expect(calls[2]).toMatch(/^POST .*\/feishu-read\/roots\/root-2\/discover$/)
    expect(calls[3]).toMatch(/^POST .*\/feishu-read\/resources\/res-1\/sync$/)
    expect(calls[4]).toMatch(/resources\/res-2\/sync$/)
    expect(calls[5]).toMatch(/resources\/res-3\/sync$/)
    expect(calls[6]).toMatch(
      /^PUT .*\/feishu-read\/page-bindings\/admin%3Atobacco-gift%3Aitems$/,
    )
    expect(JSON.parse(fetchMock.mock.calls[6][1].body).bindings).toHaveLength(1)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/admin/tobacco-gift', 'layout')
  })

  it('surfaces backend error messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, 400)))
    await expect(saveAdministrationFeishuConfigAction(config)).rejects.toThrow('凭据未配置')
  })

  it('falls back to status text when error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('gateway down', { status: 502 })),
    )
    await expect(discoverAdministrationFeishuRootAction('root-1')).rejects.toThrow('请求失败（502）')
  })
})
