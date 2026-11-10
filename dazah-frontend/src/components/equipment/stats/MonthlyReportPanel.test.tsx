/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMonthlyReportsClient: vi.fn(),
  generateMonthlyReport: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchMonthlyReportsClient: api.fetchMonthlyReportsClient,
}))
vi.mock('@/actions/equipment', () => ({
  generateMonthlyReport: api.generateMonthlyReport,
}))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import { MonthlyReportPanel } from './MonthlyReportPanel'

const reports = [
  {
    id: 'r-1',
    report_month: '2026-10',
    metrics: { total_orders: 12 },
    content_md: '## 总体情况\n\n本月工单 12 单，运行平稳。',
    generated_at: '2026-11-01T08:00:00Z',
  },
]

describe('MonthlyReportPanel', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchMonthlyReportsClient.mockResolvedValue(reports)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('renders report list with month tag', async () => {
    act(() => {
      root.render(
        <AntApp>
          <MonthlyReportPanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('月度健康报告')
    expect(text).toContain('2026-10')
    expect(text).toContain('每月 1 日 08:00 自动生成')
  })

  it('opens markdown view modal on click', async () => {
    act(() => {
      root.render(
        <AntApp>
          <MonthlyReportPanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const viewBtn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('查看报告'),
    ) as HTMLButtonElement
    expect(viewBtn).toBeTruthy()
    await act(async () => {
      viewBtn.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    // Markdown 渲染为标题元素
    const heading = document.querySelector('.monthly-report-md h2')
    expect(heading?.textContent).toContain('总体情况')
    expect(document.body.textContent).toContain('本月工单 12 单')
  })

  it('shows empty state when no reports', async () => {
    api.fetchMonthlyReportsClient.mockResolvedValue([])
    act(() => {
      root.render(
        <AntApp>
          <MonthlyReportPanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(document.body.textContent).toContain('暂无报告')
  })

  it('点击生成调用 action 并刷新列表', async () => {
    api.generateMonthlyReport.mockResolvedValue({ id: 'r-new' })
    api.fetchMonthlyReportsClient.mockResolvedValue([
      { id: 'r-new', report_month: '2026-10', metrics: null, content_md: '# x', generated_at: '2026-11-05T08:00:00Z' },
    ])
    act(() => {
      root.render(
        <AntApp>
          <MonthlyReportPanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const genBtn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('生成报告'),
    ) as HTMLButtonElement
    expect(genBtn).toBeTruthy()
    await act(async () => {
      genBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(api.generateMonthlyReport).toHaveBeenCalledWith('2026-10')
    expect(api.fetchMonthlyReportsClient.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('生成失败提示错误', async () => {
    api.generateMonthlyReport.mockRejectedValue(new Error('LLM 未配置'))
    act(() => {
      root.render(
        <AntApp>
          <MonthlyReportPanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const genBtn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('生成报告'),
    ) as HTMLButtonElement
    await act(async () => {
      genBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(document.body.textContent || '').toContain('LLM 未配置')
  })
})
