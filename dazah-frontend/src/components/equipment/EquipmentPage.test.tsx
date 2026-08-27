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
vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => equipmentStore }))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Button = ({ children, onClick }: { children?: ReactNode; onClick?: () => void }) =>
    createElement('button', { onClick }, children)
  const Tabs = ({ items }: { items: Array<{ children: ReactNode; label: string }> }) =>
    createElement('div', null, items.map((item) => createElement('section', { key: item.label }, item.children)))
  return { App: Wrapper, Button, ConfigProvider: Wrapper, Tabs }
})

vi.mock('@ant-design/icons', () => ({
  MenuFoldOutlined: () => null,
  MenuUnfoldOutlined: () => null,
  ReloadOutlined: () => null,
}))

vi.mock('./StatsCards', () => ({ StatsCards: () => <div>统计卡片</div> }))
vi.mock('./EquipmentTable', () => ({ EquipmentTable: () => <div>设备表格</div> }))
vi.mock('./CategoryTree', () => ({ CategoryTree: () => <div>分类树</div> }))
vi.mock('./LocationTree', () => ({ LocationTree: () => <div>位置树</div> }))
vi.mock('./EquipmentDrawer', () => ({ EquipmentDrawer: () => null }))
vi.mock('./CategoryDrawer', () => ({ CategoryDrawer: () => null }))
vi.mock('./LocationDrawer', () => ({ LocationDrawer: () => null }))
vi.mock('./RepairDrawer', () => ({ RepairDrawer: () => null }))

import { EquipmentPage } from './EquipmentPage'
import type { EquipmentCategory, EquipmentStatistics, Location } from '@/types/equipment'

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

const department = (id: string, name: string) => ({
  id,
  name,
  leader_name: null,
  leader_user_id: null,
  leader_id: null,
})

describe('EquipmentPage data lifecycle', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    api.fetchCategoriesClient.mockResolvedValue([category('fallback-category')])
    api.fetchLocationsClient.mockResolvedValue([location('fallback-location')])
    api.fetchDepartmentsClient.mockResolvedValue([department('fallback-department', '设备部')])
    api.fetchEquipmentsClient.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('hydrates SSR data, compensates missing store data, and requests the active filters', async () => {
    const initialCategory = category('initial-category')
    const initialLocation = location('initial-location')

    await act(async () => {
      root.render(
        <EquipmentPage
          initialCategories={[initialCategory]}
          initialLocations={[initialLocation]}
          initialEquipments={[]}
          initialTotal={3}
          initialStatistics={statistics}
          initialDepartments={[department('initial-department', '工程设备部')]}
        />,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(equipmentStore.setCategories).toHaveBeenCalledWith([initialCategory])
    expect(equipmentStore.setLocations).toHaveBeenCalledWith([initialLocation])
    expect(equipmentStore.setTotal).toHaveBeenCalledWith(3)
    expect(api.fetchCategoriesClient).toHaveBeenCalledOnce()
    expect(api.fetchLocationsClient).toHaveBeenCalledOnce()
    expect(api.fetchDepartmentsClient).toHaveBeenCalledOnce()
    expect(api.fetchEquipmentsClient).toHaveBeenCalledWith({
      category_id: 'category-1',
      location_id: 'location-1',
      department_id: 'department-1',
      status: '在用',
      keyword: '反应釜',
      page: 1,
      page_size: 20,
    })
    expect(equipmentStore.setLoading).toHaveBeenNthCalledWith(1, true)
    expect(equipmentStore.setLoading).toHaveBeenLastCalledWith(false)
  })

  it('rehydrates when server props change', async () => {
    const renderPage = (id: string) => (
      <EquipmentPage
        initialCategories={[category(id)]}
        initialLocations={[location(id)]}
        initialEquipments={[]}
        initialTotal={id === 'first' ? 1 : 2}
        initialStatistics={statistics}
        initialDepartments={[department(id, `部门-${id}`)]}
      />
    )

    await act(async () => {
      root.render(renderPage('first'))
      await Promise.resolve()
    })
    await act(async () => {
      root.render(renderPage('second'))
      await Promise.resolve()
    })

    expect(equipmentStore.setCategories).toHaveBeenCalledWith([expect.objectContaining({ id: 'second' })])
    expect(equipmentStore.setLocations).toHaveBeenCalledWith([expect.objectContaining({ id: 'second' })])
    expect(equipmentStore.setDepartments).toHaveBeenCalledWith([department('second', '部门-second')])
    expect(equipmentStore.setTotal).toHaveBeenCalledWith(2)
  })
})
