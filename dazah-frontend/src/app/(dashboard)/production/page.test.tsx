/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFermentationBoard: vi.fn(),
  markTankMaintenance: vi.fn(),
  removeTankMaintenance: vi.fn(),
  uploadScheduleExcel: vi.fn(),
  getScheduleExcelArchives: vi.fn(),
  getScheduleExcelArchive: vi.fn(),
  deleteScheduleExcelArchive: vi.fn(),
  getFermentationBatchActuals: vi.fn(),
  upsertFermentationBatchActual: vi.fn(),
  deleteFermentationBatchActual: vi.fn(),
  setFermentationMonthCapacity: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
}))

import ProductionHomePage from './page'

const BOARD = {
  now: '2026-09-08T12:00:00',
  period: { start: '2026-08-27', end: '2026-09-26', label: '8月27日～9月26日' },
  month_planned_capacity_kg: 930000,
  kpis: {
    month_planned: 31,
    month_done_planned: 10,
    done_with_yield: 9,
    yield_pending: 1,
    month_done_yield_kg: 298531.0,
    running: 2,
    pending: 19,
    plan_capacity: null,
    contam_count: null,
    contam_rate: null,
    avg_yield_rate: null,
    utilization: null,
    avg_batch_yield: null,
    qualify_rate: null,
  },
  tanks: [
    {
      tank_no: '302A',
      status: 'running',
      batch_no: 'FA26234',
      inoculate_at: '2026-09-06T21:00:00',
      cultured_hours: 39,
      cycle_hours: 72,
      dump_at: '2026-09-09T10:00:00',
      note: '距放罐约 46h',
    },
    {
      tank_no: '303A',
      status: 'idle',
      batch_no: null,
      inoculate_at: null,
      cultured_hours: null,
      cycle_hours: 72,
      dump_at: null,
      note: '等待排产',
    },
    {
      tank_no: '304A',
      status: 'maintenance',
      batch_no: null,
      inoculate_at: null,
      cultured_hours: null,
      cycle_hours: 72,
      dump_at: null,
      note: '检修：滤芯更换',
    },
  ],
  recent: [
    {
      batch_no: 'FA26231',
      dump_date: '2026-09-06',
      tank_no: '303A',
      yield_kg: null,
      yield_rate: null,
      result: '计划放罐',
    },
  ],
  trend: null,
  dumped_batches: [
    { batch_no: 'FA26231', dump_date: '2026-09-08' },
    { batch_no: 'FA26230', dump_date: '2026-09-07' },
  ],
  alerts: [
    { level: 'info', text: '待接种批次 FA26235 今日 20:00 进种子罐（202A）' },
  ],
  maintenance: [],
}

