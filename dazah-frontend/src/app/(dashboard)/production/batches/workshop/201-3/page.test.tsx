/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
const chart = vi.hoisted(() => ({ option: null as import('echarts-for-react').EChartsReactProps['option'] | null }))
vi.mock('echarts-for-react', () => ({
  default: ({ option }: import('echarts-for-react').EChartsReactProps) => { chart.option = option; return <div data-testid="echarts" /> },
}))

import Workshop2013Page from './page'

const DASHBOARD = {
  monthly_output_kg: 1000,
  monthly_batches: 20,
  avg_yield: 88,
  pass_rate: 90,
  ba_stock_kg: 500,
  ba_batches: 3,
  ba_monthly_consume: 100,
  stages: { crude: 5, extraction: 3 },
  status_distribution: [],
  monthly_trend: [{ month: 1, output_kg: 100 }, { month: 2, output_kg: 1250 }],
  rrt_pass_rates: [],
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('Workshop2013Page', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders dashboard KPI cards and trend', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: DASHBOARD }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><Workshop2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('多拉菌素')
    expect(text).toContain('本月产量')
    expect(chart.option.yAxis.name).toBe('kg')
    expect(chart.option.yAxis.axisLabel.formatter(100)).toBe('100')
    expect(chart.option.yAxis.axisLabel.formatter(1250)).toBe('1,250')
    expect(chart.option.tooltip.formatter([{ name: '1月', value: 100 }])).toBe('1月<br/>产量: 100 kg')
  })

  it('renders empty when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 500, message: 'error', data: null }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><Workshop2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actionsCall(container)).toContain('多拉菌素')
  })
})

function actionsCall(container: HTMLElement): string {
  return container.textContent || ''
}