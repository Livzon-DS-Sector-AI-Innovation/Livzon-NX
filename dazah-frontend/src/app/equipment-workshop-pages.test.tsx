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
  }
})

import AssetsRedirect from '@/app/(dashboard)/equipment/assets/page'
import AssetsWorkshopPage from '@/app/(dashboard)/equipment/assets/[workshop]/page'
import InspectionRedirect from '@/app/(dashboard)/equipment/inspection/page'
import InspectionWorkshopPage from '@/app/(dashboard)/equipment/inspection/[workshop]/page'
import MaintenanceRedirect from '@/app/(dashboard)/equipment/maintenance/page'
import MaintenanceWorkshopPage from '@/app/(dashboard)/equipment/maintenance/[workshop]/page'
import PersonnelRedirect from '@/app/(dashboard)/equipment/personnel/page'
import PersonnelWorkshopPage from '@/app/(dashboard)/equipment/personnel/[workshop]/page'
import SparePartsRedirect from '@/app/(dashboard)/equipment/spare-parts/page'
import SparePartsWorkshopPage from '@/app/(dashboard)/equipment/spare-parts/[workshop]/page'
import StatsPage from '@/app/(dashboard)/equipment/stats/page'

function params(workshop: string) {
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

describe('equipment workshop server pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    defaults()
  })

  it('renders the assets page scoped to the workshop and passes workshop to fetches', async () => {
    const element = (await AssetsWorkshopPage(params('101-2'))) as {
      props: Record<string, unknown>
    }
    expect(element.props.workshopCode).toBe('101-2')
    expect(element.props.workshopLabel).toBe('101二车间')
    expect(actions.fetchEquipments).toHaveBeenCalledWith({
      workshop: '101-2',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchEquipmentStatistics).toHaveBeenCalledWith('101-2')
  })

  it('rejects unknown workshops with notFound', async () => {
    await expect(AssetsWorkshopPage(params('999'))).rejects.toThrow('NOT_FOUND')
    expect(navigation.notFound).toHaveBeenCalled()
  })

  it('falls back to empty assets data when a fetch fails', async () => {
    actions.fetchEquipments.mockRejectedValue(new Error('boom'))
    const element = (await AssetsWorkshopPage(params('201-1'))) as {
      props: Record<string, unknown>
    }
    expect(element.props.workshopCode).toBe('201-1')
    expect(element.props.initialEquipments).toEqual([])
  })

  it('renders the maintenance page scoped to the workshop', async () => {
    const element = (await MaintenanceWorkshopPage(params('201-1'))) as {
      props: Record<string, unknown>
    }
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

  it('rejects unknown workshops on the maintenance page', async () => {
    await expect(MaintenanceWorkshopPage(params('bad'))).rejects.toThrow('NOT_FOUND')
  })

  it('falls back to empty maintenance data when a fetch fails', async () => {
    actions.fetchWorkOrders.mockRejectedValue(new Error('boom'))
    const element = (await MaintenanceWorkshopPage(params('103'))) as {
      props: Record<string, unknown>
    }
    expect(element.props.workshopCode).toBe('103')
    expect(element.props.initialWorkOrders).toEqual([])
  })

  it('renders the spare parts page scoped to the workshop', async () => {
    const element = (await SparePartsWorkshopPage(params('201-1'))) as {
      props: Record<string, unknown>
    }
    expect(element.props.workshopCode).toBe('201-1')
    expect(actions.fetchSpareParts).toHaveBeenCalledWith({
      workshop: '201-1',
      page: 1,
      page_size: 20,
    })
    expect(actions.fetchStockWarnings).toHaveBeenCalledWith('201-1')
  })

  it('rejects unknown workshops on the spare parts page', async () => {
    await expect(SparePartsWorkshopPage(params('bad'))).rejects.toThrow('NOT_FOUND')
  })

  it('renders the inspection page with the workshop label', async () => {
    const element = (await InspectionWorkshopPage(params('201-1'))) as {
      props: Record<string, unknown>
    }
    expect(element.props.workshopCode).toBe('201-1')
    expect(element.props.workshopLabel).toBe('201一车间')
  })

  it('rejects unknown workshops on the inspection page', async () => {
    await expect(InspectionWorkshopPage(params('bad'))).rejects.toThrow('NOT_FOUND')
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

    const element = (await StatsPage()) as {
      props: { initialData: { inspectionSummaries: unknown } }
    }

    expect(actions.fetchInspectionTodaySummaries).toHaveBeenCalled()
    expect(element.props.initialData.inspectionSummaries).toEqual(summaries)
  })

  it('degrades to empty inspection summaries when the fetch rejects', async () => {
    actions.fetchInspectionTodaySummaries.mockRejectedValue(new Error('boom'))

    const element = (await StatsPage()) as {
      props: { initialData: { inspectionSummaries: unknown } }
    }

    expect(element.props.initialData.inspectionSummaries).toEqual([])
  })

  it('renders the personnel page scoped to the workshop', async () => {
    const element = (await PersonnelWorkshopPage(params('201-1'))) as {
      props: { children: { props: Record<string, unknown> } }
    }
    const page = element.props.children
    expect(page.props.workshopCode).toBe('201-1')
    expect(page.props.workshopLabel).toBe('201一车间')
  })

  it('rejects unknown workshops on the personnel page', async () => {
    await expect(PersonnelWorkshopPage(params('bad'))).rejects.toThrow('NOT_FOUND')
  })

  it.each([
    ['台账', AssetsRedirect, '/equipment/assets/201-1'],
    ['维护保养', MaintenanceRedirect, '/equipment/maintenance/201-1'],
    ['备件管理', SparePartsRedirect, '/equipment/spare-parts/201-1'],
    ['人员配置', PersonnelRedirect, '/equipment/personnel/201-1'],
    ['巡检', InspectionRedirect, '/equipment/inspection/201-1'],
  ])('%s 旧入口重定向到 201一车间', (_name, Page, target) => {
    expect(() => (Page as () => void)()).toThrow('REDIRECT')
    expect(navigation.redirect).toHaveBeenCalledWith(target)
  })
})
