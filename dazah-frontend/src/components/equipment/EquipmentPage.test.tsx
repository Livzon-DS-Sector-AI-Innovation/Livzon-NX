/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchCategoriesClient: vi.fn(),
  fetchDepartmentsClient: vi.fn(),
  fetchEquipmentsClient: vi.fn(),
  fetchEquipmentStatisticsClient: vi.fn(),
  fetchLocationsClient: vi.fn(),
}))

const equipmentStore = vi.hoisted(() => ({
  categories: [] as Array<{ id: string }>,
  departments: [] as Array<{ id: string }>,
  equipments: [],
  failureCodes: { actions: [], causes: [], symptoms: [] },
  keyword: '反应釜',
  loading: false,
  locations: [] as Array<{ id: string }>,
  selectedCategory: 'category-1',
  selectedLocation: 'location-1',
  statistics: null,
  statusFilter: '在用',
  departmentFilter: 'department-1',
  setCategories: vi.fn(),
  setDepartments: vi.fn(),
  setEquipments: vi.fn(),
  setLoading: vi.fn(),
  setLocations: vi.fn(),
  setSelectedCategory: vi.fn(),
  setSelectedLocation: vi.fn(),
  setStatistics: vi.fn(),
  setTotal: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => api)
vi.mock('@/stores/equipment', () => ({ useEquipmentStore: (selector?: (s: typeof equipmentStore) => unknown) => (selector ? selector(equipmentStore) : equipmentStore) }))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Button = ({ children, onClick }: { children?: ReactNode; onClick?: () => void }) =>
    createElement('button', { onClick }, children)
  const Tabs = ({ items }: { items: Array<{ children: ReactNode; label: string }> }) =>
    createElement('div', null, items.map((item) => createElement('section', { key: item.label }, item.children)))
  return { App: Wrapper, Button, Tabs }
})

vi.mock('@ant-design/icons', () => ({
  MenuFoldOutlined: () => null,
  MenuUnfoldOutlined: () => null,
  ReloadOutlined: () => null,
}))

const tablePropsLog: Array<Record<string, unknown>> = []
vi.mock('./StatsCards', () => ({ StatsCards: () => <div>统计卡片</div> }))
vi.mock('./EquipmentTable', () => ({
  EquipmentTable: (props: Record<string, unknown>) => {
    tablePropsLog.push(props)
    return <div>设备表格</div>
  },
}))
vi.mock('./CategoryTree', () => ({ CategoryTree: () => <div>分类树</div> }))
vi.mock('./LocationTree', () => ({ LocationTree: () => <div>位置树</div> }))
const drawerPropsLog: Array<Record<string, unknown>> = []
vi.mock('./EquipmentDrawer', () => ({
  EquipmentDrawer: (props: Record<string, unknown>) => {
    drawerPropsLog.push(props)
    return null
  },
}))
vi.mock('./CategoryDrawer', () => ({
  CategoryDrawer: (props: Record<string, unknown>) => {
    drawerPropsLog.push(props)
    return null
  },
}))
vi.mock('./LocationDrawer', () => ({ LocationDrawer: () => null }))
vi.mock('./RepairDrawer', () => ({ RepairDrawer: () => null }))

import { EquipmentPage } from './EquipmentPage'
import type {
  DepartmentOption,
  Equipment,
  EquipmentCategory,
  EquipmentStatistics,
  Location,
} from '@/types/equipment'

const category = (id: string): EquipmentCategory => ({
  id,
  name: `分类-${id}`,
  code: id,
  parent_id: null,
  description: null,
  created_at: '2026-08-20T00:00:00Z',
  updated_at: '2026-08-20T00:00:00Z',
  created_by: null,
  updated_by: null,
})

const location = (id: string): Location => ({
  id,
  name: `位置-${id}`,
  code: id,
  parent_id: null,
  description: null,
  created_at: '2026-08-20T00:00:00Z',
  updated_at: '2026-08-20T00:00:00Z',
  created_by: null,
  updated_by: null,
})

const statistics: EquipmentStatistics = {
  total: 0,
  by_status: { 在用: 0, 备用: 0, 维修中: 0, 停用: 0, 报废: 0 },
  by_category: {},
  by_location: {},
}

