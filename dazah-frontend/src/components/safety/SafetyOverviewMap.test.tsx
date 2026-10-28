/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const pushMock = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    AimOutlined: Icon,
    EnvironmentOutlined: Icon,
    ExpandOutlined: Icon,
    QuestionCircleOutlined: Icon,
    ShrinkOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  type AnyProps = Record<string, unknown>
  const Box = ({ children, title, extra }: AnyProps) =>
    createElement('div', null, title as ReactNode, extra as ReactNode, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  const Collapse = ({ items }: { items?: Array<{ key: string; label: ReactNode; children: ReactNode }> }) =>
    createElement(
      'div',
      { 'data-collapse': 'true' },
      (items ?? []).map((item) =>
        createElement(
          'section',
          { key: item.key, 'data-collapse-item': item.key },
          createElement('h4', null, item.label),
          item.children
        )
      )
    )
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)

  return {
    Button,
    Card: Box,
    Collapse,
    Drawer: ({ children, open, title }: AnyProps) =>
      createElement(
        'div',
        { 'data-drawer-open': String(Boolean(open)), 'data-drawer-title': title ? 'set' : 'none' },
        open ? (children as ReactNode) : null
      ),
    Empty: () => createElement('div', null, 'empty'),
    Space: Box,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
  }
})

import SafetyOverviewMap from './SafetyOverviewMap'
import type { SafetyOverviewData } from '@/actions/safety'

const OVERVIEW: SafetyOverviewData = {
  buildings: [
    { id: 'b-1', code: '101', name: '101车间', category: 'workshop', x_pct: 79, y_pct: 67 },
    { id: 'b-2', code: '802', name: '污水处理系统', category: 'env', x_pct: 47, y_pct: 12 },
  ],
  markers: [
    {
      building_id: 'b-1',
      name: '101车间',
      x_pct: 79,
      y_pct: 67,
      total: 2,
      levels: { level_2: 2 },
      items: [
        {
          source: 'special_op',
          matched_by: 'location',
          title: '动火作业测试',
          location_text: '101车间',
          building_id: 'b-1',
          department: '提炼四部',
          risk_level: 'level_2',
          operation_type: 'hot_work',
          happened_at: '2026-10-27T03:00:00Z',
          detail_url: '/safety/special-ops',
        },
        {
          source: 'daily_risk',
          matched_by: 'location',
          title: '常规巡查报备',
          location_text: '101车间',
          building_id: 'b-1',
          department: '提炼五部',
          risk_level: 'level_3',
          operation_type: '',
          happened_at: '2026-10-27T01:00:00Z',
          detail_url: '/safety/risk-reporting',
        },
      ],
    },
  ],
  unmapped: [
    {
      location_text: '完全陌生地点',
      total: 1,
      items: [
        {
          source: 'daily_risk',
          matched_by: 'location',
          title: '未知地点报备',
          location_text: '完全陌生地点',
          building_id: null,
          department: '提炼六部',
          risk_level: 'level_3',
          operation_type: '',
          happened_at: '2026-10-27T02:00:00Z',
          detail_url: '/safety/risk-reporting',
        },
      ],
    },
  ],
  over_limit_chemicals: [],
  source_totals: { special_op: 2, daily_risk: 1 },
  weekly_operation_types: [],
  open_hazard_count: 0,
  generated_at: '2026-10-27T03:00:00Z',
}

let root: Root | null = null
let container: HTMLElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
})

afterEach(() => {
  root?.unmount()
  container.remove()
  vi.clearAllMocks()
})

async function renderMap(overview: SafetyOverviewData) {
  root = createRoot(container)
  await act(async () => {
    root!.render(createElement(SafetyOverviewMap, { overview }))
  })
}

describe('SafetyOverviewMap', () => {
  it('renders vector campus map with count bubbles only on risk buildings', async () => {
    await renderMap(OVERVIEW)
    const image = container.querySelector('img')
    expect(image).not.toBeNull()
    expect(image!.getAttribute('src')).toBe('/safety/campus-map.svg')

    // 有风险的建筑渲染数量气泡（title 含建筑名），点击可打开明细
    const riskBubble = container.querySelector('button[title^="101车间 · 当日 2 条"]')
    expect(riskBubble).not.toBeNull()
    expect(riskBubble!.textContent).toContain('101车间')
    expect(riskBubble!.textContent).toContain('2')

    // 无风险建筑不再渲染覆盖层（名称已烙入底图）
    expect(container.innerHTML).not.toContain('污水处理系统 · 当日')

    expect(container.innerHTML).toContain('当日 3 条 · 落点 2 · 未映射 1')
    expect(container.innerHTML).toContain('未映射地点 1 处')
    expect(container.innerHTML).toContain('特殊作业 2')
  })

  it('opens building detail drawer on bubble click and navigates on item click', async () => {
    await renderMap(OVERVIEW)
    // 风险建筑渲染数量气泡（title 含建筑名与条数）
    const bubble = container.querySelector('button[title^="101车间 · 当日 2 条"]')
    expect(bubble).not.toBeNull()
    expect(bubble!.textContent).toContain('101车间 2')
    await act(async () => {
      ;(bubble as HTMLElement).click()
    })
    const drawer = container.querySelector('[data-drawer-open="true"]')
    expect(drawer).not.toBeNull()
    expect(drawer!.innerHTML).toContain('动火作业测试')
    expect(drawer!.innerHTML).toContain('常规巡查报备')

    const itemRow = drawer!.querySelector('[data-item-title="动火作业测试"]')
    expect(itemRow).not.toBeNull()
    await act(async () => {
      ;(itemRow as HTMLElement).click()
    })
    expect(pushMock).toHaveBeenCalledWith('/safety/special-ops')
  })

  it('全宽切换按钮往返切换', async () => {
    const view = await renderMap(OVERVIEW)
    const toggle = Array.from(
      container.querySelectorAll<HTMLButtonElement>('button'),
    ).find((b) => b.textContent === '全宽')
    expect(toggle).toBeTruthy()
    await act(async () => {
      toggle!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    const half = Array.from(container.querySelectorAll<HTMLButtonElement>('button')).find((b) => b.textContent === '半宽')
    expect(half).toBeTruthy()
    await act(async () => {
      half!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
  })
})
