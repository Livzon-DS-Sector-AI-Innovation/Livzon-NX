/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'

const storeMock = vi.hoisted(() => ({
  equipments: [] as Array<import('@/types/equipment').Equipment>,
  total: 0,
  statusFilter: '',
  keyword: '',
  departments: [] as Array<{ id: string; name: string }>,
  departmentFilter: null as string | null,
  categories: [{ id: 'cat-1', name: '反应设备' }] as unknown as Array<import('@/types/equipment').EquipmentCategory>,
  locations: [{ id: 'loc-1', name: '一楼泵房' }] as unknown as Array<import('@/types/equipment').Location>,
  selectedCategory: null as string | null,
  selectedLocation: null as string | null,
  setDepartmentFilter: vi.fn(),
  setStatusFilter: vi.fn(),
  setKeyword: vi.fn(),
  setSelectedCategory: vi.fn(),
  setSelectedLocation: vi.fn(),
  openEquipmentDrawer: vi.fn(),
  openRepairDrawer: vi.fn(),
}))

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => storeMock }))

const importModalMock = vi.hoisted(() => ({
  lastProps: null as Record<string, unknown> | null,
  EquipmentImportModal: (props: Record<string, unknown>) => {
    importModalMock.lastProps = props
    return null
  },
}))
vi.mock('./EquipmentImportModal', () => importModalMock)

import { EquipmentTable } from './EquipmentTable'
import type { Equipment } from '@/types/equipment'

const equipment = (overrides: Partial<Equipment> = {}): Equipment => ({
  id: 'eq-1',
  equipment_no: 'SB-2024-001',
  name: 'R-101反应釜',
  category_ids: ['cat-1'],
  category_names: '反应设备',
  location_id: 'loc-1',
  location_name: '201二车间',
  status: '在用',
  importance: '高',
  model: 'RF-1000',
  specification: null,
  manufacturer: '宁波某设备厂',
  supplier: null,
  production_date: '2024-05-01',
  factory_no: 'FACT-2024-001',
  arrival_date: '2024-06-15',
  commissioning_date: null,
  description: '不锈钢反应釜',
  technical_params: { 功率: '3kW', 容积: '500L' },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: null,
  updated_by: null,
  department_id: null,
  department_name: null,
  responsible_person_id: null,
  responsible_person_name: null,
  ...overrides,
})

// 过滤掉 antd 的表头测量行与展开列表头（无文本）
const headerTitles = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('thead th'))
    .filter((th) => !th.closest('.ant-table-measure-row'))
    .map((th) => th.textContent?.trim() || '')
    .filter(Boolean)

describe('EquipmentTable ledger columns', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    // happy-dom 没有 ResizeObserver，表格组件用它计算滚动高度
    globalThis.ResizeObserver =
      globalThis.ResizeObserver ||
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('renders the simplified ledger field set in order', () => {
    storeMock.equipments = [equipment()]
    storeMock.total = 1
    act(() => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} />
        </AntApp>,
      )
    })
    expect(headerTitles(container)).toEqual([
      '设备编号',
      '设备名称',
      '规格型号',
      '安装地点',
      '状态',
      '操作',
    ])
    const text = container.textContent || ''
    expect(text).toContain('SB-2024-001')
    expect(text).toContain('R-101反应釜')
    expect(text).toContain('RF-1000')
    expect(text).toContain('201二车间')
    // 明细字段折叠进展开行，收起时不显示
    expect(text).not.toContain('宁波某设备厂')
  })

  it('shows placeholders for empty ledger values in the collapsed row', () => {
    storeMock.equipments = [
      equipment({
        id: 'eq-21',
        equipment_no: 'SB-2024-021',
        model: null,
        manufacturer: null,
        technical_params: null,
        factory_no: null,
        description: null,
      }),
    ]
    storeMock.total = 21
    act(() => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} />
        </AntApp>,
      )
    })
    const pagination = container.querySelector('.ant-pagination')
    expect(pagination?.textContent).toContain('21 条')
    // 取第一条数据行
    const firstRow = container.querySelector('.ant-table-tbody .ant-table-row')
    expect(firstRow?.textContent).toContain('SB-2024-021')
    expect(firstRow?.textContent).toContain('-')
    expect(firstRow?.textContent).not.toContain('功率')
  })

  it('expands a row to reveal the full factory details', () => {
    storeMock.equipments = [equipment()]
    storeMock.total = 1
    act(() => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} />
        </AntApp>,
      )
    })
    expect(container.textContent).not.toContain('宁波某设备厂')
    const expandIcon = container.querySelector('.ant-table-row-expand-icon')
    expect(expandIcon).toBeTruthy()
    act(() => {
      expandIcon?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const expandedRow = container.querySelector('.ant-table-expanded-row')
    expect(expandedRow?.textContent).toContain('宁波某设备厂')
    expect(expandedRow?.textContent).toContain('FACT-2024-001')
    expect(expandedRow?.textContent).toContain('2024-05-01')
    expect(expandedRow?.textContent).toContain('2024-06-15')
    expect(expandedRow?.textContent).toContain('功率：3kW；容积：500L')
    expect(expandedRow?.textContent).toContain('不锈钢反应釜')
  })
})

describe('EquipmentTable 导入入口', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.ResizeObserver =
      globalThis.ResizeObserver ||
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    importModalMock.lastProps = null
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('opens and closes the import modal from the toolbar button', () => {
    act(() => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} workshopCode="103" />
        </AntApp>,
      )
    })
    expect(importModalMock.lastProps?.open).toBe(false)
    expect(importModalMock.lastProps?.workshopCode).toBe('103')
    // antd 对两字按钮自动插入空格（「导 入」），按单字匹配
    const button = Array.from(document.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('导'),
    )
    expect(button).toBeTruthy()
    act(() => {
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(importModalMock.lastProps?.open).toBe(true)
    const onClose = importModalMock.lastProps?.onClose as () => void
    act(() => {
      onClose()
    })
    expect(importModalMock.lastProps?.open).toBe(false)
  })

  it('opens the repair and edit drawers from the row actions, and the create drawer from the toolbar', async () => {
    storeMock.equipments = [equipment()]
    storeMock.total = 1
    await act(async () => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} />
        </AntApp>,
      )
    })
    const actions = Array.from(container.querySelectorAll('.ant-table-tbody .ant-table-row [role="button"]'))
    expect(actions.map((node) => node.textContent?.trim())).toEqual(['报修', '编辑'])

    await act(async () => { actions[0].dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(storeMock.openRepairDrawer).toHaveBeenCalledWith('eq-1')
    await act(async () => { actions[1].dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(storeMock.openEquipmentDrawer).toHaveBeenCalledWith(expect.objectContaining({ id: 'eq-1' }))

    const create = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('新增'),
    )
    await act(async () => { create?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(storeMock.openEquipmentDrawer).toHaveBeenCalledWith()
  })

  it('tracks the keyword as typed and applies it with the enter key', async () => {
    storeMock.equipments = [equipment()]
    storeMock.total = 1
    const onPageChange = vi.fn()
    await act(async () => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={onPageChange} resetKey={0} />
        </AntApp>,
      )
    })
    const search = container.querySelector('input[placeholder*="搜索"]') as HTMLInputElement
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(search, '泵')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(storeMock.setKeyword).toHaveBeenCalledWith('泵')
    await act(async () => {
      search.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }))
    })
    expect(onPageChange).toHaveBeenCalledWith(1, 20)
  })
})
