/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/SyncSettingsButton', () => ({
  default: () => <button>同步设置</button>,
}))
const prodActions = vi.hoisted(() => ({
  getPlans: vi.fn(),
}))
vi.mock('@/actions/production', () => prodActions)

import PlanPage from './page'

const PLANS = [
  {
    id: 'pl-1',
    workshop: '203车间',
    product_name: 'L-苯丙氨酸',
    plan_date: '2026-07-01',
    planned_yield: 800000,
    unit: 'KG',
    actual_completion: 92400,
    completion_rate: 0.1155,
    safety_status: '无异常',
    quality_status: '无异常',
    remarks: '',
    source: 'feishu',
  },
]

describe('PlanPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    prodActions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: PLANS,
      meta: { total: 1 },
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function renderAndSettle() {
    act(() => {
      root.render(<App><PlanPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
  }

  it('renders the synced plan ledger with feishu columns (read-only)', async () => {
    await renderAndSettle()
    const text = container.textContent || ''
    // 飞书原表列头
    expect(text).toContain('车间')
    expect(text).toContain('产品')
    expect(text).toContain('日期')
    expect(text).toContain('单位')
    expect(text).toContain('计划产量')
    expect(text).toContain('实际完成')
    expect(text).toContain('完成率')
    expect(text).toContain('安环情况')
    expect(text).toContain('质量情况')
    expect(text).toContain('备注')
    // 行数据：千分位产量 + 完成率百分比
    expect(text).toContain('203车间')
    expect(text).toContain('800,000')
    expect(text).toContain('92,400')
    expect(text).toContain('11.6%')
    expect(text).toContain('无异常')
    // 同步入口保留；只读无新增
    expect(text).toContain('同步设置')
    expect(text).not.toContain('新建计划')
  })

  it('shows six placeholder summary cards without values', async () => {
    await renderAndSettle()
    const text = container.textContent || ''
    // 占位卡标题（KG 与批分开）
    expect(text).toContain('计划产量（KG）')
    expect(text).toContain('实际完成（KG）')
    expect(text).toContain('完成率（KG）')
    expect(text).toContain('计划产量（批）')
    expect(text).toContain('实际完成（批）')
    expect(text).toContain('完成率（批）')
    // 占位样式：-- + 数据源待接入，无真实汇总数值
    expect(text).toContain('数据源待接入')
    expect(text).not.toContain('861,000')
    expect(text).not.toContain('11.5%')
    const summaryCards = Array.from(container.querySelectorAll('.ant-card')).filter(
      (c) => c.textContent?.includes('数据源待接入'),
    )
    expect(summaryCards).toHaveLength(6)
  })

  it('keeps the sync entry and shows empty table when no plans synced', async () => {
    prodActions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
    })
    await renderAndSettle()
    const text = container.textContent || ''
    expect(text).toContain('同步设置')
    // 占位卡不受数据影响
    expect(text).toContain('数据源待接入')
    expect(container.querySelectorAll('.ant-table-row')).toHaveLength(0)
  })
})
