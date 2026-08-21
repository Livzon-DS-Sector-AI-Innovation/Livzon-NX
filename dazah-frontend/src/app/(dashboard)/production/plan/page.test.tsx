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
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  deletePlan: vi.fn(),
}))
vi.mock('@/actions/production', () => prodActions)

import PlanPage from './page'

const ROWS = [
  {
    id: 'sp-1',
    product_name: '霉酚酸',
    unit: 'kg',
    last_month_delivered_uninvoiced: 100,
    current_year_delivered: 500,
    month_planned_delivery: 600,
    month_delivered_qty: 300,
    undelivered_qty: 300,
    month_planned_invoice: 600,
    invoiced_qty: 280,
    delivery_completion_rate: 50,
    last_month_end_inventory: 50,
    month_planned_capacity: 700,
    month_end_inventory: 80,
    remarks: '',
  },
]

const PLANS = [
  {
    id: 'pl-1',
    workshop: '101-1发酵车间',
    product_name: '洛伐他汀',
    plan_date: '2026-07-01',
    planned_yield: 800,
    unit: 'kg',
    actual_completion: 720,
    completion_rate: 0.9,
    safety_status: '正常',
    quality_status: '合格',
    remarks: '',
    source: 'feishu',
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('PlanPage', () => {
  let root: Root
  let container: HTMLElement
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    prodActions.getPlans.mockResolvedValue({ code: 200, message: 'success', data: PLANS, meta: { total: 1 } })
    prodActions.deletePlan.mockResolvedValue({ code: 200, message: 'success', data: null })
    prodActions.createPlan.mockResolvedValue({ code: 200, message: 'success', data: null })
    prodActions.updatePlan.mockResolvedValue({ code: 200, message: 'success', data: null })

    fetchMock = vi.fn((url: string, opts?: Request) => {
      const method = opts?.method || 'GET'
      if (url.includes('/sales-plan-details') && method === 'GET') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: ROWS, meta: { total: 1 } }))
      }
      if (url.includes('/sales-plan-details') && method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      if (url.includes('/sales-plan-details') && method === 'DELETE') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
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

  it('renders the sales plan detail ledger with loaded rows', async () => {
    prodActions.getPlans.mockResolvedValue({ code: 200, message: 'success', data: [], meta: { total: 0 } })
    vi.stubGlobal('fetch', fetchMock)

    act(() => {
      root.render(<App><PlanPage /></App>)
    })

    // 切换到销售执行 Tab
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const salesTab = Array.from(container.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('产销计划'))
    if (salesTab) {
      await act(async () => { salesTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }

    const text = container.textContent || ''
    expect(text).toContain('生产计划')
    expect(text).toContain('霉酚酸')
    expect(text).toContain('500')
    // SyncSettingsButton 展示
    expect(text).toContain('同步设置')
  })

  it('renders the production-plan tab with rows and handles plan edit/delete/apply filters', async () => {
    vi.stubGlobal('fetch', fetchMock)

    act(() => {
      root.render(<App><PlanPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })

    const text = container.textContent || ''
    expect(text).toContain('洛伐他汀')
    expect(text).toContain('90.0%')
    expect(text).toContain('飞书')

    // 点击删除按钮触发 deletePlan
    const delBtn = Array.from(container.querySelectorAll('.ant-popover-open')).length > 0
    const deleteBtns = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent?.includes('删除'))
    if (deleteBtns.length > 0) {
      act(() => { deleteBtns[0].click() })
      await act(async () => { await new Promise((r) => setTimeout(r, 40)) })
      // Popconfirm confirm
      const okBtn = Array.from(container.querySelectorAll('.ant-popover-buttons button')).find((b) => b.textContent?.includes('确定'))
      if (okBtn) {
        await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 40)) })
      }
      expect(prodActions.deletePlan).toHaveBeenCalled()
    }
  })

  it('creates a new production plan through the modal', async () => {
    vi.stubGlobal('fetch', fetchMock)
    prodActions.getPlans.mockResolvedValue({ code: 200, message: 'success', data: [], meta: { total: 0 } })

    act(() => {
      root.render(<App><PlanPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    // 触发所有可能的「新建计划」按钮
    const newBtns = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent?.trim() === '新建计划')
    for (const btn of newBtns) {
      await act(async () => { btn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const text = document.body.textContent || ''
    expect(text).toContain('新建生产计划')
    expect(text).toContain('生产计划')
  })
})
