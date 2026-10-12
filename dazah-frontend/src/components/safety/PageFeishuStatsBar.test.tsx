/* @vitest-environment happy-dom */

import type { CSSProperties, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const chartMocks = vi.hoisted(() => ({ onSelect: vi.fn() }))

vi.mock('echarts-for-react', async () => {
  const { createElement } = await import('react')
  return {
    default: ({
      option,
      onEvents,
    }: {
      option: Record<string, unknown>
      onEvents?: { click: (params: { name?: string }) => void }
    }) =>
      createElement(
        'div',
        { 'data-chart': JSON.stringify(option) },
        createElement(
          'button',
          {
            type: 'button',
            'data-chart-click': 'true',
            onClick: () => onEvents?.click({ name: '其他' }),
          },
          'chart-click'
        )
      )
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type Props = {
    children?: ReactNode
    style?: CSSProperties
    title?: ReactNode
  }

  const Box = ({ children, style, title }: Props) =>
    createElement('div', { style, 'data-title': title }, title, children)
  const EmptyBox = ({ style }: Props) => createElement('div', { style })
  const Empty = Object.assign(
    ({ style }: Props) => createElement('div', { style, className: 'ant-empty' }),
    { PRESENTED_IMAGE_SIMPLE: 'simple' }
  )
  void EmptyBox

  const Text = ({ children }: Props) => createElement('span', null, children)
  return {
    Card: Box,
    Empty,
    Typography: { Text },
  }
})

import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import PageFeishuStatsBar from './PageFeishuStatsBar'
import type { PageTableStats } from '@/lib/safety-page-tables'

const stats: PageTableStats = {
  page_key: 'safety:risk-hazard:hazard-inspection:hazard-duty',
  page_name: '24小时值班隐患',
  total: 349,
  groups: [
    {
      field: '值班日期',
      kind: 'date',
      mode: 'month',
      buckets: [
        { key: '2026-07', count: 97 },
        { key: '2026-08', count: 80 },
        { key: '2026-09', count: 102 },
        { key: '2026-10', count: 70 },
      ],
    },
    {
      field: '车间/位置',
      kind: 'text',
      mode: 'value',
      buckets: [
        { key: '201一车间', count: 26 },
        { key: '201二车间', count: 11 },
        { key: '其他', count: 4 },
      ],
    },
    {
      field: '整改情况',
      kind: 'select',
      mode: 'value',
      buckets: [
        { key: '已整改', count: 339 },
        { key: '未整改', count: 10 },
      ],
    },
  ],
}

function chartPayloads(html: string): Record<string, unknown>[] {
  return [...html.matchAll(/data-chart="([^"]+)"/g)].map((match) =>
    JSON.parse(
      match[1].replaceAll('&quot;', '"').replaceAll('&#x2F;', '/').replaceAll('&amp;', '&')
    )
  )
}

describe('PageFeishuStatsBar', () => {
  it('renders three echarts cards fed with the aggregated data', () => {
    const html = renderToStaticMarkup(<PageFeishuStatsBar stats={stats} />)
    const charts = chartPayloads(html)

    expect(charts).toHaveLength(3)

    const [monthOption, workshopOption, statusOption] = charts as [
      { series: { data: number[] }[]; xAxis: { data: string[] } },
      { series: { data: number[] }[]; yAxis: { data: string[] } },
      {
        series: { data: { name: string; value: number; itemStyle: { color: string } }[] }[]
        title: { text: string }
      },
    ]

    // 月度趋势：柱状图按时间升序
    expect(monthOption.xAxis.data).toEqual(['7月', '8月', '9月', '10月'])
    expect(monthOption.series[0].data).toEqual([97, 80, 102, 70])

    // 车间分布：横向条形图（反转后最大值在最上）
    expect(workshopOption.yAxis.data).toEqual(['其他', '201二车间', '201一车间'])
    expect(workshopOption.series[0].data).toEqual([4, 11, 26])

    // 整改情况：环形图 + 中心总数，语义配色
    expect(statusOption.title.text).toBe('349')
    const donut = statusOption.series[0].data
    expect(donut.find((item) => item.name === '已整改')?.itemStyle.color).toBe('#1aae39')
    expect(donut.find((item) => item.name === '未整改')?.itemStyle.color).toBe('#dd5b00')

    // 卡片标题顺序：月份 / 车间 / 整改
    const titles = [...html.matchAll(/data-title="([^"]+)"/g)].map((match) => match[1])
    expect(titles).toEqual(['月度隐患趋势', '车间隐患分布', '整改情况'])
  })

  it('renders empty placeholders for missing groups', () => {
    const html = renderToStaticMarkup(
      <PageFeishuStatsBar
        stats={{
          page_key: 'k',
          page_name: '24小时值班隐患',
          total: 0,
          groups: [
            { field: '值班日期', kind: 'date', mode: 'month', buckets: [] },
            {
              field: '车间/位置',
              kind: 'text',
              mode: 'value',
              buckets: [{ key: '201一车间', count: 0 }],
            },
          ],
        }}
      />
    )

    // 聚合结果为空的维度展示空态，而不是画出空图
    expect(html).toContain('ant-empty')
  })

  it('renders nothing without stats', () => {
    const html = renderToStaticMarkup(<PageFeishuStatsBar stats={null} />)
    expect(html).toBe('')
  })
})

describe('PageFeishuStatsBar interactions and colors', () => {
  it('colors neutral buckets grey and forwards chart clicks to onSelect', async () => {
    const neutralStats: PageTableStats = {
      page_key: 'k',
      page_name: '24小时值班隐患',
      total: 8,
      groups: [
        {
          field: '整改情况',
          kind: 'select',
          mode: 'value',
          buckets: [
            { key: '已整改', count: 5 },
            { key: '其他', count: 3 },
          ],
        },
      ],
    }

    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    act(() => {
      root.render(
        createElement(PageFeishuStatsBar, {
          stats: neutralStats,
          onSelect: chartMocks.onSelect,
        })
      )
    })

    const html = container.innerHTML
    // 「其他」不属于未/已语义 → 中性灰
    expect(html).toContain('#bfbfbf')

    const clickButton = container.querySelector(
      'button[data-chart-click="true"]'
    ) as HTMLButtonElement
    act(() => clickButton?.click())

    expect(chartMocks.onSelect).toHaveBeenCalledWith('整改情况', '其他')

    await act(async () => root.unmount())
    container.remove()
  })
})
