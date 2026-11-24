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
  equipments: [] as Array<{ id: string; equipment_no: string; name: string; importance: string }>,
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
  setStatusFilter: vi.fn(),
  setTotal: vi.fn(),
}))

const qrcodeApi = vi.hoisted(() => ({
  fetchEquipmentQrcodePdf: vi.fn(),
  message: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/api/equipment-client', () => api)
vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => equipmentStore }))
vi.mock('@/lib/api/client/equipmentQrcode', () => ({
  fetchEquipmentQrcodePdf: qrcodeApi.fetchEquipmentQrcodePdf,
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const App = Object.assign(Wrapper, { useApp: () => ({ message: qrcodeApi.message }) })
  const Button = ({ children, onClick }: { children?: ReactNode; onClick?: () => void }) =>
    createElement('button', { onClick }, children)
  return { App, Button }
})

vi.mock('@ant-design/icons', () => ({
  MenuFoldOutlined: () => null,
  MenuUnfoldOutlined: () => null,
  QrcodeOutlined: () => null,
  ReloadOutlined: () => null,
}))

// 子组件用占位替换并记录收到的 props，便于断言页面下发的数据与回调
const children = vi.hoisted(() => ({
  tableProps: [] as Array<Record<string, unknown>>,
  repairDrawerProps: [] as Array<Record<string, unknown>>,
}))
vi.mock('./EquipmentTable', () => ({
  EquipmentTable: (props: Record<string, unknown>) => {
    children.tableProps.push(props)
    return <div>设备表格</div>
  },
}))
vi.mock('./EquipmentDrawer', () => ({ EquipmentDrawer: () => null }))
vi.mock('./RepairDrawer', () => ({
  RepairDrawer: (props: Record<string, unknown>) => {
    children.repairDrawerProps.push(props)
    return null
  },
}))

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
    children.tableProps.length = 0
    children.repairDrawerProps.length = 0
    equipmentStore.equipments = []
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

  it('hydrates SSR data, compensates missing store data, and requests the active filters', async () => {
    const initialCategory = category('initial-category')
    const initialLocation = location('initial-location')
    const initialStatistics: EquipmentStatistics = {
      ...statistics,
      total: 3,
      by_status: { ...statistics.by_status, 在用: 2 },
    }

    await act(async () => {
      root.render(
        <EquipmentPage
          workshopCode="201-1"
          initialCategories={[initialCategory]}
          initialLocations={[initialLocation]}
          initialEquipments={[]}
          initialTotal={3}
          initialStatistics={initialStatistics}
          initialDepartments={[department('initial-department', '工程设备部')]}
        />,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    // 状态筛选按钮行：展示统计数，点击切换 statusFilter
    const text = container.textContent || ''
    expect(text).toContain('总数')
    expect(text).toContain('在用')
    expect(text).toContain('维修中')
    expect(text).toContain('停用')
    expect(equipmentStore.setStatistics).toHaveBeenCalledWith(initialStatistics)
    const allPill = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('总数'),
    )
    expect(allPill).toBeTruthy()
    act(() => {
      allPill?.click()
    })
    expect(equipmentStore.setStatusFilter).toHaveBeenCalledWith('')

    expect(equipmentStore.setCategories).toHaveBeenCalledWith([initialCategory])
    expect(equipmentStore.setLocations).toHaveBeenCalledWith([initialLocation])
    expect(equipmentStore.setTotal).toHaveBeenCalledWith(3)
    expect(api.fetchCategoriesClient).toHaveBeenCalledOnce()
    expect(api.fetchLocationsClient).toHaveBeenCalledOnce()
    expect(api.fetchDepartmentsClient).toHaveBeenCalledOnce()
    expect(api.fetchEquipmentStatisticsClient).toHaveBeenCalledWith('201-1')
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
    expect(equipmentStore.setLoading).toHaveBeenNthCalledWith(1, true)
    expect(equipmentStore.setLoading).toHaveBeenLastCalledWith(false)
  })

  it('rehydrates when server props change', async () => {
    const renderPage = (id: string) => (
      <EquipmentPage
        workshopCode="201-1"
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

  it('exports workshop qrcode PDF from the toolbar button', async () => {
    qrcodeApi.fetchEquipmentQrcodePdf.mockResolvedValueOnce(undefined)

    await act(async () => {
      root.render(
        <EquipmentPage
          workshopCode="201-1"
          initialCategories={[]}
          initialLocations={[]}
          initialEquipments={[]}
          initialTotal={0}
          initialStatistics={statistics}
          initialDepartments={[]}
        />,
      )
      await Promise.resolve()
    })

    const exportButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('导出设备码'),
    )
    expect(exportButton).toBeTruthy()

    await act(async () => {
      exportButton!.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(qrcodeApi.fetchEquipmentQrcodePdf).toHaveBeenCalledWith('201-1')
    expect(qrcodeApi.message.success).toHaveBeenCalled()
  })

  it('shows an error message when qrcode export fails', async () => {
    qrcodeApi.fetchEquipmentQrcodePdf.mockRejectedValueOnce(new Error('导出超时（>30秒），请重试'))

    await act(async () => {
      root.render(
        <EquipmentPage
          workshopCode="201-1"
          initialCategories={[]}
          initialLocations={[]}
          initialEquipments={[]}
          initialTotal={0}
          initialStatistics={statistics}
          initialDepartments={[]}
        />,
      )
      await Promise.resolve()
    })

    const exportButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('导出设备码'),
    )
    await act(async () => {
      exportButton!.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(qrcodeApi.message.error).toHaveBeenCalledWith('导出超时（>30秒），请重试')
  })

  const renderPage = async () => {
    await act(async () => {
      root.render(
        <EquipmentPage
          workshopCode="201-1"
          initialCategories={[]}
          initialLocations={[]}
          initialEquipments={[]}
          initialTotal={0}
          initialStatistics={statistics}
          initialDepartments={[]}
        />,
      )
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  const buttonNamed = (text: string) =>
    Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes(text),
    )

  it('resets the category and location filters from the toolbar', async () => {
    await renderPage()

    const reset = buttonNamed('重置筛选')
    expect(reset).toBeTruthy()
    await act(async () => {
      reset!.click()
    })
    expect(equipmentStore.setSelectedCategory).toHaveBeenCalledWith(null)
    expect(equipmentStore.setSelectedLocation).toHaveBeenCalledWith(null)
  })

  it('forwards paging from the table and hands the equipment list to the repair drawer', async () => {
    equipmentStore.equipments = [
      { id: 'eq-1', equipment_no: 'SB-1', name: '反应釜', importance: '高' },
      { id: 'eq-2', equipment_no: 'SB-2', name: '离心泵', importance: '中' },
    ]
    await renderPage()

    expect(children.repairDrawerProps.at(-1)?.equipments).toEqual([
      { id: 'eq-1', equipment_no: 'SB-1', name: '反应釜', importance: '高' },
      { id: 'eq-2', equipment_no: 'SB-2', name: '离心泵', importance: '中' },
    ])
    const table = children.tableProps.at(-1) as { onPageChange: (page: number, size: number) => void }
    await act(async () => {
      table.onPageChange(3, 50)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(api.fetchEquipmentsClient).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 3, page_size: 50 }),
    )
  })
})
