/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMaintainersClient: vi.fn(),
  fetchWorkOrderByIdClient: vi.fn(),
  fetchSparePartsClient: vi.fn(),
  fetchWorkOrderMaterialsClient: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/equipment-client')>()
  return { ...actual, ...api }
})

const actions = vi.hoisted(() => ({
  assignWorkOrder: vi.fn(),
  startWorkOrder: vi.fn(),
  completeWorkOrder: vi.fn(),
  verifyWorkOrder: vi.fn(),
  closeWorkOrder: vi.fn(),
  claimWorkOrder: vi.fn(),
  consumeMaterials: vi.fn(),
}))

vi.mock('@/actions/equipment', () => actions)

import { WorkOrderDetailDrawer } from './WorkOrderDetailDrawer'
import { useEquipmentStore } from '@/stores/equipment'
import type { WorkOrder } from '@/types/equipment'

const baseWorkOrder = {
  id: 'wo-1',
  work_order_no: 'GD-20261019-001',
  status: '执行中',
  order_type: '故障维修',
  priority: '高',
  equipment_id: 'eq-1',
  equipment_name: '方锥混合机',
  fault_description: '异响',
  reported_at: '2026-10-18T08:00:00Z',
  actual_duration: 90,
} as unknown as WorkOrder

let root: Root | null = null

function renderDrawer() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(
      <AntApp>
        <WorkOrderDetailDrawer onRefresh={vi.fn()} />
      </AntApp>,
    )
  })
}

function openWith(workOrder: WorkOrder) {
  act(() => {
    useEquipmentStore.setState({
      workOrderDetailOpen: true,
      viewingWorkOrder: workOrder,
    })
  })
}

beforeEach(() => {
  api.fetchMaintainersClient.mockResolvedValue([])
  api.fetchSparePartsClient.mockResolvedValue({
    items: [
      {
        id: 'sp-1', code: 'BJ-001', name: '滤芯', specification: null,
        unit: '个', category: null, default_supplier: null, unit_price: null,
        min_qty: 5, current_qty: 20, is_active: true,
        created_at: '', updated_at: '', created_by: null, updated_by: null,
      },
    ],
    total: 1, page: 1, page_size: 200,
  })
  api.fetchWorkOrderMaterialsClient.mockResolvedValue([
    {
      id: 'mat-1', work_order_id: 'wo-1', spare_part_id: 'sp-1',
      spare_part_code: 'BJ-001', spare_part_name: '滤芯',
      spare_part_unit: '个', quantity: 2,
      created_at: '2026-10-19T02:00:00Z', remark: null,
    },
  ])
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
  useEquipmentStore.setState({
    workOrderDetailOpen: false,
    viewingWorkOrder: null,
  })
  vi.clearAllMocks()
})

describe('WorkOrderDetailDrawer 领料', () => {
  it('维修期间展示领料入口与既有领料记录', async () => {
    renderDrawer()
    openWith(baseWorkOrder)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const text = document.body.textContent || ''
    expect(text).toContain('领料记录')
    expect(text).toContain('BJ-001')
    // 领料按钮（执行中可领）
    const consumeBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('领料'))
    expect(consumeBtn).toBeTruthy()
  })

  it('已完成/已关闭工单保留领料记录但不再提供领料入口', async () => {
    renderDrawer()
    openWith({ ...baseWorkOrder, status: '已关闭' } as WorkOrder)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    const text = document.body.textContent || ''
    expect(text).toContain('领料记录')
    expect(text).toContain('BJ-001')
    const consumeBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent === '领料')
    expect(consumeBtn).toBeUndefined()
  })

  it('领料取数使用工单物料接口并携带备件下拉', async () => {
    renderDrawer()
    openWith(baseWorkOrder)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    expect(api.fetchWorkOrderMaterialsClient).toHaveBeenCalledWith('wo-1')
    expect(api.fetchSparePartsClient).toHaveBeenCalledWith({ page_size: 200 })
  })

  it('领料抽屉：点击领料打开表单，空备件选择提交被校验拦下', async () => {
    const { MaterialConsumeDrawer } = await import('./MaterialConsumeDrawer')
    const container = document.createElement('div')
    document.body.appendChild(container)
    const localRoot = createRoot(container)
    act(() => {
      localRoot.render(
        <AntApp>
          <MaterialConsumeDrawer
            workOrderId="wo-1"
            spareParts={[]}
            onRefresh={vi.fn()}
          />
        </AntApp>,
      )
    })

    const consumeBtn = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('领料'))
    expect(consumeBtn).toBeTruthy()
    await act(async () => { consumeBtn!.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // 抽屉打开：出现表单与确认按钮
    const text = document.body.textContent || ''
    expect(text).toContain('工单领料')
    const submitBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent === '确认领料')
    expect(submitBtn).toBeTruthy()

    // 未选择备件：表单校验失败，不触发起始化提交（无备件可选）
    await act(async () => { submitBtn!.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
    expect(document.body.textContent || '').toContain('工单领料')

    act(() => localRoot.unmount())
    container.remove()
  })

  it('领料成功：提交扣库存请求并刷新领料记录与备件下拉', async () => {
    actions.consumeMaterials.mockResolvedValue({ code: 200, data: null })
    renderDrawer()
    openWith(baseWorkOrder)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })

    // 打开领料抽屉
    const consumeBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('领料')) as HTMLElement
    expect(consumeBtn).toBeTruthy()
    await act(async () => { consumeBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 120)) })

    // antd v6：对 Select 根元素派发 mousedown 打开选择面后点选备件
    const selectTrigger = document.querySelector('.ant-select') as HTMLElement
    expect(selectTrigger).toBeTruthy()
    await act(async () => {
      selectTrigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const dropdown = document.body.querySelector(
      '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
    ) as HTMLElement
    expect(dropdown).toBeTruthy()
    const option = Array.from(
      dropdown.querySelectorAll('.ant-select-item-option'),
    ).find((o) => o.textContent?.includes('BJ-001')) as HTMLElement
    expect(option).toBeTruthy()
    await act(async () => {
      option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })

    // 提交：走领料接口
    const submitBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent === '确认领料') as HTMLElement
    await act(async () => { submitBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 120)) })
    expect(actions.consumeMaterials).toHaveBeenCalledWith('wo-1', {
      items: [{ spare_part_id: 'sp-1', quantity: 1 }],
    })

    // 成功回调：备件下拉重取 + 领料记录表重建（再次拉取记录）
    expect(api.fetchSparePartsClient.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(api.fetchWorkOrderMaterialsClient.mock.calls.length).toBeGreaterThanOrEqual(2)
  })
})
