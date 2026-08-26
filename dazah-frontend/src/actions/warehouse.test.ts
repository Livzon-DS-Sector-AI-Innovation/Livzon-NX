import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'warehouse-action-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  chatWarehouseAiAction,
  createWarehouseFeishuRootAction,
  deleteWarehouseFeishuRootAction,
  deleteWarehouseRecordAction,
  discoverWarehouseFeishuRootAction,
  saveWarehouseFeishuConfigAction,
  saveWarehousePageBindingsAction,
  syncWarehouseFeishuTableAction,
  syncWarehouseFeishuTablesAction,
  testWarehouseFeishuConfigAction,
  updateWarehousePageFeishuConfigAction,
  updateWarehouseRecordAction,
} from './warehouse'

function response(data: unknown = { ok: true }): Response {
  return new Response(JSON.stringify({ code: 200, message: 'ok', data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('warehouse server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('forwards Feishu configuration, mapping, record and AI writes', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    const config = {
      config_name: '仓储',
      app_id: 'app-id',
      app_secret: 'secret',
      is_active: true,
      timezone: 'Asia/Shanghai',
      daily_sync_time: '02:00',
      remark: null,
    }
    await saveWarehouseFeishuConfigAction(config)
    await testWarehouseFeishuConfigAction(config)
    await createWarehouseFeishuRootAction({ name: '原辅料', source_type: 'base', source_url: 'https://feishu.cn/base/a' })
    await deleteWarehouseFeishuRootAction('root/1')
    await discoverWarehouseFeishuRootAction('root/1')
    await syncWarehouseFeishuTableAction('table/1')
    await syncWarehouseFeishuTablesAction(['table/1', 'table/2'])
    await saveWarehousePageBindingsAction('raw-summary', [{
      resource_id: 'resource-1',
      tab_name: '库存',
      sort_order: 1,
      is_default: true,
      is_enabled: true,
      visible_field_ids: ['field-1'],
    }])
    await chatWarehouseAiAction('库存预警')
    await updateWarehouseRecordAction('raw-summary', 'record/1', { 物料: '酸' })
    await deleteWarehouseRecordAction('raw-summary', 'record/1')
    await updateWarehousePageFeishuConfigAction('raw-summary', {
      app_token: 'app-token',
      table_id: 'table-id',
      table_name: '原辅料',
      view_id: 'view-id',
    })

    expect(fetchMock).toHaveBeenCalledTimes(13)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer warehouse-action-token'
    })).toBe(true)
    expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).includes('/warehouse/page-data/raw-summary') &&
      init?.method === 'PUT' &&
      String(init.body).includes('current_mirror')),
    ).toBe(true)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/warehouse/settings')
  })

  it('surfaces protected write failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '无仓储写权限' }), {
        status: 403,
        headers: { 'content-type': 'application/json' },
      }),
    ))

    await expect(deleteWarehouseFeishuRootAction('root-1')).rejects.toThrow('无仓储写权限')
  })

  it('returns null for a successful empty warehouse response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })))
    await expect(saveWarehouseFeishuConfigAction({} as never)).resolves.toBeNull()
  })
})