const equipmentItem = (id: string): Equipment =>
  ({
    id,
    equipment_no: `SB-${id}`,
    name: `设备-${id}`,
    workshop_code: '201-1',
    asset_value: null,
    depreciation_years: null,
    data_issue_note: null,
  }) as unknown as Equipment

const department = (id: string, name: string) => ({
  id,
  name,
  leader_name: null,
  leader_user_id: null,
  leader_id: null,
})

function pageProps(overrides: {
  initialCategories?: EquipmentCategory[]
  initialLocations?: Location[]
  initialEquipments?: Equipment[]
  initialTotal?: number
  initialDepartments?: DepartmentOption[]
} = {}) {
  return {
    workshopCode: '201-1',
    initialCategories: [category('initial-category')],
    initialLocations: [location('initial-location')],
    initialEquipments: [equipmentItem('eq-1')],
    initialTotal: 1,
    initialStatistics: statistics,
    initialDepartments: [department('initial-department', '工程设备部')],
    ...overrides,
  }
}

describe('EquipmentPage data lifecycle', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    tablePropsLog.length = 0
    drawerPropsLog.length = 0
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    api.fetchCategoriesClient.mockResolvedValue([category('fallback-category')])
    api.fetchLocationsClient.mockResolvedValue([location('fallback-location')])
    api.fetchDepartmentsClient.mockResolvedValue([department('fallback-department', '设备部')])
    api.fetchEquipmentsClient.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    api.fetchEquipmentStatisticsClient.mockResolvedValue(statistics)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('renders SSR data directly without refetching when initial data is present', async () => {
    await act(async () => {
      root.render(<EquipmentPage {...pageProps()} />)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(tablePropsLog.length).toBeGreaterThan(0)
    expect(tablePropsLog.at(-1)).toMatchObject({
      data: [expect.objectContaining({ id: 'eq-1' })],
      total: 1,
      page: 1,
      pageSize: 20,
    })
    // 非空 SSR 数据视为新鲜，不触发客户端补偿请求
    expect(api.fetchEquipmentsClient).not.toHaveBeenCalled()
    expect(api.fetchCategoriesClient).not.toHaveBeenCalled()
    expect(api.fetchLocationsClient).not.toHaveBeenCalled()
    expect(api.fetchDepartmentsClient).not.toHaveBeenCalled()
  })

  it('compensates with client fetches when SSR data is empty and applies active filters', async () => {
    await act(async () => {
      root.render(
        <EquipmentPage
          {...pageProps({
            initialCategories: [],
            initialLocations: [],
            initialEquipments: [],
            initialTotal: 0,
            initialDepartments: [],
          })}
        />,
      )
      await Promise.resolve()
      await Promise.resolve()
      await new Promise((resolve) => setTimeout(resolve, 20))
      await Promise.resolve()
    })

    expect(api.fetchCategoriesClient).toHaveBeenCalledOnce()
    expect(api.fetchLocationsClient).toHaveBeenCalledOnce()
    expect(api.fetchDepartmentsClient).toHaveBeenCalledOnce()
    // 列表查询携带 store 中的活跃筛选
    expect(api.fetchEquipmentsClient).toHaveBeenCalledWith({
      workshop: '201-1',
      category_id: 'category-1',
      location_id: 'location-1',
      department_id: 'department-1',
      status: '在用',
      keyword: '反应釜',
      page: 1,
      page_size: 20,
    })
  })

  it('refreshes the equipment query when the drawer reports a mutation', async () => {
    api.fetchEquipmentsClient.mockClear()
    await act(async () => {
      root.render(<EquipmentPage {...pageProps()} />)
      await Promise.resolve()
    })
    // 空列表触发一次补偿查询后清零，验证抽屉回调驱动刷新
    await act(async () => {
      const equipmentDrawerProps = drawerPropsLog.find(
        (props) => 'onRefresh' in props && 'workshopCode' in props,
      ) as { onRefresh: () => void } | undefined
      equipmentDrawerProps?.onRefresh()
      await Promise.resolve()
      await Promise.resolve()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(api.fetchEquipmentsClient).toHaveBeenCalled()
    expect(api.fetchEquipmentStatisticsClient).toHaveBeenCalled()
  })
})
