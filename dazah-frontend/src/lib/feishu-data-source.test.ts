import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  feishuDataSourceApi,
  getFeishuMappedMenuTarget,
  getFeishuModuleDefinition,
} from './feishu-data-source'

describe('native energy pages remain independent of archived Wiki mappings', () => {
  it.each(['/energy', '/energy/entry', '/energy/reports', '/energy/analysis', '/energy/data-quality', '/energy/settings', '/energy/sources', '/energy/data', '/energy/sync-runs'])(
    'does not gate %s on a mapped sheet lookup', path => {
      expect(getFeishuMappedMenuTarget('energy', path, new URLSearchParams('source=feishu&task=example'))).toBeUndefined()
    },
  )
  it('does not offer retired historical pages as spreadsheet mapping targets', () => {
    expect(getFeishuModuleDefinition('energy').pages).toEqual([])
  })
})

describe('administration read mirror data source', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers only the two mirror pages as binding targets', () => {
    expect(getFeishuModuleDefinition('administration').pages).toEqual([
      { label: '烟酒礼品管理 / 物品清单', value: 'admin:tobacco-gift:items' },
      { label: '烟酒礼品管理 / 领用记录', value: 'admin:tobacco-gift:records' },
    ])
  })

  it('uses the platform feishu-read route family', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({ code: 200, data: [] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await feishuDataSourceApi.listRoots('administration', 'cfg-1')
    await feishuDataSourceApi.listResources('administration')
    await feishuDataSourceApi.syncResource('administration', 'res-1')
    await feishuDataSourceApi.saveBindings('administration', 'admin:tobacco-gift:items', [])

    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(urls).toEqual([
      '/api/v1/administration/feishu-read/roots',
      '/api/v1/administration/feishu-read/resources',
      '/api/v1/administration/feishu-read/resources/res-1/sync',
      '/api/v1/administration/feishu-read/page-bindings/admin%3Atobacco-gift%3Aitems',
    ])
  })
})
