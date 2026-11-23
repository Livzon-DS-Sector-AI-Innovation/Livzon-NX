import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ActionRequestError } from '@/lib/server-action-result'

const actions = vi.hoisted(() => ({
  fetchEquipments: vi.fn(),
  fetchEquipmentStatistics: vi.fn(),
  fetchDepartments: vi.fn(),
}))

vi.mock('@/actions/equipment', () => actions)
// 台账页面本身另有测试；这里用占位组件暴露它拿到的 SSR 数据
vi.mock('@/components/equipment', () => ({
  EquipmentPage: (props: Record<string, unknown>) => (
    <section
      data-testid="equipment-page"
      data-workshop={String(props.workshopCode)}
      data-total={String(props.initialTotal)}
      data-items={(props.initialEquipments as unknown[]).length}
      data-first={(props.initialEquipments as Array<{ id: string }>)[0]?.id ?? ''}
      data-categories={(props.initialCategories as unknown[]).length}
      data-departments={(props.initialDepartments as unknown[]).length}
      data-stats={JSON.stringify(props.initialStatistics)}
    />
  ),
}))
vi.mock('@/components/equipment/EquipmentQueryFailure', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/equipment/EquipmentQueryFailure')>()
  return {
    ...actual,
    EquipmentQueryFailure: ({ status }: { status: number }) => (
      <section data-testid="query-failure">{status}</section>
    ),
  }
})
vi.mock('@/components/equipment/inspection/FeishuInspectionPage', () => ({
  FeishuInspectionPage: ({ workshopCode, workshopLabel }: { workshopCode: string; workshopLabel: string }) => (
    <div data-testid="feishu-inspection" data-workshop={workshopCode} data-label={workshopLabel} />
  ),
}))
vi.mock('@/components/equipment/repair/RepairLedgerPage', () => ({
  RepairLedgerPage: ({ workshopCode, workshopLabel }: { workshopCode: string; workshopLabel: string }) => (
    <div data-testid="repair-ledger" data-workshop={workshopCode} data-label={workshopLabel} />
  ),
}))

import AssetsView from './assets-view'
import InspectionView from './inspection-view'
import RepairView from './repair-view'

const render = async (element: Promise<ReactElement> | ReactElement) =>
  renderToStaticMarkup(await element)

const ok = (data: unknown) => ({ code: 200, data })

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AssetsView（台账 SSR 预取）', () => {
  it('hands the fetched ledger, statistics and departments to the ledger page', async () => {
    const items = [{ id: 'e-1' }, { id: 'e-2' }]
    const statistics = { total: 2, by_status: { 在用: 2 }, by_category: {}, by_location: {} }
    actions.fetchEquipments.mockResolvedValue(ok({ items, total: 2 }))
    actions.fetchEquipmentStatistics.mockResolvedValue(ok(statistics))
    actions.fetchDepartments.mockResolvedValue([{ id: 'd-1' }])

    const html = await render(AssetsView({ workshopCode: '101-1' }))

    expect(actions.fetchEquipments).toHaveBeenCalledWith({ workshop: '101-1', page: 1, page_size: 20 })
    expect(actions.fetchEquipmentStatistics).toHaveBeenCalledWith('101-1')
    expect(html).toContain('data-testid="equipment-page" data-workshop="101-1" data-total="2" data-items="2" data-first="e-1"')
    expect(html).toContain('data-categories="0" data-departments="1"')
    expect(html).toContain(`data-stats="${JSON.stringify(statistics).replaceAll('"', '&quot;')}"`)
  })

  it('shows the access-denied state when a fetch is rejected with 401 or 403', async () => {
    actions.fetchEquipments.mockRejectedValue(new ActionRequestError(403, '无权查询该车间'))
    actions.fetchEquipmentStatistics.mockResolvedValue(ok({ total: 0 }))
    actions.fetchDepartments.mockResolvedValue([])
    expect(await render(AssetsView({ workshopCode: '203' }))).toContain('data-testid="query-failure">403')

    actions.fetchEquipments.mockResolvedValue(ok({ items: [], total: 0 }))
    actions.fetchEquipmentStatistics.mockRejectedValue(new ActionRequestError(401, '登录已过期'))
    expect(await render(AssetsView({ workshopCode: '203' }))).toContain('data-testid="query-failure">401')
  })

  it('degrades to empty data on server errors and failed optional requests', async () => {
    actions.fetchEquipments.mockRejectedValue(new ActionRequestError(500, 'boom'))
    actions.fetchEquipmentStatistics.mockRejectedValue(new Error('offline'))
    actions.fetchDepartments.mockRejectedValue(new Error('offline'))

    const html = await render(AssetsView({ workshopCode: '201-1' }))

    expect(html).toContain('data-total="0" data-items="0" data-first=""')
    expect(html).toContain('data-departments="0"')
    expect(html).toContain('&quot;total&quot;:0')
    expect(html).not.toContain('query-failure')
  })
})

describe('inspection / repair 模块视图', () => {
  it('pass the workshop through to their client pages', async () => {
    const inspection = await render(InspectionView({ workshopCode: '101-1', workshopLabel: '101一车间' }))
    expect(inspection).toContain('data-testid="feishu-inspection" data-workshop="101-1" data-label="101一车间"')

    const repair = await render(RepairView({ workshopCode: '201-3', workshopLabel: '201三车间' }))
    expect(repair).toContain('data-testid="repair-ledger" data-workshop="201-3" data-label="201三车间"')
  })
})
