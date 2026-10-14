/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearProductionAuthForTest, setProductionAdminForTest } from '@/test/production-auth'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
const chart = vi.hoisted(() => ({ option: null as import('echarts-for-react').EChartsReactProps['option'] | null }))
vi.mock('echarts-for-react', () => ({ default: ({ option }: import('echarts-for-react').EChartsReactProps) => {
  chart.option = option
  return <div data-testid="chart" />
} }))
vi.mock('@/components/production/MCSheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/MCTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import BlendingPage from './page'

const RECORD = {
  id: 'bl-1',
  created_at: new Date().toISOString(),
  batch_no: 'MC-BL-1',
  total_weight: 100,
  pack_spec: '25kg/桶',
  total_impurity: 0.4,
  content: 99.2,
  rrt_053: 0.02,
  rrt_201: 0.03,
  inputs: [
    {
      id: 'in-1',
      input_batch_no: 'MC-F2-1',
      input_weight: 50,
      rrt_053: 0.02,
      content: 99.2,
    },
  ],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/blending-records/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('BlendingPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    setProductionAdminForTest()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    clearProductionAuthForTest()
  })

  it('renders the blending ledger with impurity columns', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<BlendingPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('混粉杂质计算')
    expect(text).toContain('MC-BL-1')
    expect(text).toContain('MC-F2-1')
    expect(text).toContain('新建混粉批次')
    expect(text).toContain('杂质标准')
  })

  it('uses backend impurity upper limits and content lower limits for chart warnings', async () => {
    const bad = { ...RECORD, id: 'bad', batch_no: 'MC-BL-BAD', total_impurity: 0.8, content: 98.5, rrt_053: 0.06, rrt_201: 0.09 }
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, data: [RECORD, bad] }))))
    act(() => root.render(<BlendingPage />))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })
    expect(chart.option.series[0].markPoint.data.map((point: { name: string }) => point.name)).toEqual(['MC-BL-BAD'])
    const selectMetric = async (label: string) => {
      const selected = container.querySelector<HTMLInputElement>('[aria-label="混粉杂质计算仪表盘趋势指标"]')
      await act(async () => { selected?.focus(); selected?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, bubbles: true })) })
      const option = [...document.querySelectorAll<HTMLElement>('.ant-select-item-option')].find((item) => item.textContent === label)
      expect(option).toBeDefined()
      await act(async () => option?.click())
      expect(chart.option.series[0].markPoint.data.map((point: { name: string }) => point.name)).toEqual(['MC-BL-BAD'])
    }
    await selectMetric('含量趋势')
    await selectMetric('RRT=0.53')
    await selectMetric('RRT=2.01')
  })})
