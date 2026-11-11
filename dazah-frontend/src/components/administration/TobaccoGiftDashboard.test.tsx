/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: navigation.refresh }),
}))

// ECharts 在 happy-dom 下无画布；这里只断言传入的 option。
const chartOptions = vi.hoisted(() => [] as unknown[])
vi.mock('@/components/shared/ThemedEChart', () => ({
  default: ({ option }: { option: unknown }) => {
    chartOptions.push(option)
    return <div data-testid="chart" />
  },
}))

import {
  TobaccoGiftDashboard,
  buildBarOption,
  formatMoney,
  formatQuantity,
  formatSyncedAt,
  sortByName,
} from './TobaccoGiftDashboard'
import TobaccoGiftRequisitionCard from './TobaccoGiftRequisitionCard'
import type { TobaccoGiftDashboardStats } from '@/types/administration'

let root: Root | null = null

function render(node: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(node)
  })
  return container
}

afterEach(() => {
  act(() => root?.unmount())
  root = null
  document.body.innerHTML = ''
  chartOptions.length = 0
  vi.clearAllMocks()
})

const stats: TobaccoGiftDashboardStats = {
  item_categories: 35,
  item_total_value: 152547,
  item_total_count: 515,
  requisitioned_total: 16,
  inventory_by_item: [{ name: '五粮液', value: 87 }],
  requisition_by_item: [{ name: '茅台', value: 48 }],
  value_by_item: [{ name: '茅台', value: 25194 }],
  requisition_by_employee: [{ name: '张三', value: 12 }],
  inventory_synced_at: '2026-11-09T08:00:00Z',
  requisition_synced_at: '2026-11-09T08:00:00Z',
}

describe('formatters', () => {
  it('formats quantity and money for display', () => {
    expect(formatQuantity(515)).toBe('515')
    expect(formatQuantity(2.5)).toBe('2.5')
    expect(formatMoney(152547)).toBe('¥152,547')
    expect(formatMoney(0.5)).toBe('¥0.5')
  })

  it('renders sync time in Asia/Shanghai regardless of host timezone', () => {
    // 回归：SSR（UTC 容器）与浏览器（东八区）输出不一致曾导致水合报错
    expect(formatSyncedAt('2026-11-09T06:57:19Z')).toContain('14:57:19')
    expect(formatSyncedAt(null)).toBe('尚未同步')
    expect(formatSyncedAt('not-a-date')).toBe('尚未同步')
  })
})

describe('buildBarOption', () => {
  it('sorts bars by item name (pinyin) like the Feishu dashboard axis', () => {
    const option = buildBarOption(
      [
        { name: '摘要', value: 46 },
        { name: '白盒中华', value: 87 },
        { name: '五粮液', value: 36 },
      ],
      '物品总数',
      '#1677ff',
    ) as {
      xAxis: { data: string[]; axisLabel: { rotate: number } }
      series: Array<{ data: number[]; name: string }>
    }
    // 拼音序：白(bai) < 五(wu) < 摘(zhai)；码位序会是 五 < 摘 < 白，可区分
    expect(option.xAxis.data).toEqual(['白盒中华', '五粮液', '摘要'])
    expect(option.series[0].data).toEqual([87, 36, 46])
    expect(option.xAxis.axisLabel.rotate).toBe(45)
    expect(option.series[0].name).toBe('物品总数')
  })

  it('sortByName keeps values attached to their names', () => {
    expect(
      sortByName([
        { name: '茅台', value: 5 },
        { name: '汾酒', value: 6 },
      ]),
    ).toEqual([
      { name: '汾酒', value: 6 },
      { name: '茅台', value: 5 },
    ])
  })

  it('hides bar top labels when there are many bars', () => {
    const many = Array.from({ length: 20 }, (_, index) => ({ name: `物品${index}`, value: index }))
    const option = buildBarOption(many, '物品总数', '#1677ff') as {
      series: Array<{ label: { show: boolean } }>
      grid: { top: number }
    }
    expect(option.series[0].label.show).toBe(false)
    expect(option.grid.top).toBe(12)
  })

  it('uses money formatting for amount charts', () => {
    const option = buildBarOption([{ name: '茅台', value: 25194 }], '总金额', '#1677ff', true) as {
      series: Array<{ label: { formatter: (params: { value: number }) => string } }>
    }
    expect(option.series[0].label.formatter({ value: 25194 })).toBe('¥25,194')
  })
})

describe('TobaccoGiftDashboard', () => {
  it('renders the four metric cards and four charts', () => {
    const container = render(<TobaccoGiftDashboard stats={stats} />)
    const text = container.textContent ?? ''
    expect(text).toContain('物品品类')
    expect(text).toContain('35')
    expect(text).toContain('¥152,547')
    expect(text).toContain('515')
    expect(text).toContain('已领用物品总数')
    expect(text).toContain('已领用」的领用单数量合计')
    expect(text).toContain('员工领用统计')
    expect(text).toContain('不含已作废')
    expect(container.querySelectorAll('[data-testid="chart"]')).toHaveLength(4)
    expect(text).not.toContain('尚未完成飞书数据绑定')
  })

  it('guides to Feishu settings before tables are bound and synced', () => {
    const container = render(
      <TobaccoGiftDashboard
        stats={{
          ...stats,
          inventory_by_item: [],
          requisition_by_item: [],
          value_by_item: [],
          requisition_by_employee: [],
          inventory_synced_at: null,
          requisition_synced_at: null,
        }}
      />,
    )
    expect(container.textContent).toContain('尚未完成飞书数据绑定')
    expect(container.querySelector('a[href="/admin/settings/feishu"]')).not.toBeNull()
    expect(container.textContent).toContain('暂无统计数据')
  })

  it('warns which table is still missing when only one side is synced', () => {
    const container = render(
      <TobaccoGiftDashboard stats={{ ...stats, inventory_synced_at: null }} />,
    )
    expect(container.textContent).toContain('「物品清单」尚未绑定或同步')
    expect(container.textContent).not.toContain('尚未完成飞书数据绑定')
    expect(container.querySelector('a[href="/admin/settings/feishu"]')).not.toBeNull()
  })

  it('shows the load error without metric cards when stats are unavailable', () => {
    const container = render(<TobaccoGiftDashboard stats={null} error="网络异常" />)
    expect(container.textContent).toContain('仪表台统计加载失败')
    expect(container.textContent).not.toContain('物品品类')
  })

  it('refreshes server data on demand', () => {
    const container = render(<TobaccoGiftDashboard stats={stats} />)
    const button = Array.from(container.querySelectorAll('button')).find((node) =>
      node.textContent?.includes('刷新'),
    )
    expect(button).toBeDefined()
    act(() => {
      button!.click()
    })
    expect(navigation.refresh).toHaveBeenCalledTimes(1)
  })
})

describe('TobaccoGiftRequisitionCard', () => {
  it('links to the Feishu requisition form in a new tab', () => {
    const container = render(<TobaccoGiftRequisitionCard />)
    const link = container.querySelector('a')
    expect(link?.getAttribute('href')).toContain('feishu.cn/share/base/form/')
    expect(link?.getAttribute('target')).toBe('_blank')
    expect(container.textContent).toContain('领用申请')
  })
})
