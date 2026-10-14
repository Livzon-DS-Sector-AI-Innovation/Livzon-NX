/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import ThemedEChart from './ThemedEChart'
import { setAppearance } from '@/lib/useAppearance'

const received = vi.hoisted(() => ({ props: null as EChartsReactProps | null }))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => {
  received.props = props
  return <div data-chart-theme={props.theme || 'default'} />
} }))

it('updates a mounted chart when appearance changes, preserving events, renderer and loading options', async () => {
  window.localStorage.clear()
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const click = vi.fn()
  const option = { tooltip: { backgroundColor: '#fff' }, series: [{ type: 'pie', data: [1, 2] }] }
  try {
    await act(async () => root.render(<ThemedEChart option={option} onEvents={{ click }} opts={{ renderer: 'svg' }} notMerge showLoading />))
    await act(async () => setAppearance('dark'))
    expect(host.querySelector('[data-chart-theme="dark"]')).not.toBeNull()
    expect(received.props?.option.tooltip.backgroundColor).toBe('#2b2b30')
    expect(received.props?.opts?.renderer).toBe('svg')
    expect(received.props?.onEvents?.click).toBe(click)
    expect(received.props?.notMerge).toBe(true)
    await act(async () => setAppearance('light'))
    expect(received.props?.option).toBe(option)
    expect(host.querySelector('[data-chart-theme="default"]')).not.toBeNull()
  } finally {
    await act(async () => root.unmount())
    host.remove()
    window.localStorage.clear()
  }
})
