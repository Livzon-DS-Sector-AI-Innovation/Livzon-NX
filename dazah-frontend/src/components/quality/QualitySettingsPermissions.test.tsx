/* @vitest-environment happy-dom */
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { QualityFeishuSettingsPage } from './QualityFeishuSettingsPage'

const flags = vi.hoisted(() => ({ canSync: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/actions/quality', () => ({
  pullQualityRecordsFromFeishu: vi.fn(), testQualityFeishuAppSettings: vi.fn(),
  testQualityFeishuEntitySetting: vi.fn(), updateQualityFeishuAppSettings: vi.fn(),
  updateQualityFeishuEntitySetting: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchQualityFeishuAppSettings: vi.fn(), fetchQualityFeishuEntityFieldMappingBundle: vi.fn(),
  fetchQualityFeishuEntitySettings: vi.fn(), fetchQualityFeishuEntityTables: vi.fn(),
  formatQualityFeishuTestSummary: vi.fn(), formatQualitySyncSummary: vi.fn(),
}))

describe('quality settings action authorization', () => {
  it.each([false, true])('requires sync permission for configuration operations: %s', canSync => {
    flags.canSync = canSync
    const client = new QueryClient()
    const container = document.createElement('div')
    container.innerHTML = renderToStaticMarkup(
      <QueryClientProvider client={client}><QualityFeishuSettingsPage /></QueryClientProvider>,
    )
    const buttons = Array.from(container.querySelectorAll('button'))
    for (const label of ['测试连接', '保存配置', '手动回拉已启用数据']) {
      const button = buttons.find(item => item.textContent?.replace(/\s/g, '') === label)
      expect(button).toBeDefined()
      expect(button!.disabled).toBe(!canSync)
    }
    client.clear()
  })
})
