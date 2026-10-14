/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import type { DOEExperiment } from '@/types/rd'
import { AntdProvider } from '@/components/AntdProvider'
import { ModuleDOE } from './ModuleDOE'

const charts = vi.hoisted(() => ({ props: [] as EChartsReactProps[] }))
vi.mock('echarts-gl', () => ({}))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => { charts.props.push(props); return <div data-chart="measured" /> } }))
const initialData: DOEExperiment = {
  id: 'doe-real', design_type: 'response_surface',
  factors: [{ name: '温度', symbol: 'T', type: 'numeric', levels: { lower: 20, upper: 80 }, unit: '℃' }, { name: '时间', symbol: 't', type: 'numeric', levels: { lower: 1, upper: 6 }, unit: 'h' }],
  responses: [{ name: '收率', unit: '%', target: 'maximize', weight: 100 }],
  runs: [{ run_no: 1, factor_values: { T: 65, t: 3 }, response_values: { 收率: 91.2 }, status: 'completed' }],
  analysis_result: { anova_table: [], regression_model: 'UNVERIFIED MODEL', r_squared: 0.99, adjusted_r_squared: 0.98, optimal_conditions: { T: 80 }, predicted_response: { 收率: 101 }, significant_factors: ['T'] },
}

it('shows recorded measurements and saves observations without legacy fabricated fitting results', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const onComplete = vi.fn()
  try {
    await act(async () => root.render(<AntdProvider><ModuleDOE optimizationId="test" initialData={initialData} onComplete={onComplete} /></AntdProvider>))
    const tab = [...host.querySelectorAll<HTMLElement>('[role="tab"]')].find((item) => item.textContent?.includes('实测数据与图表'))
    await act(async () => tab?.click())
    expect(host.textContent).toContain('统计拟合尚未接入')
    expect(host.textContent).not.toContain('UNVERIFIED MODEL')
    expect(host.textContent).not.toContain('AI生成')
    expect(charts.props.at(-1)?.option.series[0].data).toEqual([{ name: '实验 1', value: [65, 3, 91.2] }])
    const save = [...host.querySelectorAll<HTMLButtonElement>('button')].find((item) => item.textContent?.includes('确认实测记录'))
    expect(save?.disabled).toBe(false)
    await act(async () => save?.click())
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ id: 'doe-real', runs: initialData.runs }))
    expect(onComplete.mock.calls[0][0]).not.toHaveProperty('analysis_result')
  } finally { await act(async () => root.unmount()); host.remove() }
})

it('blocks confirmation for missing measurements and shows an honest empty chart state', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const onComplete = vi.fn()
  try {
    await act(async () => root.render(<AntdProvider><ModuleDOE optimizationId="empty" initialData={{ ...initialData, runs: [] }} onComplete={onComplete} /></AntdProvider>))
    const tab = [...host.querySelectorAll<HTMLElement>('[role="tab"]')].find((item) => item.textContent?.includes('实测数据与图表'))
    await act(async () => tab?.click())
    expect(host.textContent).toContain('暂无可绘制的实测实验点')
    expect(host.querySelector('[data-chart]')).toBeNull()
    const save = [...host.querySelectorAll<HTMLButtonElement>('button')].find((item) => item.textContent?.includes('确认实测记录'))
    expect(save?.disabled).toBe(true)
    expect(onComplete).not.toHaveBeenCalled()
  } finally { await act(async () => root.unmount()); host.remove() }
})

it('switches reaction steps without plotting or saving the previous step measurements', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const onComplete = vi.fn()
  const second = { ...initialData, id: 'doe-second', runs: [{ ...initialData.runs[0], response_values: { 收率: 72.4 } }] }
  try {
    await act(async () => root.render(<AntdProvider><ModuleDOE optimizationId="steps" currentStepId="first"
      reactionSteps={[{ id: 'first', step_name: '第一步', step_order: 1, status: 'in_progress', doe_experiment: initialData }, { id: 'second', step_name: '第二步', step_order: 2, status: 'pending', doe_experiment: second }]}
      onComplete={onComplete} /></AntdProvider>))
    const input = host.querySelector<HTMLInputElement>('[aria-label="反应步骤"]')
    await act(async () => { input?.focus(); input?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', keyCode: 40, bubbles: true })) })
    const option = [...document.querySelectorAll<HTMLElement>('.ant-select-item-option')].find((item) => item.textContent?.includes('第二步'))
    expect(option).toBeDefined()
    await act(async () => option?.click())
    await act(async () => [...host.querySelectorAll<HTMLElement>('[role="tab"]')].find((item) => item.textContent?.includes('实测数据与图表'))?.click())
    expect(charts.props.at(-1)?.option.series[0].data[0].value).toEqual([65, 3, 72.4])
    await act(async () => [...host.querySelectorAll<HTMLButtonElement>('button')].find((item) => item.textContent?.includes('确认实测记录'))?.click())
    expect(onComplete.mock.calls[0][0].id).toBe('doe-second')
  } finally { await act(async () => root.unmount()); host.remove() }
})

it('removes a cleared response instead of retaining an old value or inventing zero', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  try {
    await act(async () => root.render(<AntdProvider><ModuleDOE optimizationId="clear" initialData={initialData} onComplete={vi.fn()} /></AntdProvider>))
    const input = [...host.querySelectorAll<HTMLInputElement>('input')].find((item) => item.value === '91.2')
    expect(input).toBeDefined()
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
      input?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const save = [...host.querySelectorAll<HTMLButtonElement>('button')].find((item) => item.textContent?.includes('确认实测记录'))
    expect(save?.disabled).toBe(true)
  } finally { await act(async () => root.unmount()); host.remove() }
})
