/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
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
  getPlans: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
}))

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option?: unknown }) =>
    createElement('pre', null, JSON.stringify(option ?? {})),
}))


// 认证 store：默认管理员（通配权限），工段矩阵用例直接改 state.user.permissions
const authStore = vi.hoisted(() => {
  const state = {
    user: {
      id: 'u-test',
      name: '测试用户',
      permissions: ['*'] as string[],
    },
  }
  return {
    state,
    useAuthStore: (selector: (s: typeof state) => unknown) => selector(state),
  }
})
vi.mock('@/stores/auth', () => authStore)

import ProductionHomePage from './page'

const BOARD = {
  now: '2026-09-08T12:00:00',
  period: { start: '2026-08-27', end: '2026-09-26', label: '8月27日～9月26日' },
  is_current_period: true,
  month_planned_capacity_kg: 930000,
  extract_finished_inbound_kg: null,
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
      extract_kg: 88.0,
      batch_yield_rate: null,
      yield_rate: null,
      result: '计划放罐',
    },
  ],
  trend: null,
  dumped_batches: [
    { batch_no: 'FA26231', dump_date: '2026-09-08' },
    { batch_no: 'FA26230', dump_date: '2026-09-07' },
  ],
  extraction_ledger: [
    {
      batch_no: 'FA26233',
      dump_date: '2026-09-10',
      yield_kg: 32569.5,
      extract_kg: null,
    },
    {
      batch_no: 'FA26232',
      dump_date: '2026-09-09',
      yield_kg: 31058.32,
      extract_kg: 28100,
    },
  ],
  extraction: {
    ferment_total_kg: 298531.0,
    extract_total_kg: 265000.0,
    ferment_batches: 9,
    extract_batches: 8,
    rate_realtime: 88.8,
    rate_paired: 90.2,
  },
  alerts: [
    { level: 'info', text: '待接种批次 FA26235 今日 20:00 进种子罐（202A）' },
  ],
  maintenance: [],
}

