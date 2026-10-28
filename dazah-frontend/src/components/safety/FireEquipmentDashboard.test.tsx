/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  onDrill: vi.fn(),
  onFilterUninspected: vi.fn(),
}))

vi.mock('@/components/shared/ThemedEChart', () => ({
  default: ({ option }: { option?: { series?: unknown[] } }) =>
    createElement('div', {
      'data-chart-series': String(option?.series?.length ?? 0),
    }),
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown>
  const Box = (props: AnyProps) =>
    createElement(
      'div',
      {
        onClick: props.onClick as never,
        'data-card': String(props.title ?? ''),
        'data-stat-card': props['data-stat-card'] as never,
      },
      props.title as ReactNode,
      props.extra as ReactNode,
      props.children as ReactNode
    )
  const Button = (props: AnyProps) =>
    createElement(
      'button',
      {
        type: 'button',
        onClick: props.onClick as never,
        'data-drill-button': props['data-drill-button'] as never,
      },
      props.children as ReactNode
    )
  const Segmented = ({ options, value, onChange }: AnyProps) =>
    createElement(
      'span',
      null,
      (options as Array<{ label: string; value: number }>).map((option) =>
        createElement(
          'button',
          {
            key: String(option.value),
            type: 'button',
            'data-window': String(option.value),
            'data-active': String(option.value === value),
            onClick: () => (onChange as (v: number) => void)?.(option.value),
          },
          option.label
        )
      )
    )
  const Text = ({ children, type }: AnyProps) =>
    createElement(
      'span',
      { 'data-text-type': String(type ?? '') },
      children as ReactNode
    )

  return {
    Button,
    Card: Box,
    Col: Box,
    Row: Box,
    Segmented,
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
    theme: { useToken: () => ({ token: {} }) },
  }
})

import FireEquipmentDashboard from './FireEquipmentDashboard'

const STATS = {
  total: 1696,
  extinguisher_count: 1696,
  hydrant_count: 0,
  inspected_this_month: 20,
  uninspected_this_month: 1676,
  failed_this_month: 1,
  expired_count: 440,
  expiring_in_30_count: 3,
  is_configured: true,
  writeback_enabled: true,
  last_synced_at: null,
  last_sync_status: null,
  last_sync_error: null,
}

const DASHBOARD = {
  expiry_summary: { overdue: 440, within_7: 0, within_15: 1, within_30: 3 },
  trend: [
    { month: '2026-09', count: 2 },
    { month: '2026-10', count: 18 },
  ],
  workshop_coverage: [
    { tab_name: '101-2、102-1车间', total: 134, inspected: 12 },
    { tab_name: '103车间', total: 103, inspected: 8 },
  ],
}

function renderDashboard(
  overrides: Partial<Parameters<typeof FireEquipmentDashboard>[0]> = {}
) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(FireEquipmentDashboard, {
        stats: STATS as never,
        dashboard: DASHBOARD as never,
        drilling: null,
        onDrill: mocks.onDrill,
        onFilterUninspected: mocks.onFilterUninspected,
        ...overrides,
      })
    )
  })
  return { container, root }
}

async function click(container: HTMLElement, selector: string) {
  const button = container.querySelector(selector)
  expect(button).not.toBeNull()
  await act(async () => {
    button!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

describe('FireEquipmentDashboard', () => {
  let root: Root | null = null
  let container: HTMLElement | null = null

  beforeEach(() => {
    mocks.onDrill.mockClear()
    mocks.onFilterUninspected.mockClear()
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = null
    container = null
  })

  it('renders stat cards, expiry buckets and coverage', () => {
    const view = renderDashboard()
    root = view.root
    container = view.container
    expect(container.textContent).toContain('器材总数')
    expect(container.textContent).toContain('1696')
    expect(container.textContent).toContain('已过期 440 台')
    expect(container.textContent).toContain('30 天内到期 3 台')
    expect(container.textContent).toContain('各车间本月点检覆盖（台）')
    // 两张图表拿到正确的 series（趋势 1 条 / 覆盖堆叠 2 条）
    expect(container.querySelector('[data-chart-series="1"]')).not.toBeNull()
    expect(container.querySelector('[data-chart-series="2"]')).not.toBeNull()
  })

  it('switches window and drills with due filter', async () => {
    const view = renderDashboard()
    root = view.root
    container = view.container

    // 默认 30 天窗口：440 过期 + 3 临期 = 443
    expect(container.textContent).toContain('443')
    await click(container, '[data-drill-button]')
    expect(mocks.onDrill).toHaveBeenCalledWith('due_30')

    // 切到 7 天窗口后再穿透 → due_7
    await click(container, '[data-window="7"]')
    await click(container, '[data-drill-button]')
    expect(mocks.onDrill).toHaveBeenLastCalledWith('due_7')
  })

  it('shows cancel state and drills null when already drilling', async () => {
    const view = renderDashboard({ drilling: 'due_30' })
    root = view.root
    container = view.container
    expect(container.textContent).toContain('取消筛选')
    await click(container, '[data-drill-button]')
    expect(mocks.onDrill).toHaveBeenCalledWith(null)
  })

  it('fires uninspected filter from stat card', async () => {
    const view = renderDashboard()
    root = view.root
    container = view.container
    const uninspected = container.querySelector(
      '[data-stat-card="本月未检"]'
    )
    expect(uninspected).not.toBeNull()
    await act(async () => {
      uninspected!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.onFilterUninspected).toHaveBeenCalled()
  })
})
