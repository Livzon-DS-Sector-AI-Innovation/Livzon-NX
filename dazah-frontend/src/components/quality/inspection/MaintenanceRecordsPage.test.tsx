/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import dayjs from 'dayjs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const tableState = vi.hoisted(() => ({ latest: {} as Record<string, unknown> }))

vi.mock('@/components/quality/inspection', () => ({
  InspectionFeishuTable: (props: Record<string, unknown>) => {
    tableState.latest = props
    // 渲染工具栏（月份选择器 + 导出按钮），供交互断言
    return <div data-testid="toolbar">{props.toolbarContent as never}</div>
  },
}))

import { MaintenanceRecordsPage } from './MaintenanceRecordsPage'

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  window.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  window.URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

function renderPage() {
  const fetchMock = vi.fn(async () =>
    new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: { 'content-type': 'application/octet-stream' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <MaintenanceRecordsPage />
        </App>
      </QueryClientProvider>,
    )
  })
  return fetchMock
}

describe('MaintenanceRecordsPage 月份过滤与导出', () => {
  it('默认选中当前月并作为 monthFilter 传给列表', () => {
    renderPage()
    expect(tableState.latest.title).toBe('设备维护保养记录')
    expect(tableState.latest.monthFilter).toBe(dayjs().format('YYYY-MM'))
  })

  it('导出汇总表按所选月份请求导出接口', async () => {
    const fetchMock = renderPage()
    const button = Array.from(document.querySelectorAll('button')).find(
      (node) => node.textContent === '导出汇总表',
    )
    expect(button).toBeTruthy()
    await act(async () => {
      button!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const exportUrl = String(
      (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] ?? '',
    )
    expect(exportUrl).toContain('/instruments/maintenance/export?')
    expect(new URLSearchParams(exportUrl.split('?')[1]).get('month')).toBe(
      dayjs().format('YYYY-MM'),
    )
  })
})
