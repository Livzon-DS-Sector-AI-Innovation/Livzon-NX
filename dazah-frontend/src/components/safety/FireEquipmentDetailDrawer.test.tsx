/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getFireEquipmentDetail: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getFireEquipmentDetail: mocks.getFireEquipmentDetail,
}))

import FireEquipmentDetailDrawer from './FireEquipmentDetailDrawer'

const DETAIL = {
  equipment: {
    id: 'eq-1',
    equipment_no: 'MQC-001',
    equipment_type: 'extinguisher',
    department: '103三车间',
    location: '罐区西侧',
    expiry_date: '2027-06-30',
    days_left: 252,
    expiry_status: 'ok',
    fields: { 型号: 'MFZ/ABC4', 压力状态: '正常' },
    month_status: 'inspected',
  },
  checklist: [],
  recent_inspections: [
    {
      id: 'r1',
      inspected_at: '2026-10-20T09:30:00',
      result: 'pass',
      inspector_name: '测试点检员',
      source: 'scan',
      failed_items: [],
      abnormal_action: null,
    },
    {
      id: 'r2',
      inspected_at: '2026-09-18T14:00:00',
      result: 'fail',
      inspector_name: '张三',
      source: 'web',
      failed_items: [{ key: 'pressure', label: '压力表指针不在绿区' }],
      abnormal_action: '已报修更换',
    },
  ],
}

describe('FireEquipmentDetailDrawer', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    mocks.getFireEquipmentDetail.mockResolvedValue({
      code: 200,
      message: 'success',
      data: DETAIL,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  function renderDrawer(equipmentId: string | null) {
    act(() => {
      root.render(
        <FireEquipmentDetailDrawer
          open
          pageKey="k"
          equipmentId={equipmentId}
          onClose={() => {}}
        />,
      )
    })
  }

  it('挂载后拉取详情并渲染器材信息与点检记录', async () => {
    renderDrawer('eq-1')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    expect(mocks.getFireEquipmentDetail).toHaveBeenCalledWith({
      pageKey: 'k',
      equipmentId: 'eq-1',
    })
    const text = document.body.textContent ?? ''
    expect(text).toContain('MQC-001')
    expect(text).toContain('103三车间')
    expect(text).toContain('2026-10-20 09:30')
    expect(text).toContain('合格')
    expect(text).toContain('不合格')
    expect(text).toContain('压力表指针不在绿区')
    expect(text).toContain('已报修更换')
  })

  it('详情请求失败时展示错误提示', async () => {
    mocks.getFireEquipmentDetail.mockResolvedValue({
      code: 500,
      message: '读取失败',
      data: null,
    })
    renderDrawer('eq-2')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    expect((document.body.textContent ?? '').includes('读取失败')).toBe(true)
  })

  it('equipmentId 为空时不发起请求', async () => {
    renderDrawer(null)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    expect(mocks.getFireEquipmentDetail).not.toHaveBeenCalled()
  })

  it('Drawer 使用 antd v6 size 属性并应用 520px 宽度', async () => {
    renderDrawer('eq-1')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const wrapper = document.querySelector('.ant-drawer-content-wrapper') as HTMLElement | null
    expect(wrapper).toBeTruthy()
    expect(wrapper!.style.width).toBe('520px')
  })
})
