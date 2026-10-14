/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import { AntdProvider } from '../AntdProvider'
import { EnergyOverview } from './EnergyOverview'

const charts = vi.hoisted(() => ({ props: [] as EChartsReactProps[] }))
vi.mock('@/lib/useAppearance', () => ({ useAppearance: () => ({ resolved: 'dark' }) }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => '/energy',
  useSearchParams: () => new URLSearchParams('source_scope=energy_summary'),
}))
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: {
  metrics: [{ metric_key: '电量', energy_type: '电', unit: 'kWh', total_value: 30, record_count: 2 }],
  latest_metrics: [],
  trend: [{ metric_key: '电量', energy_type: '电', unit: 'kWh', date: '2026-10-01', value: 30 }],
  distribution: [{ metric_key: '电量', energy_type: '电', unit: 'kWh', key: '一车间', value: 30 }],
}, isLoading: false, error: null }) }))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => {
  charts.props.push(props)
  return <div data-chart-theme={props.theme} />
} }))
it('renders the energy trend and ranking in dark mode without losing their values', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<AntdProvider><EnergyOverview /></AntdProvider>))
    expect(host.querySelectorAll('[data-chart-theme="dark"]').length).toBe(2)
    expect(charts.props[0].option.series[0].data).toEqual([30])
    expect(charts.props[1].option.series[0].data).toEqual([30])
    for (const chart of charts.props) {
      expect(chart.option.tooltip.backgroundColor).toBe('#2b2b30')
      expect(chart.option.textStyle.color).toBe('#eeedf1')
    }
    expect(host.textContent).toContain('电量')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
