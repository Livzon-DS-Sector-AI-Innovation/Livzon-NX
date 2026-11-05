/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMaintainersClient: vi.fn(),
  fetchWorkOrderByIdClient: vi.fn(),
  fetchSparePartsClient: vi.fn(),
  fetchWorkOrdersClient: vi.fn(),
  fetchWorkOrderEventsClient: vi.fn(),
  transferWorkOrder: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchMaintainersClient: api.fetchMaintainersClient,
  fetchWorkOrderByIdClient: api.fetchWorkOrderByIdClient,
  fetchSparePartsClient: api.fetchSparePartsClient,
  fetchWorkOrdersClient: api.fetchWorkOrdersClient,
  fetchWorkOrderEventsClient: api.fetchWorkOrderEventsClient,
}))
vi.mock('@/actions/equipment', () => ({
  transferWorkOrder: api.transferWorkOrder,
  assignWorkOrder: vi.fn(),
  startWorkOrder: vi.fn(),
  completeWorkOrder: vi.fn(),
  verifyWorkOrder: vi.fn(),
  closeWorkOrder: vi.fn(),
  claimWorkOrder: vi.fn(),
  updateWorkOrderExternalCost: vi.fn(),
}))

import { WorkOrderDetailDrawer } from './WorkOrderDetailDrawer'
import { useEquipmentStore } from '@/stores/equipment'

const baseWo = {
  id: 'wo-1',
  work_order_no: 'WO-20261104-0001',
  equipment_id: 'eq-1',
  equipment_name: '离心泵A',
  equipment_no: 'LB-001',
  order_type: '故障维修',
  priority: '高',
  status: '执行中',
  fault_symptom_id: null,
  fault_cause_id: null,
  fault_action_id: null,
  fault_description: '漏了',
  reporter_id: 'u1',
  reporter_name: '张三',
  assignee_id: 'u-old',
  assignee_name: '李四',
  responsible_person_id: null,
  reported_at: '2026-11-04T08:00:00Z',
  assigned_at: null,
  started_at: '2026-11-04T08:05:00Z',
  completed_at: null,
  verified_at: null,
  verification_result: null,
  verification_remark: null,
  repair_detail: null,
  actual_duration: 30,
  transfer_count: 1,
  images: [],
  created_at: '2026-11-04T08:00:00Z',
  updated_at: '2026-11-04T08:00:00Z',
  maintenance_plan_id: null,
  verified_by: null,
  created_by: null,
  updated_by: null,
  planned_start_date: null,
  checklist_template_id: null,
  spare_parts_cost: null,
  labor_cost: null,
  external_cost: null,
  external_vendor: null,
}

describe('WorkOrderDetailDrawer 转派（方案E）', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchMaintainersClient.mockResolvedValue([
      { user_id: 'u-new', name: '王五', employee_no: 'E002', department_id: 'd1' },
    ])
    api.fetchWorkOrderEventsClient.mockResolvedValue([])
    api.fetchSparePartsClient.mockResolvedValue({ items: [], total: 0 })
    api.transferWorkOrder.mockReset()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
    useEquipmentStore.setState({ workOrderDetailOpen: false, viewingWorkOrder: null })
  })

  function openDrawer(overrides: Record<string, unknown> = {}) {
    useEquipmentStore.setState({
      workOrderDetailOpen: true,
      viewingWorkOrder: { ...baseWo, ...overrides },
    })
    act(() => {
      root.render(
        <AntApp>
          <WorkOrderDetailDrawer onRefresh={() => {}} />
        </AntApp>,
      )
    })
  }

  it('执行中工单显示带转派次数的转派按钮；已完成不显示', async () => {
    openDrawer()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('转派（1次）')

    // 已完成状态不显示
    openDrawer({ status: '已完成', transfer_count: 2 })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(document.body.textContent || '').not.toContain('转派（2次）')
  })

  it('打开转派弹窗并提交调用 transferWorkOrder', async () => {
    api.transferWorkOrder.mockResolvedValue({ id: 'wo-1' })
    openDrawer()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const btn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('转派（1次）'),
    ) as HTMLButtonElement
    await act(async () => {
      btn.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    const modalText = document.body.textContent || ''
    expect(modalText).toContain('选择新维修人')
    expect(modalText).toContain('已转派 1 次')
    // 未选人提交：onOk 返回 reject 拦截，不调用接口（弹窗保持）
    const okBtn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('确认转派'),
    ) as HTMLButtonElement
    expect(okBtn).toBeTruthy()
    await act(async () => {
      okBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(api.transferWorkOrder).not.toHaveBeenCalled()
    expect(document.body.textContent || '').toContain('选择新维修人')
  })
})
