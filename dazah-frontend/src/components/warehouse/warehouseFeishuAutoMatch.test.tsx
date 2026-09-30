/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WarehouseFeishuConfigPage } from './WarehouseFeishuConfigPage'
import type { WarehousePageFeishuConfig } from '@/types/warehouse'

const permissions = vi.hoisted(() => ({ canSync: true }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => permissions }))

const updateAction = vi.hoisted(() => vi.fn())
vi.mock('@/actions/warehouse', () => ({
  updateWarehousePageFeishuConfigAction: updateAction,
}))

const apiMocks = vi.hoisted(() => ({
  configs: vi.fn(),
  tables: vi.fn(),
}))
vi.mock('@/lib/api/client/warehouse', () => ({
  fetchWarehousePageFeishuConfigs: apiMocks.configs,
  fetchWarehousePageFormLinks: vi.fn(async () => ({
    inbound_form_url: null,
    outbound_form_url: null,
  })),
  fetchWarehouseHomeQuickFormLinks: vi.fn(async () => ({})),
  fetchWarehousePageFeishuConfigTables: apiMocks.tables,
}))

const configs: WarehousePageFeishuConfig[] = [
  {
    page_key: 'acceptance-page',
    app_token: 'AppTokenAA1111',
    table_id: 'tbl-old-1',
    table_name: '验收登记表',
  },
  {
    page_key: 'material-ledger',
    app_token: 'AppTokenAA1111',
    table_id: 'tbl-old-2',
    table_name: '物料台账',
  },
]

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  apiMocks.configs.mockReset().mockResolvedValue(configs)
  apiMocks.tables.mockReset().mockResolvedValue({
    app_token: 'ResolvedAppToken',
    tables: [
      { table_id: 'tbl-new-accept', table_name: '验收登记表' },
      { table_id: 'tbl-new-material', table_name: '物料台账' },
      { table_id: 'tbl-extra', table_name: '其他子表' },
    ],
  })
  updateAction.mockReset().mockResolvedValue({})
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  document.querySelectorAll('.ant-modal-root, .ant-message').forEach((el) => el.remove())
})

function renderPage(): void {
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <App>
          <WarehouseFeishuConfigPage initialConfigs={configs} />
        </App>
      </QueryClientProvider>,
    )
  })
}

async function openGroupAndFillUrl(): Promise<void> {
  renderPage()
  const header = container.querySelector<HTMLElement>('.ant-collapse-header')
  expect(header).not.toBeNull()
  await act(async () => {
    header!.click()
  })
  const input = Array.from(container.querySelectorAll('input')).find((el) =>
    el.placeholder?.includes('粘贴多维表格链接'),
  ) as HTMLInputElement
  expect(input).toBeTruthy()
  // React 受控组件需用原生 setter 触发 onChange
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )!.set!
  await act(async () => {
    setter.call(input, 'https://example.feishu.cn/wiki/WikiNodeToken?table=tbl-1')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

it('按名称匹配：wiki 链接换取 app_token 后按页面名称分配子表并更新', async () => {
  await openGroupAndFillUrl()

  const matchButton = Array.from(container.querySelectorAll('button')).find(
    (b) => b.textContent?.includes('按名称匹配'),
  ) as HTMLButtonElement
  expect(matchButton?.disabled).toBe(false)
  await act(async () => {
    matchButton.click()
  })

  // 确认弹窗列出匹配结果
  await vi.waitFor(() => {
    expect(document.querySelector('.ant-modal')?.textContent).toContain(
      '2 个页面分别绑定',
    )
  })
  expect(apiMocks.tables).toHaveBeenCalledWith('https://example.feishu.cn/wiki/WikiNodeToken?table=tbl-1')

  await act(async () => {
    ;(
      Array.from(document.querySelectorAll('.ant-modal .ant-btn-primary')).find(
        (b) => b.textContent?.includes('确认更新'),
      ) as HTMLElement
    )?.click()
  })

  await vi.waitFor(() => {
    expect(updateAction).toHaveBeenCalledTimes(2)
  })
  const calls = updateAction.mock.calls.map((c) => [c[0], c[1].app_token, c[1].table_id])
  expect(calls).toContainEqual(['acceptance-page', 'ResolvedAppToken', 'tbl-new-accept'])
  expect(calls).toContainEqual(['material-ledger', 'ResolvedAppToken', 'tbl-new-material'])
})

it('按名称匹配：读取子表失败时提示错误且不更新任何配置', async () => {
  apiMocks.tables.mockRejectedValue(new Error('wiki 链接无法解析出 app_token'))
  await openGroupAndFillUrl()

  const matchButton = Array.from(container.querySelectorAll('button')).find(
    (b) => b.textContent?.includes('按名称匹配'),
  ) as HTMLButtonElement
  await act(async () => {
    matchButton.click()
  })

  await vi.waitFor(() => {
    expect(document.body.textContent).toContain('wiki 链接无法解析出 app_token')
  })
  expect(updateAction).not.toHaveBeenCalled()
})
