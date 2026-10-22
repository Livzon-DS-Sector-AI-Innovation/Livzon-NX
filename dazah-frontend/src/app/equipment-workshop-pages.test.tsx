/* @vitest-environment happy-dom */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  fetchCategoryTree: vi.fn(),
  fetchLocationTree: vi.fn(),
  fetchEquipments: vi.fn(),
  fetchEquipmentStatistics: vi.fn(),
  fetchDepartments: vi.fn(),
  fetchWorkOrders: vi.fn(),
  fetchWorkOrderStatistics: vi.fn(),
  fetchFailureCodes: vi.fn(),
  fetchCalibrationPlans: vi.fn(),
  fetchCalibrationRecords: vi.fn(),
  fetchMaintenancePlans: vi.fn(),
  fetchOverdueMaintenancePlans: vi.fn(),
  fetchSpareParts: vi.fn(),
  fetchStockWarnings: vi.fn(),
  fetchInspectionTodaySummaries: vi.fn(),
}))

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
  redirect: vi.fn(() => {
    throw new Error('REDIRECT')
  }),
}))

vi.mock('next/navigation', () => navigation)
vi.mock('@/actions/equipment', () => actions)
vi.mock('@/components/equipment', () => {
  const passthrough = ({ children }: { children?: unknown }) => children
  return {
    EquipmentPage: () => null,
    MaintenancePage: () => null,
    SparePartsPage: () => null,
    PersonnelPage: () => null,
    PersonnelQueryProvider: passthrough,
    StatsDashboard: () => null,
    WorkshopNavBlocks: () => null,
    ModuleTabs: () => null,
  }
})

import EquipmentConsolePage from '@/app/(dashboard)/equipment/page'
import AssetsRedirect from '@/app/(dashboard)/equipment/assets/page'
import AssetsWorkshopRedirect from '@/app/(dashboard)/equipment/assets/[workshop]/page'
import InspectionRedirect from '@/app/(dashboard)/equipment/inspection/page'
import InspectionWorkshopRedirect from '@/app/(dashboard)/equipment/inspection/[workshop]/page'
import MaintenanceRedirect from '@/app/(dashboard)/equipment/maintenance/page'
import MaintenanceWorkshopRedirect from '@/app/(dashboard)/equipment/maintenance/[workshop]/page'
import PersonnelRedirect from '@/app/(dashboard)/equipment/personnel/page'
import PersonnelWorkshopRedirect from '@/app/(dashboard)/equipment/personnel/[workshop]/page'
import SparePartsRedirect from '@/app/(dashboard)/equipment/spare-parts/page'
import SparePartsWorkshopRedirect from '@/app/(dashboard)/equipment/spare-parts/[workshop]/page'
import StatsPage from '@/app/(dashboard)/equipment/stats/page'

type PageElement = {
  type: (props: Record<string, unknown>) => Promise<PageElement> | PageElement
  props: Record<string, unknown>
}

/** 渲染统一工作台，返回 [车间块, 模块Tab, 选中模块视图] 与模块视图元素 */
async function renderConsole(module?: string, workshop?: string) {
  const element = (await EquipmentConsolePage({
    searchParams: Promise.resolve({
      ...(workshop ? { workshop } : {}),
      ...(module ? { module } : {}),
    }),
  })) as unknown as { props: { children: unknown[] } }
  // 页面根元素即节奏容器（与生产概览页一致），其 children 就是模块元素
  const children = element.props.children.filter(Boolean)
  return children as unknown as PageElement[]
}

/** 执行模块视图（异步服务端组件）取其渲染出的内容元素 props */
async function renderView(view: PageElement): Promise<PageElement> {
  const result = await view.type(view.props)
  return result as PageElement
}

function legacyParams(workshop: string) {
  return { params: Promise.resolve({ workshop }) }
}

function queryParams(workshop?: string) {
  return { searchParams: Promise.resolve(workshop ? { workshop } : {}) }
}

