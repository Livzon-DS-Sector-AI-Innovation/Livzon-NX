/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMaintenancePlansClient: vi.fn(),
  fetchWorkOrdersClient: vi.fn(),
  fetchInspectionFeishuRecords: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchMaintenancePlansClient: api.fetchMaintenancePlansClient,
  fetchWorkOrdersClient: api.fetchWorkOrdersClient,
}))
vi.mock('@/lib/api/inspection-feishu', () => ({
  fetchInspectionFeishuRecords: api.fetchInspectionFeishuRecords,
}))

import { EquipmentDetailDrawer } from './EquipmentDetailDrawer'
import type { Equipment } from '@/types/equipment'

const equipment = {
  id: 'eq-1',
  equipment_no: 'XT1-1-1-129',
  name: '方锥混合机',
  category_ids: ['cat-1'],
  location_id: 'loc-1',
  status: '在用',
  importance: '高',
  model: 'PJ-500L',
  specification: null,
  manufacturer: '温州设备厂',
  supplier: null,
  production_date: null,
  factory_no: 'CC-2024-118',
  arrival_date: '2024-06-15',
  commissioning_date: null,
  description: null,
  data_issue_note: '【出厂日期】为空',
  technical_params: { 功率: '3kW', 容积: '500L' },
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
  created_by: null,
  updated_by: null,
  department_id: null,
  department_name: null,
  responsible_person_id: null,
  responsible_person_name: null,
} as unknown as Equipment

const historyRecord = {
  id: 'rec-1',
  source: 'history',
  record_date: '2026-10-09',
  equipment_name: '方锥混合机',
  equipment_no: 'XT1-1-1-129',
  am_clean: '√',
  am_lubrication: '√',
  pm_clean: '×',
  anomaly_note: '下午清洁异常',
  has_abnormal: true,
} as never

function renderDrawer(root: Root, onClose = vi.fn()) {
  act(() => {
    root.render(
      <AntApp>
        <EquipmentDetailDrawer
          open
          equipment={equipment}
          categoryName="反应设备"
          locationName="201二车间"
          onClose={onClose}
        />
      </AntApp>,
    )
  })
}

describe('EquipmentDetailDrawer', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchMaintenancePlansClient.mockResolvedValue({ items: [], total: 0 })
    api.fetchWorkOrdersClient.mockResolvedValue({ items: [], total: 0 })
    api.fetchInspectionFeishuRecords.mockResolvedValue({
      items: [historyRecord],
      total: 1,
      page: 1,
      page_size: 50,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('shows ledger extension fields including tech params and data issues', async () => {
    renderDrawer(root)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('CC-2024-118')
    expect(text).toContain('2024-06-15')
    expect(text).toContain('功率：3kW；容积：500L')
    expect(text).toContain('数据待修正')
    expect(text).toContain('【出厂日期】为空')
  })

  it('loads inspection mirror records by equipment keyword into the history tab', async () => {
    renderDrawer(root)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(api.fetchInspectionFeishuRecords).toHaveBeenCalledWith({
      keyword: 'XT1-1-1-129',
      page: 1,
      page_size: 50,
    })

    const historyTab = [...document.body.querySelectorAll('.ant-tabs-tab')].find(
      (tab) => tab.textContent?.includes('巡检记录'),
    ) as HTMLElement | undefined
    expect(historyTab).toBeTruthy()
    await act(async () => {
      historyTab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('2026-10-09')
    expect(text).toContain('√2')
    expect(text).toContain('×1')
    expect(text).toContain('历史记录')
    expect(text).toContain('异常')
    expect(text).toContain('下午清洁异常')
  })

  it('reports inspection load failures without breaking the drawer', async () => {
    api.fetchInspectionFeishuRecords.mockRejectedValue(new Error('镜像未配置'))
    renderDrawer(root)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(document.body.textContent).toContain('加载巡检记录失败')
  })
})
