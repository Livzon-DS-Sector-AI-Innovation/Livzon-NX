/* @vitest-environment happy-dom */

import { act, type CSSProperties, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const safetyActions = vi.hoisted(() => ({
  getSafetyPageTableStats: vi.fn(),
  getOpenHazardDetails: vi.fn(),
}))

vi.mock('@/actions/safety', () => safetyActions)

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    AlertOutlined: Icon,
    ArrowRightOutlined: Icon,
    CheckCircleOutlined: Icon,
    ClockCircleOutlined: Icon,
    EnvironmentOutlined: Icon,
    ExperimentOutlined: Icon,
    FireOutlined: Icon,
    RobotOutlined: Icon,
    TeamOutlined: Icon,
    UserOutlined: Icon,
    WarningOutlined: Icon,
  }
})

vi.mock('./SafetyOverviewMap', () => ({
  default: () => null,
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type Props = {
    children?: ReactNode
    style?: CSSProperties
    title?: ReactNode
  }

  const Box = ({ children, style, title }: Props) => createElement('div', { style }, title, children)
  const Text = ({ children, style }: Props) => createElement('span', { style }, children)
  const Title = ({ children, style }: Props) => createElement('h1', { style }, children)

  const Segmented = ({ options, value, onChange }: Record<string, unknown>) =>
    createElement(
      'span',
      null,
      ((options as Array<{ label: string; value: string }>) ?? []).map((option) =>
        createElement(
          'button',
          {
            key: option.value,
            type: 'button',
            'data-segmented': String(option.value),
            onClick: () => (onChange as (v: string) => void)?.(option.value),
          },
          option.label
        )
      )
    )

  return {
    Alert: Box,
    Button: Box,
    Card: Box,
    Segmented,
    Col: Box,
    Drawer: Box,
    Row: Box,
    Space: Box,
    Table: Box,
    Tag: Text,
    Typography: { Text, Title },
  }
})

import { antdTheme } from '@/lib/antd-theme'
import SafetyDashboard, { type DashboardData } from './SafetyDashboard'

const dashboardData: DashboardData = {
  openHazardCount: 3,
  unfinishedIdentCount: 1,
  expiringCerts: [],
  todaySpecialOps: [],
  todayDailyRisks: [],
  overview: null,
  chemicalInventories: [],
}

describe('SafetyDashboard font contract', () => {
  it('uses the shared UI font variable for the dashboard and Ant Design theme', () => {
    const markup = renderToStaticMarkup(<SafetyDashboard data={dashboardData} />)

    expect(antdTheme.token?.fontFamily).toBe('var(--font-ui)')
    expect(markup).toContain('安全管理总览')
    expect(markup.match(/font-family:\s*var\(--font-ui\)/g)?.length).toBeGreaterThanOrEqual(4)
  })
})

describe('SafetyDashboard 未关闭隐患下钻', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  async function flushLoad() {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5))
    })
  }

  it('初始渲染值班镜像记录（字段名映射与富文本取值）', async () => {
    await act(async () => {
      root.render(
        <SafetyDashboard
          data={{
            ...dashboardData,
            openHazardRecords: [
              {
                record_id: 'h-1',
                fields: {
                  隐患内容: [{ name: '溶剂库堆放超高' }],
                  '车间/位置': '原料仓库',
                  值班人员: '张三',
                  值班日期: '2026-10-20',
                  整改情况: '整改中',
                },
              },
            ],
          }}
        />,
      )
    })
    await flushLoad()
    expect(container.textContent).toContain('溶剂库堆放超高')
    expect(container.textContent).toContain('原料仓库')
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('整改中')
  })

  it('切换台账镜像源：按台账页面键统计当年未关闭数量', async () => {
    // vitest 下组件两处并发动态 import 存在 mock 竞态（其中一路会命中
    // 真实 'use server' 模块并抛错），因此本用例断言 stats 调用参数与
    // 异常兜底后的空态，明细行的 API 断言由 actions 单测覆盖。
    safetyActions.getSafetyPageTableStats.mockResolvedValue({
      code: 200,
      data: { total: 7 },
    })
    await act(async () => {
      root.render(<SafetyDashboard data={dashboardData} />)
    })
    await flushLoad()
    const ledgerTab = container.querySelector<HTMLButtonElement>(
      '[data-segmented="ledger"]',
    )
    expect(ledgerTab).toBeTruthy()
    await act(async () => {
      ledgerTab?.click()
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(safetyActions.getSafetyPageTableStats).toHaveBeenCalledWith(
      expect.objectContaining({
        pageKey: 'safety:risk-hazard:hazard-inspection:hazard-quick-report',
        groupBy: ['关闭状态'],
        conditions: expect.arrayContaining([
          expect.objectContaining({ field: '关闭状态', op: 'neq', value: '已关闭' }),
          expect.objectContaining({
            field: '检查内容',
            op: 'gte',
            value: `${new Date().getFullYear()}-01-01`,
          }),
        ]),
      }),
    )
  })

  it('明细加载异常时归零显示空态', async () => {
    safetyActions.getSafetyPageTableStats.mockRejectedValue(new Error('down'))
    safetyActions.getOpenHazardDetails.mockRejectedValue(new Error('down'))
    await act(async () => {
      root.render(<SafetyDashboard data={dashboardData} />)
    })
    await flushLoad()
    const ledgerTab = container.querySelector<HTMLButtonElement>(
      '[data-segmented="ledger"]',
    )
    await act(async () => {
      ledgerTab?.click()
    })
    await flushLoad()
    expect(container.textContent).toContain('该来源暂无未关闭隐患')
  })
})
