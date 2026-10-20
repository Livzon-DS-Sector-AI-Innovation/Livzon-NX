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
  }
})

import AssetsPage from '@/app/(dashboard)/equipment/assets/page'
import AssetsWorkshopRedirect from '@/app/(dashboard)/equipment/assets/[workshop]/page'
import InspectionPage from '@/app/(dashboard)/equipment/inspection/page'
import InspectionWorkshopRedirect from '@/app/(dashboard)/equipment/inspection/[workshop]/page'
import MaintenancePage from '@/app/(dashboard)/equipment/maintenance/page'
import MaintenanceWorkshopRedirect from '@/app/(dashboard)/equipment/maintenance/[workshop]/page'
import PersonnelPage from '@/app/(dashboard)/equipment/personnel/page'
import PersonnelWorkshopRedirect from '@/app/(dashboard)/equipment/personnel/[workshop]/page'
import SparePartsPage from '@/app/(dashboard)/equipment/spare-parts/page'
import SparePartsWorkshopRedirect from '@/app/(dashboard)/equipment/spare-parts/[workshop]/page'
import StatsPage from '@/app/(dashboard)/equipment/stats/page'

type PageElement = { props: Record<string, unknown> }

/** 单页路由渲染片段 [车间切换块, 内容组件]，取内容组件的 props */
async function renderContent(
  Page: (args: { searchParams: Promise<{ workshop?: string }> }) => Promise<unknown>,
  workshop?: string,
): Promise<PageElement> {
  const element = (await Page({
    searchParams: Promise.resolve(workshop ? { workshop } : {}),
  })) as unknown as { props: { children: unknown[] } }
  const children = element.props.children
  const content = Array.isArray(children) ? children[children.length - 1] : children
  return content as PageElement
}

function legacyParams(workshop: string) {
  return { params: Promise.resolve({ workshop }) }
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

describe('equipment single pages with workshop query', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    defaults()
  })

  it('renders the assets page scoped to ?workshop= and passes it to fetches', async () => {
    const element = await renderContent(AssetsPage, '101-2')
    expect(element.props.workshopCode).toBe('101-2')
    expect(element.props.workshopLabel).toBe('101二车间')
    expect(actions.fetchEquipments).toHaveBeenCalledWith({
      workshop: '101-2',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchEquipmentStatistics).toHaveBeenCalledWith('101-2')
  })

  it('falls back to the default workshop when the query is missing or invalid', async () => {
    const element = await renderContent(AssetsPage)
    expect(element.props.workshopCode).toBe('201-1')
    const invalid = await renderContent(AssetsPage, '999')
    expect(invalid.props.workshopCode).toBe('201-1')
  })

  it('falls back to empty assets data when a fetch fails', async () => {
    actions.fetchEquipments.mockRejectedValue(new Error('boom'))
    const element = await renderContent(AssetsPage, '201-1')
    expect(element.props.workshopCode).toBe('201-1')
    expect(element.props.initialEquipments).toEqual([])
  })

  it('renders the maintenance page scoped to ?workshop=', async () => {
    const element = await renderContent(MaintenancePage, '201-1')
    expect(element.props.workshopCode).toBe('201-1')
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
  })

  it('maintenance degrades per-domain when individual fetches fail', async () => {
    actions.fetchWorkOrders.mockRejectedValue(new Error('boom'))
    const element = await renderContent(MaintenancePage, '103')
    expect(element.props.workshopCode).toBe('103')
    expect(element.props.initialWorkOrders).toEqual([])
    // 其余域不受影响
    expect(element.props.initialCalibrationPlans).toEqual([])
    expect(actions.fetchCalibrationPlans).toHaveBeenCalled()
  })

  it('renders the spare parts page scoped to ?workshop=', async () => {
    const element = await renderContent(SparePartsPage, '201-1')
    expect(element.props.workshopCode).toBe('201-1')
    expect(actions.fetchSpareParts).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchStockWarnings).toHaveBeenCalledWith('201-1')
  })

  it('renders the inspection page with the workshop label', async () => {
    const element = await renderContent(InspectionPage, '201-1')
    expect(element.props.workshopCode).toBe('201-1')
    expect(element.props.workshopLabel).toBe('201一车间')
  })

  it('renders the personnel page scoped to ?workshop=', async () => {
    const provider = await renderContent(PersonnelPage, '101-1')
    // PersonnelQueryProvider（透传 mock）内层才是页面组件
    const page = (provider.props as unknown as { children: PageElement }).children
    expect(page.props.workshopCode).toBe('101-1')
    expect(page.props.workshopLabel).toBe('101一车间')
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

describe('equipment legacy workshop redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    defaults()
  })

  it.each([
    ['台账', AssetsWorkshopRedirect, '/equipment/assets?workshop=101-2'],
    ['维护保养', MaintenanceWorkshopRedirect, '/equipment/maintenance?workshop=201-3'],
    ['备件管理', SparePartsWorkshopRedirect, '/equipment/spare-parts?workshop=103'],
    ['人员配置', PersonnelWorkshopRedirect, '/equipment/personnel?workshop=101-1'],
    ['巡检', InspectionWorkshopRedirect, '/equipment/inspection?workshop=203'],
  ])('%s 旧车间路径重定向到 ?workshop= 查询参数', async (_name, Page, target) => {
    const workshop = target.split('=')[1]
    await expect(Page(legacyParams(workshop))).rejects.toThrow('REDIRECT')
    expect(navigation.redirect).toHaveBeenCalledWith(target)
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