describe('ProductionHomePage (fermentation board)', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    authStore.state.user.permissions = ['*']
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: BOARD,
    })
    // 生产计划默认无数据：提炼计划产量卡显示"待更新"占位
    actions.getPlans.mockResolvedValue({
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
    window.localStorage.clear()
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
    expect(text).toContain('103-1车间L-苯丙氨酸生产看板')
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
    expect(text).toContain('298,531.00 kg')
    // 产能达成率 = 已完成产能 / 计划产能（298531/930000 ≈ 32.1%），在右栏产能值下方
    expect(text).toContain('产能达成率 32.10%')
    expect(text).not.toContain('（298,531.00 kg/930,000 kg）')
    expect(text).not.toContain('染菌数｜染菌率')
    // 理论批次卡：一天一批，截至今天（随运行日期浮动）、已完成÷理论=设备利用率
    expect(text).toContain('理论批次')
    expect(text).toContain('设备利用率')
    expect(text).toMatch(/截至 \d{2}-\d{2} · 一天一批/)
    expect(text).toContain('已完成 10 ÷ 理论')
    expect(text).toMatch(/设备利用率\s*\n?\s*\d+(\.\d+)?%/)
    expect(text).not.toContain('当前运行批次')
    expect(text).not.toContain('待启动排产批次')
    // 本月批次进度条：产能口径（绿色段=已完成产能/计划产能），汇总行已删除
    expect(text).toContain('本月批次进度')
    expect(text).not.toContain('已放罐 10/31')
    expect(text).toContain('已完成 9 批｜298,531.00 kg')
    expect(text).toContain('待出产量 1 批')
    expect(text).toContain('未开始 19 批')
    // 右侧计划产能：未设置显示 --，有设置显示 kg
    expect(text).toContain('本月计划产能')
    expect(container.textContent || '').toContain('--')
    // 箭头位置 = 产能进度点 298531/930000 ≈ 32.1%
    const arrow = container.querySelector('.relative .absolute[style*="left: 32"]')
    expect(arrow).toBeTruthy()
    // 进度条粒子脉冲层（Canvas）随进度条渲染
    expect(container.querySelectorAll('[data-testid="progress-particles"]').length).toBe(1)
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
          tank_no: '303A',
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
    // 抽屉表含罐号列
    expect(drawerText).toContain('罐号')
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
    expect(text).toContain('930,000 kg')
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

  it('renders the per-batch output chart with average line', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        trend: { batches: ['FA26229', 'FA26230'], outputs: [31000, 30500] },
      },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('FA26229')
    expect(text).toContain('平均产量 30750.0 kg')
  })

  async function openHistoryDrawer() {
    const historyBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('历史数据'),
    ) as HTMLElement
    await act(async () => {
      historyBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
  }

  function modalOkBtn(): HTMLElement {
    const btn = Array.from(
      document.body.querySelectorAll('.ant-modal-footer button'),
    ).find((b) => b.classList.contains('ant-btn-primary')) as HTMLElement | undefined
    expect(btn).toBeTruthy()
    return btn!
  }

  function modalCancelBtn(): HTMLElement {
    const btn = Array.from(
      document.body.querySelectorAll('.ant-modal-footer button'),
    ).find((b) => (b.textContent || '').replace(/\s/g, '') === '取消') as HTMLElement | undefined
    expect(btn).toBeTruthy()
    return btn!
  }

  it('records a batch actual from the dumped list and refreshes', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({ code: 200, data: [] })
    actions.upsertFermentationBatchActual.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await render()
    await openHistoryDrawer()
    const addBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent?.includes('录入批次产量'),
    ) as HTMLElement
    await act(async () => {
      addBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 未选批次时先提示且不提交
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actions.upsertFermentationBatchActual).not.toHaveBeenCalled()
    expect(document.body.textContent || '').toContain('请填写批次号')
    // 选择已放罐批次（自动带出计划放罐日期）后保存
    const selector = document.body.querySelector('.ant-modal .ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (o) => o.textContent?.includes('FA26230'),
    ) as HTMLElement
    await act(async () => {
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.upsertFermentationBatchActual).toHaveBeenCalledWith({
      batch_no: 'FA26230',
      dump_date: '2026-09-07',
      yield_kg: null,
      remark: null,
    })
    expect(document.body.textContent || '').toContain('已保存批次产量')
  })

  it('edits an existing batch actual', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({
      code: 200,
      data: [
        { id: 'a-1', batch_no: 'FA26231', dump_date: '2026-09-08', yield_kg: 100, remark: '染菌批' },
      ],
    })
    actions.upsertFermentationBatchActual.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await render()
    await openHistoryDrawer()
    const editBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent === '编辑',
    ) as HTMLElement
    await act(async () => {
      editBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('编辑批次产量：FA26231')
    // 修改放罐产量与备注
    const yieldInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find(
      (i) => (i as HTMLInputElement).placeholder?.includes('放罐产量'),
    ) as HTMLInputElement
    const textarea = document.body.querySelector('.ant-modal textarea') as HTMLTextAreaElement
    await act(async () => {
      const inputSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set
      inputSetter?.call(yieldInput, '105')
      yieldInput.dispatchEvent(new Event('input', { bubbles: true }))
      const textSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set
      textSetter?.call(textarea, '复检合格')
      textarea.dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.upsertFermentationBatchActual).toHaveBeenCalledWith(
      expect.objectContaining({ batch_no: 'FA26231', yield_kg: 105, remark: '复检合格' }),
    )
  })

  it('deletes a batch actual after confirmation', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({
      code: 200,
      data: [
        { id: 'a-1', batch_no: 'FA26231', dump_date: '2026-09-08', yield_kg: 100, remark: null },
      ],
    })
    actions.deleteFermentationBatchActual.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await render()
    await openHistoryDrawer()
    const delBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent === '删除',
    ) as HTMLElement
    await act(async () => {
      delBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const confirmBtn = Array.from(
      document.body.querySelectorAll('.ant-popover button, .ant-popconfirm button'),
    ).find((b) => (b.textContent || '').replace(/\s/g, '') === '删除') as HTMLElement
    expect(confirmBtn).toBeTruthy()
    await act(async () => {
      confirmBtn.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.deleteFermentationBatchActual).toHaveBeenCalledWith('a-1')
    expect(document.body.textContent || '').toContain('已删除批次产量记录')
  })

  it('shows error hints when the actuals list fails', async () => {
    actions.getFermentationBatchActuals
      .mockResolvedValueOnce({ code: 500, message: '服务不可用' })
      .mockRejectedValueOnce(new Error('network down'))
    await render()
    const historyBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('历史数据'),
    ) as HTMLElement
    await act(async () => {
      historyBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 非 200：展示后端 message
    expect(document.body.textContent || '').toContain('服务不可用')
    // 再次打开：请求直接抛错走兜底提示
    await act(async () => {
      historyBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('历史数据加载失败')
    expect(actions.getFermentationBatchActuals).toHaveBeenCalledTimes(2)
  })

  it('shows backend messages when save or delete fails', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({
      code: 200,
      data: [
        { id: 'a-2', batch_no: 'FA26230', dump_date: '2026-09-07', yield_kg: 200, remark: null },
      ],
    })
    actions.upsertFermentationBatchActual.mockResolvedValue({
      code: 500,
      message: '批次号不存在',
    })
    actions.deleteFermentationBatchActual.mockResolvedValue({
      code: 500,
      message: '记录已被删除',
    })
    await render()
    await openHistoryDrawer()
    const addBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent?.includes('录入批次产量'),
    ) as HTMLElement
    await act(async () => {
      addBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const selector = document.body.querySelector('.ant-modal .ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (o) => o.textContent?.includes('FA26231'),
    ) as HTMLElement
    await act(async () => {
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(document.body.textContent || '').toContain('批次号不存在')
    // 取消录入弹窗后，从列表删除走失败分支
    await act(async () => {
      modalCancelBtn().click()
      await new Promise((r) => setTimeout(r, 250))
    })
    const delBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent === '删除',
    ) as HTMLElement
    expect(delBtn).toBeTruthy()
    await act(async () => {
      delBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const confirmBtn = Array.from(
      document.body.querySelectorAll('.ant-popover button, .ant-popconfirm button'),
    ).find((b) => (b.textContent || '').replace(/\s/g, '') === '删除') as HTMLElement
    expect(confirmBtn).toBeTruthy()
    await act(async () => {
      confirmBtn.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.deleteFermentationBatchActual).toHaveBeenCalledWith('a-2')
    expect(document.body.textContent || '').toContain('记录已被删除')
  })

  it('shows an error when the capacity save fails', async () => {
    actions.setFermentationMonthCapacity.mockResolvedValue({
      code: 500,
      message: '排产表未覆盖当前日期',
    })
    await render()
    const editBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.getAttribute('title') === '设置本月计划产能',
    ) as HTMLElement
    await act(async () => {
      editBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(document.body.textContent || '').toContain('排产表未覆盖当前日期')
  })

  it('falls back to empty plan rows when the plan fetch fails', async () => {
    actions.getPlans.mockRejectedValue(new Error('plan service down'))
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('月生产计划待更新')
  })

  it('persists the selected plan row per month into local storage', async () => {
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'pl-1',
          workshop: '203车间',
          product_name: 'L-苯丙氨酸',
          plan_date: '2026-09-01',
          planned_yield: 100,
          unit: 'KG',
          actual_completion: 0,
          completion_rate: 0,
          safety_status: '',
          quality_status: '',
          remarks: '',
          source: 'feishu',
        },
        {
          id: 'pl-2',
          workshop: '203车间',
          product_name: '甲瓦',
          plan_date: '2026-09-01',
          planned_yield: 200,
          unit: 'KG',
          actual_completion: 0,
          completion_rate: 0,
          safety_status: '',
          quality_status: '',
          remarks: '',
          source: 'feishu',
        },
      ],
    })
    await render()
    // antd v6：选择面为 .ant-select-content，对 Select 根元素派发 mousedown 打开
    const trigger = container.querySelector('.plan-product-select') as HTMLElement
    expect(trigger).toBeTruthy()
    await act(async () => {
      trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const dropdown = document.body.querySelector(
      '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
    ) as HTMLElement
    expect(dropdown).toBeTruthy()
    const option = Array.from(
      dropdown.querySelectorAll('.ant-select-item-option'),
    ).find((o) => o.textContent?.includes('甲瓦')) as HTMLElement
    expect(option).toBeTruthy()
    await act(async () => {
      option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const raw = window.localStorage.getItem('dazah.production.plan-card.selection')
    expect(raw).toBeTruthy()
    const store = JSON.parse(raw || '{}') as Record<string, string>
    const values = Object.values(store)
    expect(values).toContain('203车间|甲瓦')
  })

  it('picks a dump date manually in the actual modal', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({ code: 200, data: [] })
    actions.upsertFermentationBatchActual.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await render()
    await openHistoryDrawer()
    const addBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent?.includes('录入批次产量'),
    ) as HTMLElement
    await act(async () => {
      addBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const selector = document.body.querySelector('.ant-modal .ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 120))
    })
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (o) => o.textContent?.includes('FA26230'),
    ) as HTMLElement
    await act(async () => {
      option.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 手动打开放罐日期面板并改选 9 日
    const dateInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find(
      (i) => (i as HTMLInputElement).placeholder?.includes('放罐日期'),
    ) as HTMLElement
    // antd：mousedown 需落在 .ant-picker 根元素上才会打开面板
    const pickerRoot = dateInput.closest('.ant-picker') as HTMLElement
    expect(pickerRoot).toBeTruthy()
    await act(async () => {
      dateInput.focus()
      pickerRoot.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      pickerRoot.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const targetCell = Array.from(
      document.body.querySelectorAll('.ant-picker-cell'),
    ).find((c) => c.getAttribute('title') === '2026-09-09') as HTMLElement | undefined
    expect(targetCell).toBeTruthy()
    await act(async () => {
      ;(targetCell!.querySelector('.ant-picker-cell-inner') as HTMLElement | null)?.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      modalOkBtn().click()
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.upsertFermentationBatchActual).toHaveBeenCalledWith(
      expect.objectContaining({ dump_date: '2026-09-09' }),
    )
  })

  it('closes the drawer and modals without saving', async () => {
    actions.getFermentationBatchActuals.mockResolvedValue({ code: 200, data: [] })
    await render()
    await openHistoryDrawer()
    const addBtn = Array.from(document.body.querySelectorAll('.ant-drawer button')).find(
      (b) => b.textContent?.includes('录入批次产量'),
    ) as HTMLElement
    await act(async () => {
      addBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    await act(async () => {
      modalCancelBtn().click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 关闭抽屉
    const drawerClose = document.body.querySelector('.ant-drawer-close') as HTMLElement
    await act(async () => {
      drawerClose.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    // 产能弹窗：修改数值后取消，不应提交
    const capacityBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.getAttribute('title') === '设置本月计划产能',
    ) as HTMLElement
    await act(async () => {
      capacityBtn.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const capacityInput = Array.from(document.body.querySelectorAll('.ant-modal input')).find(
      (i) => (i as HTMLInputElement).placeholder?.includes('本月计划产能'),
    ) as HTMLInputElement
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(capacityInput, '950000')
      capacityInput.dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    await act(async () => {
      modalCancelBtn().click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(actions.setFermentationMonthCapacity).not.toHaveBeenCalled()
  })

  it('switches period via the month picker and reloads with a located date', async () => {
    await render()
    // 月份选择器：顶部标题栏（103-1车间L-苯丙氨酸生产看板 与 生产周期 标签之间）
    const pickerInput = Array.from(container.querySelectorAll('.ant-picker input')).find(
      (i) => i.closest('.ant-space')?.textContent?.includes('103-1车间L-苯丙氨酸生产看板'),
    ) as HTMLInputElement
    expect(pickerInput).toBeTruthy()
    await act(async () => {
      pickerInput.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      pickerInput.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    // 面板月份格按 Jan~Dec 顺序排列（测试环境无中文 locale），第 8 格 = 8 月
    const monthCells = Array.from(
      document.body.querySelectorAll('.ant-picker-dropdown .ant-picker-cell'),
    )
    expect(monthCells.length).toBeGreaterThanOrEqual(12)
    const augCell = monthCells[7] as HTMLElement
    const callsBefore = actions.getFermentationBoard.mock.calls.length
    await act(async () => {
      augCell.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    const call = actions.getFermentationBoard.mock.calls[callsBefore]
    expect(call?.[0]).toBe('2026-08-15')
  })

  it('renders a read-only view for a historical period', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        is_current_period: false,
        period: { start: '2026-07-27', end: '2026-08-26', label: '7月27日～8月26日' },
      },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 历史标记与标题
    expect(text).toContain('历史批次进度')
    expect(text).toContain('历史周期')
    expect(text).toContain('回到本月')
    // 写操作隐藏：产能编辑与检修按钮均不渲染
    expect(container.querySelector('button[title="设置本月计划产能"]')).toBeFalsy()
    expect(
      Array.from(container.querySelectorAll('button')).some((b) =>
        b.textContent?.includes('标记检修'),
      ),
    ).toBe(false)
  })

  it('hides the extraction card for fermentation-only role', async () => {
    authStore.state.user.permissions = ['production:fermentation-yield']
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { ...BOARD, extraction: null },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼计划产量')
    expect(text).toContain('本月计划批次')
    expect(text).toContain('发酵罐实时状态')
    expect(text).not.toContain('提炼已出成品')
    expect(text).not.toContain('提炼收率（实时）')
    // 收率分析占位对发酵岗可见（无敏感数据）
    expect(text).toContain('收率分析（待接入）')
    expect(text).not.toContain('批次台账')
    expect(text).not.toContain('成品日报')
  })

  it('shows only extraction summary for extraction-only role', async () => {
    authStore.state.user.permissions = ['production:extraction-yield']
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        kpis: null,
        tanks: [],
        recent: [],
        trend: null,
        month_planned_capacity_kg: null,
      },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼已出成品（仓储成品入库）')
    expect(text).toContain('数据源待接入')
    // 批次台账/饼状图/成品日报卡片已下线
    expect(text).not.toContain('批次台账')
    expect(text).not.toContain('成品日报')
    // 收率分析占位卡对提炼岗可见
    expect(text).toContain('收率分析（待接入）')
    // 发酵模块（KPI/罐状态/图表）对提炼岗不可见
    expect(text).not.toContain('本月计划批次')
    expect(text).not.toContain('发酵罐实时状态')
    expect(text).not.toContain('单批产量（最多 31 批）')
    expect(text).not.toContain('提炼计划产量')
    expect(text).not.toContain('提炼收率（实时）')
  })

  it('shows the full extraction trio for leadership (both permissions)', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼计划产量')
    expect(text).toContain('提炼已出成品')
    // 收率卡已改为占位，不再展示实时/配对口径数值
    expect(text).not.toContain('提炼收率（实时）')
    expect(text).not.toContain('88.8%')
    expect(text).toContain('收率分析（待接入）')
    // 最近完成批次表已移除提炼成品/单批收率列
    expect(text).not.toContain('提炼成品(kg)')
    expect(text).not.toContain('单批收率')
    // 批次台账/成品日报卡片已下线
    expect(text).not.toContain('批次台账')
    expect(text).not.toContain('成品日报')
  })

  it('shows warehouse inbound total when wired (FA product)', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { ...BOARD, extract_finished_inbound_kg: 410490 },
    })
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-rate',
          workshop: '203车间',
          product_name: 'L-苯丙氨酸',
          plan_date: '2026-09-01',
          planned_yield: 790000,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
      ],
      meta: { total: 1 },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼已出成品（仓储成品入库）')
    expect(text).toContain('410,490')
    expect(text).toContain('L-苯丙氨酸 · 本月合计(kg)')
    // 右栏完成率 = 410,490 ÷ 790,000，保留两位小数
    expect(text).toContain('完成率')
    expect(text).toContain('51.96%')
    expect(text).toContain('已出成品 ÷ 计划产量')
  })

  it('keeps placeholder text when warehouse inbound is not wired', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼已出成品（仓储成品入库）')
    expect(text).toContain('数据源待接入')
    // 已出成品或计划产量缺数据时完成率显示 --
    expect(text).toContain('完成率')
    expect(text).toContain('--')
  })

  it('shows plan yield with workshop-product picker when month plans exist', async () => {
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-1',
          workshop: '201-2车间',
          product_name: '霉酚酸',
          plan_date: '2026-09-01',
          planned_yield: 61000,
          unit: 'KG',
          actual_completion: 6920,
          completion_rate: 0.11,
          remarks: '',
          source: 'feishu',
        },
        {
          id: 'p-2',
          workshop: '101-2发酵车间',
          product_name: '霉酚酸',
          plan_date: '2026-09-01',
          planned_yield: 30,
          unit: '批',
          actual_completion: 7,
          completion_rate: 0.23,
          remarks: '',
          source: 'feishu',
        },
      ],
      meta: { total: 2 },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼计划产量')
    // 默认选中第一行（201-2车间 霉酚酸），显示其计划产量与单位
    expect(text).toContain('61,000')
    expect(text).toContain('KG · 9月计划')
    // 下拉选中值带车间+产品（渲染在 Select 文本中）
    expect(text).toContain('201-2车间 霉酚酸')
    // 月份查询参数随概览自然月
    expect(actions.getPlans).toHaveBeenCalledWith(
      expect.objectContaining({ month: expect.stringMatching(/^\d{4}-\d{2}$/) }),
    )
  })

  it('shows month-pending hint when no plans for the overview month', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('提炼计划产量')
    expect(text).toMatch(/\d+月生产计划待更新/)
    // 无计划数据时不显示"单位 · X月计划"取数文案（KPI 卡的"发酵本月计划产能"不受影响）
    expect(text).not.toContain('KG · ')
    expect(text).not.toContain('批 · ')
  })

  it('restores the remembered plan selection after reload', async () => {
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-1',
          workshop: '201-1车间',
          product_name: '洛伐他汀',
          plan_date: '2026-09-01',
          planned_yield: 45200,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
        {
          id: 'p-2',
          workshop: '203车间',
          product_name: 'L-苯丙氨酸',
          plan_date: '2026-09-01',
          planned_yield: 790000,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
      ],
      meta: { total: 2 },
    })
    // 预置本月记忆：上次选的是第二行（203车间 L-苯丙氨酸）
    const month = new Date().toISOString().slice(0, 7)
    window.localStorage.setItem(
      'dazah.production.plan-card.selection',
      JSON.stringify({ [month]: '203车间|L-苯丙氨酸' }),
    )
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 恢复记忆行而非默认第一行
    expect(text).toContain('790,000')
    expect(text).toContain('203车间 L-苯丙氨酸')
    expect(text).not.toContain('45,200')
  })
})