function defaults() {
  actions.fetchCategoryTree.mockResolvedValue([])
  actions.fetchLocationTree.mockResolvedValue([])
  actions.fetchEquipments.mockResolvedValue({ items: [], total: 0 })
  actions.fetchEquipmentStatistics.mockResolvedValue({
    total: 0,
    by_status: {},
    by_category: {},
    by_location: {},
  })
  actions.fetchDepartments.mockResolvedValue([])
  actions.fetchWorkOrders.mockResolvedValue({ items: [], total: 0 })
  actions.fetchWorkOrderStatistics.mockResolvedValue({
    total: 0,
    by_status: {},
    by_type: {},
    by_priority: {},
  })
  actions.fetchFailureCodes.mockResolvedValue([])
  actions.fetchCalibrationPlans.mockResolvedValue({ items: [], total: 0 })
  actions.fetchCalibrationRecords.mockResolvedValue({ items: [], total: 0 })
  actions.fetchMaintenancePlans.mockResolvedValue({ items: [], total: 0 })
  actions.fetchOverdueMaintenancePlans.mockResolvedValue([])
  actions.fetchSpareParts.mockResolvedValue({ items: [], total: 0 })
  actions.fetchStockWarnings.mockResolvedValue([])
  actions.fetchInspectionTodaySummaries.mockResolvedValue([])
}

describe('equipment unified console with workshop + module queries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    defaults()
  })

  it('wraps modules in the same rhythm container as the production overview (p-4 + gap-3)', async () => {
    // 车间块/模块 Tab 不自带 marginBottom，页面边距与模块间距全部由根容器统一提供
    const element = (await EquipmentConsolePage({
      searchParams: Promise.resolve({ module: 'assets', workshop: '101-2' }),
    })) as unknown as { props: { className?: string } }
    expect(element.props.className).toBe('p-4 flex flex-col gap-3')
  })

  it('renders the assets module scoped to ?workshop= and passes it to fetches', async () => {
    const children = await renderConsole('assets', '101-2')
    // 车间块 + 模块Tab + 模块视图三段结构
    expect(children).toHaveLength(3)
    const view = await renderView(children[2])
    expect(view.props.workshopCode).toBe('101-2')
    expect(actions.fetchEquipments).toHaveBeenCalledWith({
      workshop: '101-2',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchEquipmentStatistics).toHaveBeenCalledWith('101-2')
    // 只取当前模块的数据
    expect(actions.fetchWorkOrders).not.toHaveBeenCalled()
    expect(actions.fetchSpareParts).not.toHaveBeenCalled()
  })

  it('falls back to the default workshop when the query is missing or invalid', async () => {
    const children = await renderConsole('assets')
    const view = await renderView(children[2])
    expect(view.props.workshopCode).toBe('201-1')
    const invalid = await renderConsole('assets', '999')
    const invalidView = await renderView(invalid[2])
    expect(invalidView.props.workshopCode).toBe('201-1')
  })

  it('renders no module content when ?module= is absent or unknown', async () => {
    const absent = await renderConsole()
    expect(absent).toHaveLength(2)
    const unknown = await renderConsole('nonsense', '103')
    expect(unknown).toHaveLength(2)
    expect(actions.fetchEquipments).not.toHaveBeenCalled()
  })

  it('renders the maintenance module scoped to ?workshop=', async () => {
    const children = await renderConsole('maintenance', '201-1')
    const view = await renderView(children[2])
    expect(view.props.workshopCode).toBe('201-1')
    expect(actions.fetchWorkOrders).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchWorkOrderStatistics).toHaveBeenCalledWith('201-1')
    expect(actions.fetchCalibrationPlans).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchMaintenancePlans).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchEquipments).not.toHaveBeenCalledWith(
      expect.objectContaining({ page_size: 20 }),
    )
  })

  it('maintenance degrades per-domain when individual fetches fail', async () => {
    actions.fetchWorkOrders.mockRejectedValue(new Error('boom'))
    const children = await renderConsole('maintenance', '103')
    const view = await renderView(children[2])
    expect(view.props.workshopCode).toBe('103')
    expect(view.props.initialWorkOrders).toEqual([])
    // 其余域不受影响
    expect(view.props.initialCalibrationPlans).toEqual([])
    expect(actions.fetchCalibrationPlans).toHaveBeenCalled()
  })

  it('renders the spare parts module scoped to ?workshop=', async () => {
    const children = await renderConsole('spare-parts', '201-1')
    const view = await renderView(children[2])
    expect(view.props.workshopCode).toBe('201-1')
    expect(actions.fetchSpareParts).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchStockWarnings).toHaveBeenCalledWith('201-1')
  })

  it('renders the inspection module with the workshop context', async () => {
    const children = await renderConsole('inspection', '201-1')
    const view = children[2]
    expect(view.props.workshopCode).toBe('201-1')
    expect(view.props.workshopLabel).toBe('201一车间')
  })

  it('renders the personnel module scoped to ?workshop=', async () => {
    const children = await renderConsole('personnel', '101-1')
    const provider = await renderView(children[2])
    const page = (provider.props as unknown as { children: PageElement }).children
    expect(page.props.workshopCode).toBe('101-1')
  })

  it('renders the stats dashboard with inspection summaries', async () => {
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
    actions.fetchInspectionTodaySummaries.mockResolvedValue(summaries)

    const element = (await StatsPage()) as unknown as {
      props: { initialData: { inspectionSummaries: unknown } }
    }

    expect(actions.fetchInspectionTodaySummaries).toHaveBeenCalled()
    expect(element.props.initialData.inspectionSummaries).toEqual(summaries)
  })

  it('degrades to empty inspection summaries when the fetch rejects', async () => {
    actions.fetchInspectionTodaySummaries.mockRejectedValue(new Error('boom'))

    const element = (await StatsPage()) as unknown as {
      props: { initialData: { inspectionSummaries: unknown } }
    }

    expect(element.props.initialData.inspectionSummaries).toEqual([])
  })
})

