/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

// 将 echarts 渲染为占位 div 以便在 DOM 中查询
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

// 传入 scopeKey/lineConfigs 时显示警戒线入口；未传时不显示（线回落图表 markLine）。

const fetchMock = vi.fn()

function renderDashboard(withScope: boolean) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  const props = {
    title: '测试仪表盘',
    data: [
      { batch_no: 'B-1', produce_date: '2026-11-01', yield_rate: 100.2 },
      { batch_no: 'B-2', produce_date: '2026-11-02', yield_rate: 97.1 },
    ],
    dateField: 'produce_date',
    cards: [],
    charts: [
      {
        key: 'yield', label: '收率趋势', title: '单批收率趋势', unit: '%',
        color: '#1890ff', field: 'yield_rate', markLine: 92,
      },
    ],
    ...(withScope
      ? {
          scopeKey: 'workshop-201-2/crude-extraction',
          lineConfigs: [{ key: 'yield', label: '收率警戒线', unit: '%' }],
        }
      : {}),
  }
  act(() => {
    root.render(
      <App>
        <Dashboard {...props} />
      </App>,
    )
  })
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    fetchMock.mockResolvedValue({
      json: async () => ({ code: 200, data: { yield: 95 } }),
    }),
  )
  container = document.createElement('div')
  document.body.append(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('Dashboard 警戒线入口', () => {
  beforeEach(() => { fetchMock.mockClear() })

  it('传入 scopeKey 时渲染警戒线按钮并拉取配置', async () => {
    renderDashboard(true)
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    const btn = [...document.querySelectorAll('button')].find(
      (b) => (b.textContent || '').trim() === '警戒线',
    )
    expect(btn).toBeTruthy()
    expect(fetchMock.mock.calls[0][0]).toContain('scope_key=')
  })

  it('未传 scopeKey 时不渲染入口也不发请求', async () => {
    renderDashboard(false)
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    const btn = [...document.querySelectorAll('button')].find(
      (b) => (b.textContent || '').trim() === '警戒线',
    )
    expect(btn).toBeUndefined()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