describe('ProductionHomePage (fermentation board)', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: BOARD,
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

  async function render() {
    act(() => {
      root.render(<App><ProductionHomePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
  }

  it('renders the board header, kpis and tank table', async () => {
    await render()
    expect(actions.getFermentationBoard).toHaveBeenCalled()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('发酵车间生产实时看板')
    expect(text).toContain('生产周期 8月27日～9月26日')
    expect(text).toContain('本月计划批次')
    expect(text).toContain('31')
    expect(text).toContain('302A')
    expect(text).toContain('FA26234')
    expect(text).toContain('运行中')
    expect(text).toContain('检修维护')
    // KPI 精简：已完成卡两栏，右侧已完成产能；口径文字已删除
    expect(text).toContain('达成率 32%')
    expect(text).not.toContain('按计划放罐时间+2h口径')
    expect(text).toContain('已完成产能')
    expect(text).toContain('298.5 t')
    // 产能达成率 = 已完成产能 / 计划产能（298531/930000 ≈ 32.1%），在右栏产能值下方
    expect(text).toContain('产能达成率 32.1%')
    expect(text).not.toContain('（298.5 t/930.0 t）')
    expect(text).not.toContain('染菌数｜染菌率')
    expect(text).not.toContain('设备利用率')
    // 本月批次进度条：汇总与图例
    expect(text).toContain('本月批次进度')
    expect(text).toContain('已放罐 10/31（32%）｜运行中 2｜待出产量 1')
    expect(text).toContain('已完成 9 批')
    expect(text).toContain('未开始 19 批')
    // 右侧计划产能：未设置显示 --，有设置显示吨
    expect(text).toContain('本月计划产能')
    expect(container.textContent || '').toContain('--')
    // 箭头位置 = 已出产量 9/31 ≈ 29%（待出产量 1 批在箭头之后）
    const arrow = container.querySelector('.relative .absolute[style*="left: 29"]')
    expect(arrow).toBeTruthy()
    // 顶部保留历史数据入口
    const historyBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('历史数据'),
    )
    expect(historyBtn).toBeTruthy()
  })

  it('renders the production chart card and empty hint', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('单批产量（最多 31 批）')
    expect(text).toContain('暂无录入数据，请点击右上角「历史数据」录入批次产量')
  })

  it('opens the history drawer and lists batch actuals', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({
      code: 200,
      data: [
        {
          id: 'a-1',
          batch_no: 'FA26231',
          dump_date: '2026-09-08',
          yield_kg: 100,
          remark: '染菌批',
        },
      ],
    })
    await render()
    const historyBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('历史数据'),
    ) as HTMLElement
    await act(async () => {
      historyBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const drawerText = document.body.textContent || ''
    expect(drawerText).toContain('批次产量历史数据')
    expect(drawerText).toContain('FA26231')
    // 列表展示备注
    expect(drawerText).toContain('染菌批')
    const addBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent?.includes('录入批次产量'),
    ) as HTMLElement | undefined
    expect(addBtn).toBeTruthy()
    await act(async () => {
      addBtn!.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('录入批次产量')

    // 批号下拉：只列出未录入产量的已放罐批次
    const selector = document.body.querySelector('.ant-modal .ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const optionText = document.body.textContent || ''
    expect(optionText).toContain('FA26230（2026-09-07）')
    expect(optionText).not.toContain('FA26231（2026-09-08）')

    // 选中批次后自动带出计划放罐日期
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (o) => o.textContent?.includes('FA26230'),
    ) as HTMLElement
    await act(async () => {
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const inputValues = Array.from(document.querySelectorAll('.ant-modal input')).map(
      (i) => (i as HTMLInputElement).value,
    )
    expect(inputValues).toContain('2026-09-07')
  })

  it('renders recent planned batches and the alert ticker', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('最近完成批次')
    expect(text).toContain('FA26231')
    expect(text).toContain('待接种批次 FA26235')
  })

  function tankTableBatchCells(): string[] {
    const table = Array.from(document.body.querySelectorAll('table')).find((t) =>
      t.textContent?.includes('当前批次号'),
    )
    expect(table).toBeTruthy()
    return Array.from(table!.querySelectorAll('tbody tr')).map(
      (row) => row.querySelectorAll('td')[2]?.textContent ?? '',
    )
  }

  it('sorts tank rows by the batch number tail ascending', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        tanks: [
          {
            tank_no: '302A',
            status: 'running',
            batch_no: 'FA26234',
            inoculate_at: '2026-09-06T21:00:00',
            cultured_hours: 39,
            cycle_hours: 61,
            dump_at: '2026-09-11T10:00:00',
            note: '距放罐约 47h',
          },
          {
            tank_no: '303A',
            status: 'dumping',
            batch_no: 'FA26232',
            inoculate_at: '2026-09-06T21:00:00',
            cultured_hours: 61,
            cycle_hours: 61,
            dump_at: '2026-09-09T10:00:00',
            note: '放罐中（预计43min后结束）',
          },
          {
            tank_no: '304A',
            status: 'idle',
            batch_no: null,
            inoculate_at: null,
            cultured_hours: null,
            cycle_hours: null,
            dump_at: null,
            note: '等待排产',
          },
        ],
  recent: [
    {
      batch_no: 'FA26231',
      dump_date: '2026-09-08',
      tank_no: '303A',
      yield_kg: null,
      remark: null,
      yield_rate: null,
      result: '计划放罐',
    },
  ],
      },
    })
    await render()
    // 批次后三位升序：231（已放罐追加行）→ 232（放罐中）→ 234 → 无批号罐置末尾；
    // 放罐中的 FA26232 不再重复出现在已放罐行（后端放罐窗口+2h 口径保证）
    expect(tankTableBatchCells()).toEqual(['FA26231', 'FA26232', 'FA26234', '-'])
    // 已放罐行备注为固定完成话术
    const tankTable = Array.from(document.body.querySelectorAll('table')).find((t) =>
      t.textContent?.includes('当前批次号'),
    )
    expect(tankTable).toBeTruthy()
    expect(tankTable!.querySelector('tbody tr td:nth-child(8)')?.textContent).toBe(
      '该罐本批次放罐作业完成',
    )
  })

  it('shows the backend hint when no archive covers today', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '排产表未覆盖当前日期，请上传当前扎帐周期的排产 Excel',
      data: null,
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('排产表未覆盖当前日期')
  })

  it('keeps workshop entries at the bottom', async () => {
    await render()
    const text = container.textContent || ''
    expect(text).toContain('生产车间')
    expect(text).toContain('101一车间（菌种）')
    expect(text).toContain('201三车间 · 多拉菌素（DR）')
  })

  it('shows a load failure hint when the board request rejects', async () => {
    actions.getFermentationBoard.mockRejectedValue(new Error('network down'))
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('看板数据加载失败')
  })

  it('shows and edits the month planned capacity', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { ...BOARD, month_planned_capacity_kg: 930000 },
    })
    actions.setFermentationMonthCapacity.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('930.0 t')
    // 打开编辑弹窗并保存
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.getAttribute('title') === '设置本月计划产能',
    ) as HTMLElement
    expect(editBtn).toBeTruthy()
    await act(async () => {
      editBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const okBtn = Array.from(
      document.body.querySelectorAll('.ant-modal-footer button'),
    ).find((b) => b.classList.contains('ant-btn-primary')) as HTMLElement
    await act(async () => {
      okBtn.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.setFermentationMonthCapacity).toHaveBeenCalledWith(930000)
  })

  it('marks a tank under maintenance and refreshes the board', async () => {
    actions.markTankMaintenance.mockResolvedValue({ code: 200, message: 'success', data: null })
    await render()
    const markBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('标记检修')) as HTMLElement | undefined
    expect(markBtn).toBeTruthy()
    await act(async () => { markBtn!.click(); await new Promise((r) => setTimeout(r, 80)) })
    // 未填写原因时先提示且不提交
    const emptyOk = Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find((b) => b.classList.contains('ant-btn-primary')) as HTMLElement | undefined
    await act(async () => { emptyOk!.click(); await new Promise((r) => setTimeout(r, 80)) })
    expect(actions.markTankMaintenance).not.toHaveBeenCalled()
    const reasonInput = Array.from(document.body.querySelectorAll('input')).find((i) => (i as HTMLInputElement).placeholder?.includes('检修原因')) as HTMLInputElement | undefined
    expect(reasonInput).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
      setter?.call(reasonInput!, '滤芯更换')
      reasonInput!.dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find((b) => b.classList.contains('ant-btn-primary')) as HTMLElement | undefined
    await act(async () => { okBtn!.click(); await new Promise((r) => setTimeout(r, 200)) })
    expect(actions.markTankMaintenance).toHaveBeenCalledWith('302A', '滤芯更换')
    expect(actions.getFermentationBoard).toHaveBeenCalledTimes(2)
    expect(document.body.textContent || '').toContain('302A 已标记检修')
  })

  it('releases a maintenance tank and refreshes the board', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        maintenance: [{ id: 'm-1', tank_no: '304A', reason: '滤芯更换', started_at: '2026-09-08T08:00:00' }],
      },
    })
    actions.removeTankMaintenance.mockResolvedValue({ code: 200, message: 'success', data: null })
    await render()
    const releaseBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('解除检修')) as HTMLElement | undefined
    expect(releaseBtn).toBeTruthy()
    await act(async () => { releaseBtn!.click(); await new Promise((r) => setTimeout(r, 200)) })
    expect(actions.removeTankMaintenance).toHaveBeenCalledWith('m-1')
    expect(actions.getFermentationBoard).toHaveBeenCalledTimes(2)
    expect(document.body.textContent || '').toContain('304A 已解除检修')
  })
})
