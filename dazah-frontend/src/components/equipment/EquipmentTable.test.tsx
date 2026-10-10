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
  categories: [] as Array<import('@/types/equipment').EquipmentCategory>,
  locations: [] as Array<import('@/types/equipment').Location>,
  setDepartmentFilter: vi.fn(),
  setStatusFilter: vi.fn(),
  setKeyword: vi.fn(),
  openEquipmentDrawer: vi.fn(),
  openRepairDrawer: vi.fn(),
}))

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => storeMock }))
vi.mock('@/actions/equipment', () => ({ deleteEquipment: vi.fn() }))
vi.mock('./EquipmentDetailDrawer', () => ({ EquipmentDetailDrawer: () => null }))

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

const headerTitles = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('thead th')).map(
    (th) => th.textContent?.trim() || '',
  )

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

  it('renders the factory ledger field set in order', () => {
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
      '序号',
      '设备编号',
      '设备名称',
      '规格型号',
      '技术参数',
      '生产厂家',
      '出厂日期',
      '出厂编号',
      '入厂日期',
      '安装地点',
      '备注',
      '操作',
    ])
    const text = container.textContent || ''
    expect(text).toContain('SB-2024-001')
    expect(text).toContain('RF-1000')
    expect(text).toContain('功率：3kW；容积：500L')
    expect(text).toContain('宁波某设备厂')
    expect(text).toContain('FACT-2024-001')
    expect(text).toContain('2024-06-15')
    expect(text).toContain('201二车间')
    expect(text).toContain('不锈钢反应釜')
  })

  it('numbers rows and shows placeholders for empty ledger values', () => {
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
    // 跳过 antd 的表头测量行，取第一条数据行
    const firstRow = container.querySelector('.ant-table-tbody .ant-table-row')
    expect(firstRow?.querySelector('td')?.textContent?.trim()).toBe('1')
    expect(firstRow?.textContent).toContain('SB-2024-021')
    expect(firstRow?.textContent).toContain('-')
    expect(firstRow?.textContent).not.toContain('功率')
  })

  it('marks only the flagged cells red, not the whole row', () => {
    storeMock.equipments = [
      equipment({
        id: 'eq-31',
        equipment_no: 'SB-2024-031',
        production_date: null,
        data_issue_note: '【出厂日期】原文「201年9月」无法识别，已置空待修正',
      }),
    ]
    storeMock.total = 1
    act(() => {
      root.render(
        <AntApp>
          <EquipmentTable onPageChange={() => {}} resetKey={0} />
        </AntApp>,
      )
    })
    const row = document.querySelector('.ant-table-tbody .ant-table-row') as HTMLElement
    // 整行不标红（悬停提示保留）
    expect(row.style.color).toBe('')
    expect(row.getAttribute('title')).toContain('201年9月')
    const cells = Array.from(row.querySelectorAll('td'))
    // 仅问题字段的单元格带 style（红色文字）；无问题的列没有 style 属性
    const styledSpan = (cellIndex: number) =>
      cells[cellIndex]?.querySelector('span[style]')
    // 出厂日期列（第 7 列，含序号）标红
    expect(styledSpan(6)).not.toBeNull()
    expect(styledSpan(6)?.textContent).toBe('-')
    // 其余列不标红
    expect(styledSpan(1)).toBeNull()
    expect(styledSpan(2)).toBeNull()
  })
})
