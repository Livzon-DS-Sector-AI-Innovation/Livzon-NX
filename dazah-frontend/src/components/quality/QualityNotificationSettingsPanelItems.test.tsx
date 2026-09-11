/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const qualityActions = vi.hoisted(() => ({
  fetchQualityNotificationSettings: vi.fn(),
  updateQualityNotificationSetting: vi.fn(),
}))
const inspectionActions = vi.hoisted(() => ({
  pushItemsLowStockTest: vi.fn(),
}))
const apiClient = vi.hoisted(() => ({
  searchChangeActionPlanPersons: vi.fn(),
  fetchQaPersonOptions: vi.fn(),
}))

vi.mock('@/actions/quality', () => qualityActions)
vi.mock('@/actions/quality-inspection', () => inspectionActions)
vi.mock('@/lib/api/client/quality', () => apiClient)

import { QualityNotificationSettingsPanel } from './QualityNotificationSettingsPanel'

const SETTINGS = [
  {
    notification_type: 'items_stock_alert',
    notification_label: '物品库存不足预警推送',
    is_enabled: false,
    lead_days: 3,
    repeat_interval_days: 1,
    send_time: '09:00',
    fallback_recipients: [],
    inspection_lines: [],
    first_recipients: [],
    escalation_hours: null,
    stock_recipients: [{ open_id: 'ou_z', name: '张三' }],
    stock_header_template: '库存告警 {count}',
    stock_footer_template: '共 {count} 种',
    stock_warning_source: 'local_threshold',
  },
]

let root: Root
beforeEach(() => {
  qualityActions.fetchQualityNotificationSettings.mockResolvedValue(SETTINGS)
  qualityActions.updateQualityNotificationSetting.mockResolvedValue(SETTINGS[0])
  inspectionActions.pushItemsLowStockTest.mockResolvedValue({
    status: 'sent', sent: 1, skipped: 0, failed: 0, item_count: 1,
  })
  apiClient.searchChangeActionPlanPersons.mockResolvedValue([])
  apiClient.fetchQaPersonOptions.mockResolvedValue([])
})

afterEach(() => {
  root?.unmount()
  vi.restoreAllMocks()
})

async function flush() {
  for (let i = 0; i < 6; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  }
}

describe('QualityNotificationSettingsPanel 物品库存不足预警卡', () => {
  it('存在 items_stock_alert 设置时渲染卡片并回填判定口径', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    root = createRoot(container)
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <App>
            <QualityNotificationSettingsPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await flush()
    expect(container.textContent).toContain('物品库存不足预警推送')
    expect(container.textContent).toContain('当前库存 ≤ 警戒库存')
    expect(container.textContent).toContain('发送测试推送')
  })

  it('测试推送：unmapped 提示未配置接收人，no_data 提示无物料', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    root = createRoot(container)
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <App>
            <QualityNotificationSettingsPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await flush()
    const testButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => (btn.textContent || '').includes('测试推送'),
    ) as HTMLButtonElement | undefined

    inspectionActions.pushItemsLowStockTest.mockResolvedValue({
      status: 'unmapped', sent: 0, skipped: 0, failed: 0, item_count: 0, message: '未配置有效接收人',
    })
    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(document.body.textContent).toContain('未配置有效接收人')

    inspectionActions.pushItemsLowStockTest.mockResolvedValue({
      status: 'no_data', sent: 0, skipped: 0, failed: 0, item_count: 0, message: '',
    })
    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(document.body.textContent).toContain('当前没有库存不足的物料，未发送测试')
  })
})
