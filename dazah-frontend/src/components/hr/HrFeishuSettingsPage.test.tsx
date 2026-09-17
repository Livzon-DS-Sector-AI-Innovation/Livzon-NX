/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const hrActions = vi.hoisted(() => ({
  updateHrFeishuAppSettings: vi.fn(),
  testHrFeishuAppSettings: vi.fn(),
  updateHrFeishuEntitySetting: vi.fn(),
  testHrFeishuEntitySetting: vi.fn(),
  updateEmailConfig: vi.fn(),
  testEmailConfig: vi.fn(),
  uploadOfferTemplateAction: vi.fn(),
}))

const hrApi = vi.hoisted(() => ({
  fetchAllHrFeishuAppSettings: vi.fn(),
  fetchHrFeishuAppSettings: vi.fn(),
  fetchEmailConfig: vi.fn(),
  fetchHrFeishuEntitySettings: vi.fn(),
  fetchHrFeishuEntityFieldMappingBundle: vi.fn(),
  fetchHrFeishuEntityTables: vi.fn(),
  formatHrFeishuTestSummary: vi.fn((r: { success?: boolean; message?: string }) =>
    r?.success ? '连接成功' : '连接失败',
  ),
}))

const feishuUrl = vi.hoisted(() => ({
  parseFeishuBitableUrl: vi.fn(() => ({ app_token: 'app-token', table_id: 'tbl-1' })),
}))

vi.mock('@/actions/hr', () => hrActions)
vi.mock('@/lib/api/hr', () => hrApi)
vi.mock('@/lib/feishu-url', () => feishuUrl)

import { HrFeishuSettingsPage } from './HrFeishuSettingsPage'

const BITABLE_APP = {
  purpose: 'bitable',
  app_id: 'cli_bitable',
  app_secret: '',
  is_enabled: true,
  app_name: '多维表格应用',
  last_test_status: null,
  last_test_error: null,
  last_tested_at: null,
}

const CONTACT_APP = {
  ...BITABLE_APP,
  purpose: 'contact',
  app_id: 'cli_contact',
  app_name: '通讯录应用',
}

const ENTITY_SETTINGS = [
  {
    id: 'es-1',
    entity_code: 'hr_feishu_members',
    entity_name: '飞书成员',
    entity_group: '通讯录',
    app_token: 'app-token',
    base_table_name: '成员表',
    base_table_id: 'tbl-1',
    is_enabled: true,
    enable_push_to_feishu: true,
    enable_pull_from_feishu: true,
    field_mappings: {},
    sort_order: 1,
    last_sync_status: null,
    last_sync_error: null,
    last_synced_at: null,
  },
]

let root: Root
beforeEach(() => {
  hrActions.updateHrFeishuAppSettings.mockResolvedValue({ purpose: 'bitable' })
  hrActions.testHrFeishuAppSettings.mockResolvedValue({ success: true, message: 'ok' })
  hrActions.updateHrFeishuEntitySetting.mockResolvedValue({ entity_code: 'hr_feishu_members' })
  hrActions.testHrFeishuEntitySetting.mockResolvedValue({ success: true, message: 'ok' })
  hrActions.updateEmailConfig.mockResolvedValue({})
  hrActions.testEmailConfig.mockResolvedValue({ success: true })
  hrActions.uploadOfferTemplateAction.mockResolvedValue({})
  hrApi.fetchAllHrFeishuAppSettings.mockResolvedValue([BITABLE_APP, CONTACT_APP])
  hrApi.fetchHrFeishuAppSettings.mockResolvedValue(BITABLE_APP)
  hrApi.fetchEmailConfig.mockResolvedValue({ is_enabled: false })
  hrApi.fetchHrFeishuEntitySettings.mockResolvedValue(ENTITY_SETTINGS)
  hrApi.fetchHrFeishuEntityFieldMappingBundle.mockResolvedValue({ items: [], total: 0 })
  hrApi.fetchHrFeishuEntityTables.mockResolvedValue([])
})

afterEach(() => {
  root?.unmount()
  vi.restoreAllMocks()
})

async function flush() {
  for (let i = 0; i < 8; i++) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  }
}

describe('HrFeishuSettingsPage 双应用配置', () => {
  it('渲染两组飞书应用配置并展示应用名称', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    root = createRoot(container)
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <App>
            <HrFeishuSettingsPage />
          </App>
        </QueryClientProvider>,
      )
    })
    await flush()
    expect(hrApi.fetchAllHrFeishuAppSettings).toHaveBeenCalled()
    expect(container.textContent).toContain('通讯录与部门管理')
    expect(container.textContent).toContain('多维表格同步')
  })

  it('展示人事飞书实体配置列表', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    root = createRoot(container)
    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <App>
            <HrFeishuSettingsPage />
          </App>
        </QueryClientProvider>,
      )
    })
    await flush()
    expect(container.textContent).toContain('飞书成员')
  })
})
