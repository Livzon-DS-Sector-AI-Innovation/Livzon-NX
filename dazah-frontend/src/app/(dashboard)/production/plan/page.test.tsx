/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import dayjs from 'dayjs'
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
  getSalesPlanDetails: vi.fn(),
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
    window.localStorage.setItem('dazah.production.plan-page.tab', 'plan')
    // 月份记忆是会话级（sessionStorage），逐用例隔离避免相互污染
    window.sessionStorage.clear()
    prodActions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: PLANS,
      meta: { total: 1 },
    })
    prodActions.getSalesPlanDetails.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
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

  it('reloads the ledger when the month changes', async () => {
    await renderAndSettle()
    prodActions.getPlans.mockClear()
    const pickerRoot = container.querySelector('.ant-picker') as HTMLElement
    expect(pickerRoot).toBeTruthy()
    const input = pickerRoot.querySelector('input') as HTMLInputElement
    await act(async () => {
      input.focus()
      pickerRoot.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      pickerRoot.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const monthCell = Array.from(
      document.body.querySelectorAll('.ant-picker-cell'),
    ).find((c) => c.getAttribute('title') === '2026-10') as HTMLElement | undefined
    expect(monthCell).toBeTruthy()
    await act(async () => {
      ;(monthCell!.querySelector('.ant-picker-cell-inner') as HTMLElement | null)?.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    const lastCall = prodActions.getPlans.mock.calls.at(-1)?.[0] as
      | { month?: string }
      | undefined
    expect(lastCall?.month).toBe('2026-10')
  })

  it('renders the sales plan tab with sync entry and detail table', async () => {
    prodActions.getSalesPlanDetails.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'sp-1',
          product_name: 'L-色氨酸',
          data_month: '2026-05',
          unit: 'KG',
          source_table_name: '5月份销售计划执行表',
          month_planned_delivery: 69000,
          month_delivered_qty: 0,
          delivery_completion_rate: 0,
        },
      ],
      meta: { total: 1 },
    })
    await renderAndSettle()
    // 切到销售计划 Tab
    const salesTab = Array.from(
      container.querySelectorAll('.ant-tabs-tab'),
    ).find((t) => (t.textContent || '').trim() === '销售计划') as HTMLElement
    expect(salesTab).toBeTruthy()
    await act(async () => {
      salesTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const text = container.textContent || ''
    // 同步入口 + 数据来源表名（取同步写入的真实飞书表名）+ 列头与数据
    expect(text).toContain('同步设置')
    expect(text).toContain('5月份销售计划执行表 · 飞书同步数据')
    // 同步逻辑说明图标（悬浮/点击展示更新逻辑）
    const tipIcon = container.querySelector(
      '[data-testid="sales-sync-logic-tip"]',
    ) as HTMLElement | null
    expect(tipIcon).toBeTruthy()
    expect(text).toContain('本月计划发货量')
    expect(text).toContain('本月已发货量')
    expect(text).toContain('L-色氨酸')
    // 数据月份列：全部月份视图下区分每行归属月份
    expect(text).toContain('数据月份')
    expect(text).toContain('2026-05')
    expect(text).toContain('69,000')
    expect(prodActions.getSalesPlanDetails).toHaveBeenCalled()
  })

  it('restores the last active tab after a reload', async () => {
    await renderAndSettle()
    const salesTab = Array.from(
      container.querySelectorAll('.ant-tabs-tab'),
    ).find((t) => (t.textContent || '').trim() === '销售计划') as HTMLElement
    await act(async () => {
      salesTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 模拟刷新：卸载后重新挂载（localStorage 保留），应停留在销售计划
    act(() => root.unmount())
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    await renderAndSettle()
    const active = container.querySelector('.ant-tabs-tab-active')
    expect((active?.textContent || '').trim()).toBe('销售计划')
  })

  it('filters sales plan details by month via the picker', async () => {
    await renderAndSettle()
    // 切到销售计划 Tab 后使用月份选择器
    const salesTab = Array.from(
      container.querySelectorAll('.ant-tabs-tab'),
    ).find((t) => (t.textContent || '').trim() === '销售计划') as HTMLElement
    await act(async () => {
      salesTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    prodActions.getSalesPlanDetails.mockClear()
    const pane = container.querySelector(
      '.ant-tabs-tabpane-active',
    ) as HTMLElement
    const pickerRoot = pane.querySelector('.ant-picker') as HTMLElement
    expect(pickerRoot).toBeTruthy()
    const input = pickerRoot.querySelector('input') as HTMLInputElement
    await act(async () => {
      input.focus()
      pickerRoot.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      pickerRoot.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const monthCell = Array.from(
      document.body.querySelectorAll('.ant-picker-cell'),
    ).find((c) => c.getAttribute('title') === '2026-10') as HTMLElement | undefined
    expect(monthCell).toBeTruthy()
    await act(async () => {
      ;(monthCell!.querySelector('.ant-picker-cell-inner') as HTMLElement | null)?.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    const lastCall = prodActions.getSalesPlanDetails.mock.calls.at(-1)?.[0] as
      | { month?: string }
      | undefined
    expect(lastCall?.month).toBe('2026-10')
  })

  it('defaults both plan and sales months to the current month for a fresh session', async () => {
    await renderAndSettle()
    const current = dayjs().format('YYYY-MM')
    const planCall = prodActions.getPlans.mock.calls[0]?.[0] as
      | { month?: string }
      | undefined
    expect(planCall?.month).toBe(current)
    const salesCall = prodActions.getSalesPlanDetails.mock.calls[0]?.[0] as
      | { month?: string }
      | undefined
    expect(salesCall?.month).toBe(current)
  })

  it('restores the remembered plan month after a reload within the session', async () => {
    window.sessionStorage.setItem('dazah.production.plan-page.month', '2026-08')
    await renderAndSettle()
    const months = prodActions.getPlans.mock.calls.map(
      (c) => (c[0] as { month?: string }).month,
    )
    // 恢复后按记住的月份加载，且不先按当月发起多余请求
    expect(months.length).toBeGreaterThan(0)
    expect(months.every((m) => m === '2026-08')).toBe(true)
  })

  it('restores the remembered sales month after a reload within the session', async () => {
    window.sessionStorage.setItem(
      'dazah.production.plan-page.sales-month',
      '2026-07',
    )
    await renderAndSettle()
    const months = prodActions.getSalesPlanDetails.mock.calls.map(
      (c) => (c[0] as { month?: string }).month,
    )
    expect(months.length).toBeGreaterThan(0)
    expect(months.every((m) => m === '2026-07')).toBe(true)
  })

  it('keeps the cleared sales month (= 全部月份) across a reload', async () => {
    window.sessionStorage.setItem('dazah.production.plan-page.sales-month', '')
    await renderAndSettle()
    const months = prodActions.getSalesPlanDetails.mock.calls.map(
      (c) => (c[0] as { month?: string }).month,
    )
    expect(months.length).toBeGreaterThan(0)
    expect(months.every((m) => m === undefined)).toBe(true)
  })

  it('paginates to the second page when there are more than 20 rows', async () => {
    const rows = Array.from({ length: 25 }, (_, i) => ({
      id: `pl-${i + 1}`,
      workshop: '203车间',
      product_name: `产品${i + 1}`,
      plan_date: '2026-09-01',
      planned_yield: 100,
      unit: 'KG',
      actual_completion: 0,
      completion_rate: 0,
      safety_status: '无异常',
      quality_status: '无异常',
      remarks: '',
      source: 'feishu',
    }))
    prodActions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: rows,
      meta: { total: 25 },
    })
    await renderAndSettle()
    prodActions.getPlans.mockClear()
    const page2 = document.body.querySelector(
      '.ant-pagination-item-2',
    ) as HTMLElement | undefined
    expect(page2).toBeTruthy()
    await act(async () => {
      page2!.querySelector('a')?.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(prodActions.getPlans).toHaveBeenCalledTimes(1)
    const lastCall = prodActions.getPlans.mock.calls[0]?.[0] as
      | { page?: number }
      | undefined
    expect(lastCall?.page).toBe(2)
  })
})
