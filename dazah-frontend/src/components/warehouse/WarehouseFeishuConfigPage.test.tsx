/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WarehouseFeishuConfigPage } from './WarehouseFeishuConfigPage'

const permissions = vi.hoisted(() => ({ canSync: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => permissions }))
vi.mock('@/actions/warehouse', () => ({ updateWarehousePageFeishuConfigAction: vi.fn() }))
vi.mock('@/lib/api/client/warehouse', () => ({
  fetchWarehousePageFeishuConfigs: vi.fn(async () => []),
  fetchWarehousePageFormLinks: vi.fn(async () => ({
    inbound_form_url: null,
    outbound_form_url: null,
  })),
  fetchWarehouseHomeQuickFormLinks: vi.fn(async () => ({})),
}))

function renderConfigPage(root: Root, initialConfigs: Parameters<typeof WarehouseFeishuConfigPage>[0]['initialConfigs']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  root.render(
    <QueryClientProvider client={client}>
      <App>
        <WarehouseFeishuConfigPage initialConfigs={initialConfigs} />
      </App>
    </QueryClientProvider>
  )
}

describe('warehouse configuration action grants', () => {
  let root: Root
  let container: HTMLDivElement
  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it.each([false, true])('requires sync_config to edit configuration: %s', async (canSync) => {
    permissions.canSync = canSync
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    await act(async () => {
      renderConfigPage(root, [
        {
          page_key: 'acceptance-page', app_token: 'test-base', table_id: 'test-table', table_name: '验收表',
        },
      ])
    })
    const input = container.querySelector<HTMLInputElement>('input')
    expect(input?.disabled).toBe(!canSync)
    const header = container.querySelector<HTMLElement>('.ant-collapse-header')
    expect(header).not.toBeNull()
    await act(async () => { header!.click() })
    const edit = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '编辑')
    expect(edit?.disabled).toBe(!canSync)
  })
})
