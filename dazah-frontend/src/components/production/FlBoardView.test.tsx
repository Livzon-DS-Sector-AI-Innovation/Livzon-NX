/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFlBoard: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

vi.mock('./SyncSettingsButton', () => ({
  default: ({ onSync }: { onSync?: () => void }) =>
    createElement(
      'button',
      { 'data-testid': 'fl-sync-button', onClick: onSync },
      '同步设置',
    ),
}))

const perms = vi.hoisted(() => ({
  state: { canSync: true, canOperate: true, canDelete: true },
  useProductionPermissions: () => perms.state,
  PRODUCTION_PAGE_KEYS: { overview: 'production:overview' },
}))

vi.mock('./useProductionPermissions', async (importOriginal) => {
  const original = await importOriginal<typeof import('./useProductionPermissions')>()
  return {
    ...original,
    useProductionPermissions: () => perms.state,
  }
})

import FlBoardView from './FlBoardView'
import type { FlBoard, FlBoardBatch } from '@/types/production'

function batch(overrides: Partial<FlBoardBatch> = {}): FlBoardBatch {
  return {
    batch_no: 'FL-2609001',
    seq: 1,
    order_date: '2026-09-19',
    pick_date: '2026-09-20',
    charge_date: '2026-09-20',
    charge_time: '8:00~10:00',
    mix_date: '2026-09-20',
    mix_time: '10:00~12:00',
    spec: '10kg/袋、2袋/箱',
    pack_date: '2026-09-20',
    pack_time: '14:00~16:00',
    inspection_date: '2026-09-20',
    planned_inbound_date: '2026-09-20',
    actual_inbound_date: '2026-09-20',
    stage_key: 'inbound',
    stage_label: '入库',
    state: 'inbound',
    state_label: '已入库',
    source_table: '9月排产',
    pack_weight_kg: 1980,
    ...overrides,
  }
}

function board(overrides: Partial<FlBoard> = {}): FlBoard {
  const confirmed = [
    batch(),
    batch({
      batch_no: 'FL-2609002',
      seq: 2,
      order_date: '2026-09-20',
      charge_date: '2026-09-21',
      pack_date: '2026-09-21',
      inspection_date: '2026-09-21',
      planned_inbound_date: '2026-09-21',
      actual_inbound_date: '2026-09-21',
    }),
  ]
  return {
    month: '2026-09',
    batch_prefix: 'FL-2609',
    is_current_month: true,
    period: {
      start: '2026-08-27',
      end: '2026-09-26',
      label: '8月27日～9月26日',
    },
    planned_kg: 7000,
    planned_batches: 6,
    inbound_batches: 4,
    inbound_kg: 7920,
    completion_rate: 113.14,
    in_progress_count: 2,
    progress: {
      by_batches: { inbound: 2, in_progress: 2, not_started: 2 },
      by_kg: { completed_kg: 7920, planned_kg: 7000 },
    },
    flow: [
      batch({
        batch_no: 'FL-2609003',
        seq: 3,
        order_date: '2026-09-02',
        charge_date: '2026-09-03',
        planned_inbound_date: '2026-09-03',
        actual_inbound_date: null,
        stage_key: 'inbound',
        stage_label: '入库',
        state: 'confirm_pending',
        state_label: '待入库确认',
        elapsed_days: 19,
      }),
      batch({
        batch_no: 'FL-2609005',
        seq: 5,
        order_date: '2026-09-21',
        charge_date: '2026-09-22',
        planned_inbound_date: '2026-09-23',
        actual_inbound_date: null,
        stage_key: 'charge',
        stage_label: '投料',
        state: 'running',
        state_label: '在制',
        elapsed_days: 0,
      }),
      batch({
        batch_no: 'FL-2609006',
        seq: 6,
        order_date: '2026-09-23',
        charge_date: '2026-09-24',
        planned_inbound_date: '2026-09-24',
        actual_inbound_date: null,
        stage_key: 'order',
        stage_label: '指令',
        state: 'upcoming',
        state_label: '待投料',
      }),
    ],
    month_batches: confirmed,
    recent_completed: confirmed,
    generated_at: '2026-09-22T08:53:00',
    ...overrides,
  }
}

describe('FlBoardView', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function render(props: { month?: string; refreshKey?: number } = {}) {
    act(() => {
      root.render(
        <App>
          <FlBoardView month={props.month ?? '2026-09'} refreshKey={props.refreshKey ?? 0} />
        </App>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  it('renders KPI cards, arrow progress bar and five-state flow table', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: board(),
    })
    await render()
    const text = container.textContent || ''
    expect(actions.getFlBoard).toHaveBeenCalledWith('2026-09')
    expect(text).toContain('本月计划产量')
    expect(text).toContain('7,000 kg')
    expect(text).toContain('计划批次')
    expect(text).toContain('本月入库批次')
    expect(text).toContain('7,920 kg')
    expect(text).toContain('113.14%')
    expect(text).toContain('在制批次')
    expect(text).not.toContain('平均生产周期')
    // 工序流转五态：待入库确认/在制/待投料 均展示（已历时列已删除）
    expect(text).toContain('待入库确认')
    expect(text).toContain('在制')
    expect(text).toContain('待投料')
    expect(text).not.toContain('已历时')
    // 箭头进度条复用发酵组件：轨道存在，图例为 FL 文案且不含「待出产量」
    expect(container.querySelector('[data-testid="batch-progress-track"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="batch-progress-arrow"]')).toBeTruthy()
    expect(text).toContain('已入库')
    expect(text).toContain('未投料')
    expect(text).not.toContain('待出产量')
    // 批次明细（已确认）与最近完成
    expect(text).toContain('2026-09 批次明细')
    expect(text).toContain('规格重量(kg)')
    expect(text).toContain('最近完成批次')
  })

  it('shows the source-mark tooltip trigger on card titles', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: board(),
    })
    await render()
    const marks = container.querySelectorAll('[data-testid="fl-source-mark"]')
    // 六张 KPI 卡 + 进度 + 流转 + 明细 + 最近完成
    expect(marks.length).toBeGreaterThanOrEqual(10)
    const text = container.textContent || ''
    expect(text).toContain('卡片标题 * 悬停查看数据来源')
  })

  it('shows the empty sync hint when no batches are synced', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: board({
        planned_kg: null,
        planned_batches: 0,
        inbound_batches: 0,
        inbound_kg: null,
        completion_rate: null,
        in_progress_count: 0,
        progress: {
          by_batches: { inbound: 0, in_progress: 0, not_started: 0 },
          by_kg: { completed_kg: null, planned_kg: null },
        },
        flow: [],
        month_batches: [],
        recent_completed: [],
      }),
    })
    await render()
    const text = container.textContent || ''
    expect(text).toContain('尚未同步到批次数据')
    expect(text).toContain('同步设置')
    expect(text).not.toContain('工序流转实时状态')
  })

  it('shows the load failure alert', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 500,
      message: '看板数据加载失败',
      data: null,
    })
    await render()
    const text = container.textContent || ''
    expect(text).toContain('看板数据加载失败')
  })

  it('reloads when refreshKey changes', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: board(),
    })
    await render({ refreshKey: 0 })
    expect(actions.getFlBoard).toHaveBeenCalledTimes(1)
    await render({ refreshKey: 1 })
    expect(actions.getFlBoard).toHaveBeenCalledTimes(2)
  })
})
