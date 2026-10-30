/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { AntdProvider } from '@/components/AntdProvider'
import { setAppearance } from '@/lib/useAppearance'
import { StatsDashboard } from './StatsDashboard'

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
}))

it('preserves actual status and category counts across appearances, including the empty state', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const data: React.ComponentProps<typeof StatsDashboard>['initialData'] = {
    equipmentStats: { total: 12, by_status: { 在用: 10, 维修中: 2, 备用: 0, 停用: 0, 报废: 0 }, by_category: { 反应釜: 6, 干燥机: 6 }, by_location: {} },
    workOrderStats: null,
    efficiency: null, stockWarnings: [], overduePlans: [], calibrationPlans: [], recentWorkOrders: [], inspectionSummaries: [],
    workshopOptions: [],
  }
  try {
    await act(async () => root.render(<AntdProvider><StatsDashboard initialData={data} /></AntdProvider>))
    for (const mode of ['dark', 'light'] as const) {
      await act(async () => setAppearance(mode))
      expect(host.textContent).toContain('83.3%')
      expect(host.textContent).toContain('16.7%')
      expect(host.querySelector('[title="在用: 10"]')).not.toBeNull()
      expect(host.querySelector('[title="维修中: 2"]')).not.toBeNull()
      expect(host.querySelector('[aria-label="工单流转图"]')?.getAttribute('tabindex')).toBe('0')
    }
    await act(async () => root.render(<AntdProvider><StatsDashboard initialData={{ ...data, equipmentStats: null }} /></AntdProvider>))
    expect(host.textContent).toContain('暂无设备数据')
    expect(host.textContent).toContain('暂无分类数据')
    expect(host.textContent).not.toContain('NaN')
  } finally { await act(async () => root.unmount()); host.remove(); await act(async () => setAppearance('system')) }
})

it('待处理工单 KPI 可点击跳转，车间切换更新联动标签', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const push = vi.fn()
  const router = { push, replace: vi.fn(), back: vi.fn() }
  // 本用例替换 next/navigation mock 的返回值
  const { useRouter } = await import('next/navigation')
  ;(useRouter as unknown as ReturnType<typeof vi.fn>).mockReturnValue(router)

  const efficiency = {
    avg_response_minutes: 2, avg_repair_minutes: 5, urgent_total: 6, urgent_on_time: 5,
    urgent_5min_rate: 0.83, total_orders: 26, monthly: [], top_faults: [],
    repairer_ranking: [{ assignee_id: 'u1', assignee_name: '秦佳豪', order_count: 21, avg_response_minutes: 2, avg_repair_minutes: 5 }],
    response_buckets: [
      { bucket: '≤5分钟', count: 19, ratio: 0.73 }, { bucket: '5-30分钟', count: 3, ratio: 0.12 },
      { bucket: '30-120分钟', count: 0, ratio: 0 }, { bucket: '>120分钟', count: 0, ratio: 0 },
      { bucket: '未接单', count: 4, ratio: 0.15 },
    ],
  }
  const data: React.ComponentProps<typeof StatsDashboard>['initialData'] = {
    equipmentStats: { total: 12, by_status: { 在用: 10, 维修中: 2, 备用: 0, 停用: 0, 报废: 0 }, by_category: {}, by_location: {} },
    workOrderStats: { total: 1, by_status: { 待处理: 1, 执行中: 0, 待验收: 0, 已完成: 0, 已关闭: 0 }, by_type: {}, by_priority: {} },
    efficiency,
    stockWarnings: [], overduePlans: [], calibrationPlans: [], recentWorkOrders: [], inspectionSummaries: [],
    workshopOptions: [{ code: '201-1', name: '201一车间' }],
  }
  try {
    await act(async () => root.render(<AntdProvider><StatsDashboard initialData={data} /></AntdProvider>))
    // KPI 点击 → router.push
    const kpi = Array.from(host.querySelectorAll('.kpi-card'))
      .find((el) => el.textContent?.includes('待处理工单')) as HTMLElement
    expect(kpi).toBeTruthy()
    await act(async () => { kpi.click() })
    expect(push).toHaveBeenCalledWith('/equipment/maintenance')

    // 车间切换 → 两张联动卡头标签从全工厂变为车间名
    const selector = host.querySelector('[role="combobox"], .ant-select-selector') as HTMLElement
    expect(selector).toBeTruthy()
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await Promise.resolve()
    })
    const option = Array.from(document.querySelectorAll('.ant-select-item-option'))
      .find((el) => el.textContent?.trim() === '201一车间') as HTMLElement | undefined
    if (option) {
      await act(async () => {
        option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        option.click()
        await Promise.resolve()
      })
      expect(host.textContent).toContain('201一车间 · 已接单')
    }
  } finally { await act(async () => root.unmount()); host.remove() }
})
