import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({
    Authorization: 'Bearer server-token',
    'X-Dazah-Operation-ID': 'fixture-operation',
    'X-Dazah-Page-Path': '/equipment',
    'X-Forwarded-For': '192.0.2.10',
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  consumeMaterials,
  createCategory,
  createEquipment,
  deleteCategory,
  fetchCalibrationPlans,
  fetchCalibrationRecords,
  fetchCategories,
  fetchCategoryTree,
  fetchDepartments,
  fetchFailureCodes,
  fetchLocationTree,
  fetchEquipments,
  fetchEquipmentStatistics,
  fetchInspectionTodaySummaries,
  fetchMaintenancePlans,
  fetchOverdueMaintenancePlans,
  fetchSpareParts,
  fetchStockWarnings,
  fetchWorkOrders,
  fetchWorkOrderStatistics,
  updateWorkOrder,
} from './equipment'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

const protectedReads: { name: string; path: string; read: () => Promise<unknown> }[] = [
  { name: '分类树', path: '/categories?tree=true', read: fetchCategoryTree },
  { name: '位置树', path: '/locations?tree=true', read: fetchLocationTree },
  { name: '设备列表', path: '/equipments?page=1&page_size=20', read: () => fetchEquipments() },
  { name: '部门列表', path: '/departments', read: fetchDepartments },
  ...(['symptoms', 'causes', 'actions'] as const).map(type => ({
    name: `故障代码 ${type}`, path: `/maintenance/failure-codes/${type}`,
    read: () => fetchFailureCodes(type),
  })),
  { name: '校准记录', path: '/maintenance/calibration/records?page=1&page_size=20', read: () => fetchCalibrationRecords() },
  { name: '保养计划', path: '/maintenance/plans/?page=1&page_size=20', read: () => fetchMaintenancePlans() },
  { name: '分类列表', path: '/categories', read: fetchCategories },
  { name: '备件列表', path: '/spare-parts/?page=1&page_size=20', read: () => fetchSpareParts() },
]

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('设备服务端查询认证回归', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it.each(protectedReads)('$name 传递身份、页面和客户端上下文', async ({ path, read }) => {
    const fetchMock = vi.fn(() => jsonResponse({ data: [{ id: 'row-1' }], meta: { total: 1 } }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await read()
    if (path.includes('page=')) {
      expect(result).toMatchObject({ items: [{ id: 'row-1' }], total: 1 })
    } else {
      expect(result).toEqual([{ id: 'row-1' }])
    }
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      `${API_BASE}/api/v1/equipment${path}`,
      { cache: 'no-store', headers: {
        Authorization: 'Bearer server-token',
        'X-Dazah-Operation-ID': 'fixture-operation',
        'X-Dazah-Page-Path': '/equipment',
        'X-Forwarded-For': '192.0.2.10',
      } },
    )
    expect(mocks.getAuthHeaders).toHaveBeenCalledOnce()
  })

  describe.each([401, 403])('HTTP %i', status => {
    it.each(protectedReads)('$name 保留鉴权失败，不转换为空数据', async ({ read }) => {
      const fetchMock = vi.fn(() => jsonResponse({ message: 'internal upstream detail' }, status))
      vi.stubGlobal('fetch', fetchMock)
      await expect(read()).rejects.toMatchObject({
        status,
        message: status === 401 ? '登录已失效，请重新登录' : '没有执行此操作的权限，请联系管理员',
      })
      expect(fetchMock).toHaveBeenCalledOnce()
    })
  })
})

describe('equipment actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a category with auth header', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'c-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '反应釜', parent_id: null }
    await createCategory(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/categories`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ Authorization: 'Bearer server-token', 'X-Dazah-Operation-ID': 'fixture-operation' }),
      }),
    )
  })

  it('creates an equipment record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'eq-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '发酵罐', category_id: 'c-1', equipment_no: 'EQ-001' }
    await createEquipment(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/equipments`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('deletes a category', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteCategory('c-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/categories/c-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('updates a work order', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'wo-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { status: 'in_progress' }
    await updateWorkOrder('wo-1', payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/maintenance/work-orders/wo-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('surfaces backend error message', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ message: '设备编号重复' }, 400))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createEquipment({ name: 'x' } as never)).rejects.toThrow('设备编号重复')
  })
})