describe('equipment legacy module path redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['台账', AssetsRedirect, 'assets'],
    ['维护保养', MaintenanceRedirect, 'maintenance'],
    ['巡检', InspectionRedirect, 'inspection'],
    ['备件管理', SparePartsRedirect, 'spare-parts'],
    ['人员配置', PersonnelRedirect, 'personnel'],
  ])('%s 旧功能页路径重定向到统一工作台（保留车间参数）', async (_name, Page, module) => {
    await expect(Page(queryParams('101-2'))).rejects.toThrow('REDIRECT')
    expect(navigation.redirect).toHaveBeenCalledWith(
      `/equipment?workshop=101-2&module=${module}`,
    )
    await expect(Page(queryParams())).rejects.toThrow('REDIRECT')
    expect(navigation.redirect).toHaveBeenCalledWith(`/equipment?module=${module}`)
  })
})

describe('equipment legacy workshop redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['台账', AssetsWorkshopRedirect, 'assets'],
    ['维护保养', MaintenanceWorkshopRedirect, 'maintenance'],
    ['备件管理', SparePartsWorkshopRedirect, 'spare-parts'],
    ['人员配置', PersonnelWorkshopRedirect, 'personnel'],
    ['巡检', InspectionWorkshopRedirect, 'inspection'],
  ])('%s 旧车间子路径直接重定向到统一工作台', async (_name, Page, module) => {
    await expect(Page(legacyParams('101-2'))).rejects.toThrow('REDIRECT')
    expect(navigation.redirect).toHaveBeenCalledWith(
      `/equipment?workshop=101-2&module=${module}`,
    )
  })

  it.each([
    AssetsWorkshopRedirect,
    MaintenanceWorkshopRedirect,
    SparePartsWorkshopRedirect,
    PersonnelWorkshopRedirect,
    InspectionWorkshopRedirect,
  ])('未知车间代码走 notFound', async (Page) => {
    await expect(Page(legacyParams('bad'))).rejects.toThrow('NOT_FOUND')
    expect(navigation.notFound).toHaveBeenCalled()
  })
})
