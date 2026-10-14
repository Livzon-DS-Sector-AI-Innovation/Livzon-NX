/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { AntdProvider } from '@/components/AntdProvider'
import { setAppearance } from '@/lib/useAppearance'
import { StatsDashboard } from './StatsDashboard'

it('preserves actual status and category counts across appearances, including the empty state', async () => {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  const data: React.ComponentProps<typeof StatsDashboard>['initialData'] = {
    equipmentStats: { total: 12, by_status: { 在用: 10, 维修中: 2, 备用: 0, 停用: 0, 报废: 0 }, by_category: { 反应釜: 6, 干燥机: 6 }, by_location: {} },
    workOrderStats: null, stockWarnings: [], overduePlans: [], calibrationPlans: [], recentWorkOrders: [], inspectionSummaries: [],
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