describe('equipment workshop scoping actions', () => {
  function stubFetch(body: unknown) {
    const fetchMock = vi.fn(() => jsonResponse(body))
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }
  const lastUrl = (m: ReturnType<typeof vi.fn>) => String(m.mock.calls.at(-1)?.[0] ?? '')

  it('fetchEquipments / fetchEquipmentStatistics 携带 workshop', async () => {
    const m = stubFetch({ code: 200, data: [], meta: { total: 0 } })
    await fetchEquipments({ workshop: '101-2', page: 1, page_size: 20 })
    expect(lastUrl(m)).toContain('workshop=101-2')
    await fetchEquipmentStatistics('101-2')
    expect(lastUrl(m)).toContain('/equipments/statistics?workshop=101-2')
  })

  it('工单列表/统计走 maintenance 路径并携带 workshop', async () => {
    const m = stubFetch({ code: 200, data: [], meta: { total: 0 } })
    await fetchWorkOrders({ workshop: '101-2', page: 1, page_size: 20 })
    expect(lastUrl(m)).toContain(`${API_BASE}/api/v1/equipment/maintenance/work-orders/?`)
    expect(lastUrl(m)).toContain('workshop=101-2')
    await fetchWorkOrderStatistics('101-2')
    expect(lastUrl(m)).toContain('/work-orders/statistics?workshop=101-2')
  })

  it('校准/维护计划携带 workshop', async () => {
    const m = stubFetch({ code: 200, data: [], meta: { total: 0 } })
    await fetchCalibrationPlans({ workshop: '201-1', page: 1 })
    expect(lastUrl(m)).toContain('/maintenance/calibration/plans?')
    expect(lastUrl(m)).toContain('workshop=201-1')
    await fetchCalibrationRecords({ workshop: '201-1', page: 1 })
    expect(lastUrl(m)).toContain('/maintenance/calibration/records?')
    expect(lastUrl(m)).toContain('workshop=201-1')
    await fetchMaintenancePlans({ workshop: '201-1', page: 1 })
    expect(lastUrl(m)).toContain('/maintenance/plans/?')
    expect(lastUrl(m)).toContain('workshop=201-1')
  })

  it('备件列表/库存预警携带 workshop', async () => {
    const m = stubFetch({ code: 200, data: [], meta: { total: 0 } })
    await fetchSpareParts({ workshop: '201-1', page: 1 })
    expect(lastUrl(m)).toContain('/api/v1/equipment/spare-parts/?')
    expect(lastUrl(m)).toContain('workshop=201-1')
    await fetchStockWarnings('201-1')
    expect(lastUrl(m)).toBe(
      `${API_BASE}/api/v1/equipment/spare-parts/stock/warnings?workshop=201-1`,
    )
  })

  it('未传 workshop 时不携带该参数（跨车间查询）', async () => {
    const m = stubFetch({ code: 200, data: [], meta: { total: 0 } })
    await fetchEquipments({ page: 1 })
    expect(lastUrl(m)).not.toContain('workshop')
    await fetchStockWarnings()
    expect(lastUrl(m)).not.toContain('workshop')
  })

  it('今日巡检汇总带登录凭证并解析 data 数组', async () => {
    const summaries = [
      {
        workshop_code: '101-2',
        date: '2026-10-13',
        total_devices: 49,
        inspected: 49,
        abnormal: 0,
        am_inspected: 49,
        pm_inspected: 49,
      },
    ]
    const m = vi.fn(() => jsonResponse({ code: 200, data: summaries }))
    vi.stubGlobal('fetch', m)

    await expect(fetchInspectionTodaySummaries()).resolves.toEqual(summaries)
    expect(m).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/inspection/feishu/today-summaries`,
      expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({ Authorization: 'Bearer server-token' }),
      }),
    )
  })

  it('今日巡检汇总在非 200 或结构异常时降级为空列表', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 500 }, 500)))
    await expect(fetchInspectionTodaySummaries()).resolves.toEqual([])

    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, data: null })))
    await expect(fetchInspectionTodaySummaries()).resolves.toEqual([])
  })
})

describe('equipment actions 补充覆盖', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('consumes materials against the work order materials endpoint', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    const items = [{ spare_part_id: 'sp-1', quantity: 2 }]
    await consumeMaterials('wo-1', { items })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/maintenance/work-orders/wo-1/materials`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ items }) }),
    )
  })

  it('fetches overdue maintenance plans from the maintenance plans path', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchOverdueMaintenancePlans()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/maintenance/plans/overdue`,
      expect.anything(),
    )
    expect(result).toEqual([])
  })
})
