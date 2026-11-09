/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  searchKnowledgeCasesClient: vi.fn(),
  fetchAllUsersClient: vi.fn(),
  createWorkOrder: vi.fn(),
  uploadWorkOrderImages: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  searchKnowledgeCasesClient: api.searchKnowledgeCasesClient,
  fetchAllUsersClient: api.fetchAllUsersClient,
}))
vi.mock('@/actions/equipment', () => ({
  createWorkOrder: api.createWorkOrder,
  uploadWorkOrderImages: api.uploadWorkOrderImages,
}))

import { RepairDrawer } from './RepairDrawer'
import { useEquipmentStore } from '@/stores/equipment'

const cases = [
  {
    id: 'case-1',
    equipment_name: '离心泵A',
    equipment_no: 'LB-001',
    symptom_name: '密封泄漏',
    cause_name: '密封圈老化',
    action_name: '更换密封圈',
    fault_description: '转轴处渗漏',
    repair_summary: '停机更换密封圈',
    key_steps: ['断电挂牌', '更换密封圈', '试机验证'],
    use_count: 2,
    score: 100,
  },
]

describe('RepairDrawer 相似案例推荐（方案B）', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.searchKnowledgeCasesClient.mockReset().mockResolvedValue(cases)
    api.fetchAllUsersClient.mockResolvedValue([])
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
    useEquipmentStore.setState({
      repairDrawerOpen: false,
      repairEquipmentId: null,
    })
  })

  function openDrawer() {
    useEquipmentStore.setState({
      repairDrawerOpen: true,
      repairEquipmentId: 'eq-1',
    })
    act(() => {
      root.render(
        <AntApp>
          <RepairDrawer
            equipments={[
              {
                id: 'eq-1',
                equipment_no: 'LB-001',
                name: '离心泵A',
                importance: '高',
                responsible_person_id: 'u-1',
              },
            ]}
            symptoms={[]}
            onRefresh={vi.fn()}
          />
        </AntApp>,
      )
    })
  }

  it('打开抽屉即按设备名检索并渲染推荐面板', async () => {
    openDrawer()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(api.searchKnowledgeCasesClient).toHaveBeenCalledWith(
      expect.objectContaining({ q: '离心泵A', equipment_id: 'eq-1', top: 3 }),
    )
    const text = document.body.textContent || ''
    expect(text).toContain('相似历史案例')
    expect(text).toContain('密封泄漏')
    expect(text).toContain('更换密封圈')
    expect(text).toContain('断电挂牌')
    expect(text).toContain('被参考 2 次')
  })

  it('无案例时静默不渲染面板（不误报错误）', async () => {
    api.searchKnowledgeCasesClient.mockResolvedValue([])
    openDrawer()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = document.body.textContent || ''
    expect(text).not.toContain('相似历史案例')
    expect(text).toContain('报故障维修')
  })

  it('检索失败静默兜底不阻断报修表单', async () => {
    api.searchKnowledgeCasesClient.mockRejectedValue(new Error('network'))
    openDrawer()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(document.body.textContent || '').toContain('报故障维修')
  })
})
