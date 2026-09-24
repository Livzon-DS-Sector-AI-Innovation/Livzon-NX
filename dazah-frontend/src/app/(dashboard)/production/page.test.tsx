/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFermentationBoard: vi.fn(),
  getFlBoard: vi.fn(),
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
  getProductionSummary: vi.fn(),
  getSalesPlanDetails: vi.fn(),
  getProductionLineStatus: vi.fn(),
  setProductionLineStatus: vi.fn(),
  getLineHaltEvents: vi.fn(),
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


// 认证 store：默认管理员；工段矩阵使用页面实际数据范围。
const authStore = vi.hoisted(() => {
  const state = {
    user: {
      id: 'u-test',
      name: '测试用户',
      role: 'admin' as string,
      permissions: ['*'] as string[],
      page_permissions: [] as Array<{ page_key: string; permissions: Array<'access' | 'query' | 'operate'>; data_scope: { scope_type: string } }>,
    },
  }
  return {
    state,
    useAuthStore: (selector: (s: typeof state) => unknown) => selector(state),
  }
})
vi.mock('@/stores/auth', () => authStore)

import ProductionHomePage from './page'
import { useProductContextStore } from '@/stores/product-context'

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
    authStore.state.user.role = 'admin'
    authStore.state.user.permissions = ['*']
    authStore.state.user.page_permissions = []
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: BOARD,
    })
    // FL 视图默认空看板：未同步时不渲染批次表格（FL 分支用例自行覆盖数据态）
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        month: '2026-09',
        batch_prefix: 'FL-2609',
        is_current_month: true,
        period: {
          start: '2026-08-27',
          end: '2026-09-26',
          label: '8月27日～9月26日',
        },
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
        generated_at: '2026-09-22T08:00:00',
      },
    })
    // 生产计划默认无数据：提炼计划产量卡显示"待更新"占位
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
    })
    // 汇总视图：生产汇总默认空数据
    actions.getProductionSummary.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { rows: [], period: null },
    })
    // 产销计划卡：默认无销售计划数据
    actions.getSalesPlanDetails.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
    })
    // 产线停产状态：默认全部生产中
    actions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { halted: [] },
    })
    actions.setProductionLineStatus.mockResolvedValue({
      code: 200,
      message: '已标记为停产中',
      data: { product_code: 'FA', halted: true },
    })
    actions.getLineHaltEvents.mockResolvedValue({ code: 200, data: { events: [] } })
    // 产品 Tab 复位为默认值，避免用例间状态串扰
    useProductContextStore.setState({ productCode: 'FA' })
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
    expect(text).toContain('L-苯丙氨酸生产线')
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
    expect(text).toMatch(/截至 \d{2}-\d{2} · 按排产计划/)
    expect(text).toContain('实际已放罐 9 ÷ 应放罐 10')
    expect(text).toMatch(/设备利用率\s*\n?\s*\d+(\.\d+)?%/)
    expect(text).not.toContain('当前运行批次')
    expect(text).not.toContain('待启动排产批次')
    // 本月批次进度条：产能口径（绿色段=已完成产能/计划产能），汇总行已删除
    expect(text).not.toContain('已放罐 10/31')
    expect(text).toContain('298,531.00 kg')
    // 右侧计划产能：未设置显示 --，有设置显示 kg
    expect(text).toContain('本月计划产能')
    expect(container.textContent || '').toContain('--')
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
    // 按移种时间排序：232/234 同移种时间(9/6 21:00)退回批号尾序 → 232 → 234；
    // 凑数的已放罐行（无移种时间）与无批号罐置末尾
    expect(tankTableBatchCells()).toEqual(['FA26232', 'FA26234', 'FA26231', '-'])
    // 已放罐行备注为固定完成话术
    const tankTable = Array.from(document.body.querySelectorAll('table')).find((t) =>
      t.textContent?.includes('当前批次号'),
    )
    expect(tankTable).toBeTruthy()
    const notes = Array.from(
      tankTable!.querySelectorAll('tbody tr td:nth-child(8)'),
    ).map((td) => td.textContent)
    // 已放罐行备注为固定完成话术
    expect(notes).toContain('该罐本批次放罐作业完成')
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

  it('shows a load failure hint when the board request rejects', async () => {
    actions.getFermentationBoard.mockRejectedValue(new Error('network down'))
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('看板数据加载失败')
  })

  it('shows the production-sales plan card in summary view', async () => {
    useProductContextStore.setState({ productCode: 'SUMMARY' })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('产销计划')
    expect(text).toContain('暂无销售计划数据，请先完成飞书同步设置并同步')
  })

  it('renders the FL batch-flow view instead of the fermentation board', async () => {
    actions.getFlBoard.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        month: '2026-09',
        batch_prefix: 'FL-2609',
        is_current_month: true,
        period: {
          start: '2026-08-27',
          end: '2026-09-26',
          label: '8月27日～9月26日',
        },
        planned_kg: 7000,
        planned_batches: 3,
        inbound_batches: 8,
        inbound_kg: 15840,
        completion_rate: 226.29,
        in_progress_count: 1,
        progress: {
          by_batches: { inbound: 2, in_progress: 1, not_started: 0 },
          by_kg: { completed_kg: 15840, planned_kg: 7000 },
        },
        flow: [
          {
            batch_no: 'FL-2609003',
            seq: 3,
            order_date: '2026-09-21',
            pick_date: '2026-09-21',
            charge_date: '2026-09-21',
            charge_time: '8:00~10:00',
            mix_date: null,
            mix_time: null,
            spec: null,
            pack_date: null,
            pack_time: null,
            inspection_date: null,
            planned_inbound_date: '2026-09-22',
            actual_inbound_date: null,
            stage_key: 'charge',
            stage_label: '投料',
            state: 'confirm_pending',
            state_label: '待入库确认',
            source_table: '9月排产',
            elapsed_days: 1,
          },
        ],
        month_batches: [],
        recent_completed: [],
        generated_at: '2026-09-22T08:53:00',
      },
    })
    useProductContextStore.setState({ productCode: 'FL' })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    // FL 独立视图：标题 + 批次工序看板（入库确认为准）
    expect(text).toContain('2%氟苯尼考预混剂生产线')
    expect(text).toContain('工序流转实时状态')
    expect(text).toContain('FL-2609003')
    expect(text).toContain('待入库确认')
    expect(text).toContain('226.29%')
    expect(text).toContain('计划批次')
    // 来源角标存在
    expect(
      container.querySelectorAll('[data-testid="fl-source-mark"]').length,
    ).toBeGreaterThanOrEqual(6)
    // 发酵模块与排产存档告警全部不出现，也不拉发酵看板
    expect(text).not.toContain('发酵罐实时状态')
    expect(text).not.toContain('本月发酵进度')
    expect(text).not.toContain('排产 Excel')
    expect(actions.getFermentationBoard).not.toHaveBeenCalled()
    // 月份参数随运行日期浮动，仅断言按概览当月取数一次
    expect(actions.getFlBoard).toHaveBeenCalledTimes(1)
    // FL 无发酵产量历史入口
    const historyBtn = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('历史数据'),
    )
    expect(historyBtn).toBeFalsy()
  })

  it('collapses the board into a halt placeholder when the line is halted', async () => {
    actions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { halted: ['FA'] },
    })
    await render()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 占位态：整页显示停产提示，看板卡片收起（标题卡按设计保留）
    expect(text).toContain('该产品生产线停产中')
    expect(text).not.toContain('本月计划批次')
    expect(text).not.toContain('立即刷新')
    // 状态下拉显示停产中
    const select = container.querySelector('[data-testid="line-status-select"]')
    expect(select?.textContent).toContain('停产中')
  })

  it('keeps the halt confirm dialog closed by default with no stray countdown', async () => {
    await render()
    const bodyText = document.body.textContent || ''
    // 确认框默认关闭；未发起切换时不出现停产/恢复确认文案
    expect(bodyText).not.toContain('确认停产')
    expect(bodyText).not.toContain('确认恢复生产')
  })

  it('renders placeholder cards with plan yield when no archive covers the period', async () => {
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '排产表未覆盖当前日期，请上传当前扎帐周期的排产 Excel',
      data: null,
    })
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-1',
          workshop: '103发酵车间',
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
    // 无存档：后端提示降级为警示条，但卡片框架照常渲染
    expect(text).toContain('排产表未覆盖当前日期')
    expect(text).toContain('发酵本月计划批次')
    expect(text).toContain('提炼计划产量')
    expect(text).toContain('本月发酵进度')
    // 发酵侧数值走空值兜底（"--"），不再整页替换为空态
    expect(text).toContain('--')
    // 提炼计划产量卡照常出飞书计划数
    expect(text).toContain('790,000')
    expect(text).toContain('103发酵车间 L-苯丙氨酸')
    // 成品入库副文案提示先上传排产，而不是"数据源待接入"
    expect(text).toContain('上传排产后按周期统计')
    expect(text).not.toContain('数据源待接入')
  })

  it('shows unified-period inbound and plan rate on the uncovered skeleton', async () => {
    // 无排产存档的未覆盖骨架：发酵段空值兜底，提炼入库按统一扎帐周期返回
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '尚未上传覆盖 2026-09-18 所在扎帐周期的排产 Excel',
      data: {
        covered: false,
        now: '2026-09-18T12:00:00',
        period: {
          start: '2026-08-27',
          end: '2026-09-26',
          label: '8月27日～9月26日',
        },
        kpis: null,
        is_current_period: true,
        month_planned_capacity_kg: null,
        extract_finished_inbound_kg: 7920,
        tanks: [],
        recent: [],
        trend: null,
        dumped_batches: [],
        extraction: null,
        alerts: [],
        maintenance: [],
      },
    })
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-ty',
          workshop: '102-2车间',
          product_name: 'L-色氨酸',
          plan_date: '2026-09-01',
          planned_yield: 60000,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
      ],
      meta: { total: 1 },
    })
    await render()
    // 切到 L-色氨酸 Tab（无排产存档的新产品，走统一周期兜底；
    // FL 氟苯尼考已改为独立批次工序视图，不再走该骨架）
    const tyTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === 'L-色氨酸',
    ) as HTMLElement
    expect(tyTab).toBeTruthy()
    await act(async () => {
      tyTab.click()
      await new Promise((r) => setTimeout(r, 150))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 未覆盖警示条保留，看板标题用全名
    expect(text).toContain('尚未上传覆盖 2026-09-18 所在扎帐周期的排产 Excel')
    expect(text).toContain('L-色氨酸生产线')
    // 提炼入库按统一扎帐周期出数，完成率 = 7920 ÷ 60000
    expect(text).toContain('7,920')
    expect(text).toContain('13.20%')
    expect(text).toContain('60,000')
    expect(text).not.toContain('上传排产后按周期统计')
    // 切回 FA，避免产品上下文泄漏到后续用例
    const faTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === 'L-苯丙氨酸',
    ) as HTMLElement
    await act(async () => {
      faTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
  })

  it('renders the uncovered skeleton without period when viewing a future month', async () => {
    // 切到未来扎帐周期且无排产（如洛伐 10 月）：骨架 period 为 null、
    // is_current_period=false，页面不得崩溃（曾因 board?.period.end 抛
    // TypeError 落入整页错误边界）
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '尚未上传覆盖 2026-10-15 所在扎帐周期的排产 Excel',
      data: {
        covered: false,
        now: '2026-09-23T12:00:00',
        period: null,
        kpis: null,
        is_current_period: false,
        month_planned_capacity_kg: null,
        extract_finished_inbound_kg: null,
        tanks: [],
        recent: [],
        trend: null,
        dumped_batches: [],
        extraction: null,
        extraction_ledger: [],
        alerts: [],
        maintenance: [],
      },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('尚未上传覆盖 2026-10-15 所在扎帐周期的排产 Excel')
    // 历史回看兜底：无周期时"截至"标签留空而不是渲染出 undefined/NaN
    expect(text).not.toContain('undefined')
    expect(text).not.toContain('NaN')
  })

  it('hints to upload or mark halt when uncovered and running', async () => {
    // 未标停产：保留"尚未上传"提示并引导设置停产
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '尚未上传覆盖 2026-10-15 所在扎帐周期的排产 Excel',
      data: {
        covered: false,
        now: '2026-09-23T12:00:00',
        period: null,
        kpis: null,
        is_current_period: false,
        month_planned_capacity_kg: null,
        extract_finished_inbound_kg: null,
        tanks: [],
        recent: [],
        trend: null,
        dumped_batches: [],
        extraction: null,
        extraction_ledger: [],
        alerts: [],
        maintenance: [],
      },
    })
    actions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      data: { halted: [], latest_events: {} },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('尚未上传覆盖 2026-10-15 所在扎帐周期的排产 Excel')
    expect(text).toContain('如该产线实际已停产，可将产线状态标记为停产')
  })

  it('states the line is halted instead of asking for upload', async () => {
    // 已标停产：看板整块收起为停产占位，不再出现"尚未上传"提示
    actions.getFermentationBoard.mockResolvedValue({
      code: 200,
      message: '尚未上传覆盖 2026-10-15 所在扎帐周期的排产 Excel',
      data: {
        covered: false,
        now: '2026-09-23T12:00:00',
        period: null,
        kpis: null,
        is_current_period: false,
        month_planned_capacity_kg: null,
        extract_finished_inbound_kg: null,
        tanks: [],
        recent: [],
        trend: null,
        dumped_batches: [],
        extraction: null,
        extraction_ledger: [],
        alerts: [],
        maintenance: [],
      },
    })
    actions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      data: { halted: ['FA'], latest_events: {} },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('该产品生产线停产中')
    expect(text).not.toContain('尚未上传覆盖')
    expect(text).not.toContain('如该产线实际已停产')
  })

  it('opens the standalone halt history modal from the title card entry', async () => {
    actions.getLineHaltEvents.mockResolvedValue({
      code: 200,
      data: {
        events: [
          {
            product_code: 'FA',
            halted: true,
            reason: '检修',
            operator_name: '王五',
            created_at: '2026-09-23T09:00:00',
          },
          {
            product_code: 'FA',
            halted: false,
            reason: null,
            operator_name: '王五',
            created_at: '2026-09-20T15:00:00',
          },
        ],
      },
    })
    await render()
    const entry = container.querySelector(
      '[data-testid="halt-history-entry"]',
    ) as HTMLElement
    expect(entry).toBeTruthy()
    await act(async () => {
      entry.click()
      await new Promise((r) => setTimeout(r, 200))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('停产历史')
    expect(text).toContain('2026-09-23 09:00　停产 · 检修 · 王五')
    expect(text).toContain('2026-09-20 15:00　复产 · 王五')
    // 只读查看，不触发状态切换请求
    expect(actions.setProductionLineStatus).not.toHaveBeenCalled()
  })

  it('keeps the selected month independent per product tab', async () => {
    // FA 切到 2026-03 后切 MC：MC 仍是当月；切回 FA 仍显示 2026-03——
    // 各视图（产品 Tab / 汇总）月份互不联动，会话内各自记忆
    actions.getFermentationBoard.mockImplementation(async (date?: string) => ({
      code: 200,
      message: 'success',
      data: {
        ...BOARD,
        period: date
          ? { start: '2026-02-27', end: '2026-03-26', label: '2月27日～3月26日' }
          : BOARD.period,
        is_current_period: !date,
      },
    }))
    await render()
    const pickerInput = () =>
      document.querySelector('.ant-picker input') as HTMLInputElement
    // 在 FA 上通过键盘输入选 2026-03（面板在 jsdom 中不可交互，走输入回车路径）
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    await act(async () => {
      pickerInput().focus()
      nativeSetter?.call(pickerInput(), '2026-03')
      pickerInput().dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 100))
    })
    await act(async () => {
      pickerInput().dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      )
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(pickerInput().value).toBe('2026-03')
    // 切到 MC：应显示当月（2026-09），不受 FA 的 2026-03 影响
    const mcTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === '霉酚酸',
    ) as HTMLElement
    await act(async () => {
      mcTab.click()
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(pickerInput().value).toBe('2026-09')
    // 切回 FA：仍记住 2026-03
    const faTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === 'L-苯丙氨酸',
    ) as HTMLElement
    await act(async () => {
      faTab.click()
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(pickerInput().value).toBe('2026-03')
    // 复位产品 Tab，避免影响后续用例
    await act(async () => {
      mcTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
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
    expect(actions.setFermentationMonthCapacity).toHaveBeenCalledWith(930000, 'FA')
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
    expect(actions.upsertFermentationBatchActual).toHaveBeenCalledWith(
      {
        batch_no: 'FA26230',
        dump_date: '2026-09-07',
        yield_kg: null,
        remark: null,
      },
      'FA',
    )
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
      'FA',
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
          workshop: '103发酵车间',
          product_name: 'L-苯丙氨酸',
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
    ).find((o) => o.textContent?.includes('103发酵车间')) as HTMLElement
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
    expect(values).toContain('103发酵车间|L-苯丙氨酸')
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
      'FA',
    )
  })

  it('switches a line to halted after the confirm countdown', async () => {
    actions.setProductionLineStatus.mockResolvedValue({
      code: 200,
      message: '已标记为停产中',
      data: null,
    })
    await render()
    // 当前产品 MC 的运行/停产切换器（Select）
    const trigger = container.querySelector(
      '[data-testid="line-status-select"]',
    ) as HTMLElement
    expect(trigger).toBeTruthy()
    // 假定时器需在弹窗挂载前接管，倒计时链才会被确定性推进
    vi.useFakeTimers()
    await act(async () => {
      trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(120)
    })
    const haltOption = Array.from(
      document.body.querySelectorAll(
        '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option',
      ),
    ).find((o) => o.textContent?.includes('停产')) as HTMLElement | undefined
    expect(haltOption).toBeTruthy()
    await act(async () => {
      haltOption!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      haltOption!.click()
      await vi.advanceTimersByTimeAsync(120)
    })
    // 确认弹窗：倒计时期间确认按钮禁用
    expect(document.body.textContent || '').toContain('确认（')
    const okBtn = () =>
      Array.from(
        document.body.querySelectorAll('.ant-modal .ant-btn-primary'),
      ).find((b) => !b.hasAttribute('disabled')) as HTMLElement | undefined
    expect(okBtn()).toBeUndefined()
    // 倒计时期间先填原因（必填：不填不能确认）
    const reasonInput = document.body.querySelector(
      '[data-testid="line-status-reason"]',
    ) as HTMLInputElement
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    await act(async () => {
      nativeSetter?.call(reasonInput, '季节性停产')
      reasonInput.dispatchEvent(new Event('input', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(100)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5100)
    })
    // act 边界每次只放行一拍：循环推进直至倒计时结束（6 拍冗余）
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })
    }
    const ready = okBtn()
    expect(ready).toBeTruthy()
    await act(async () => {
      ready!.click()
      await vi.advanceTimersByTimeAsync(200)
    })
    vi.useRealTimers()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.setProductionLineStatus).toHaveBeenCalledWith(
      true,
      'FA',
      '季节性停产',
    )
    expect(document.body.textContent || '').toContain('已标记为停产中')
  })

  it('shows the halt timeline in the confirm modal', async () => {
    actions.setProductionLineStatus.mockResolvedValue({
      code: 200,
      message: '已标记为停产中',
      data: null,
    })
    actions.getLineHaltEvents.mockResolvedValue({
      code: 200,
      data: {
        events: [
          {
            product_code: 'MC',
            halted: false,
            reason: '检修完成',
            operator_name: '李四',
            created_at: '2026-09-01T10:00:00',
          },
        ],
      },
    })
    await render()
    const trigger = container.querySelector(
      '[data-testid="line-status-select"]',
    ) as HTMLElement
    vi.useFakeTimers()
    await act(async () => {
      trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(120)
    })
    const haltOption = Array.from(
      document.body.querySelectorAll(
        '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option',
      ),
    ).find((o) => o.textContent?.includes('停产')) as HTMLElement
    await act(async () => {
      haltOption.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      haltOption.click()
      await vi.advanceTimersByTimeAsync(120)
    })
    vi.useRealTimers()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200))
    })
    const bodyText = document.body.textContent || ''
    // 时间线在弹窗内展示（最近事件）
    expect(bodyText).toContain('停产历史')
    expect(bodyText).toContain('2026-09-01 10:00')
    expect(bodyText).toContain('复产 · 检修完成 · 李四')
  })

  it('sends the halt reason with the confirm request', async () => {
    actions.setProductionLineStatus.mockResolvedValue({
      code: 200,
      message: '已标记为停产中',
      data: null,
    })
    await render()
    const trigger = container.querySelector(
      '[data-testid="line-status-select"]',
    ) as HTMLElement
    vi.useFakeTimers()
    await act(async () => {
      trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(120)
    })
    const haltOption = Array.from(
      document.body.querySelectorAll(
        '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option',
      ),
    ).find((o) => o.textContent?.includes('停产')) as HTMLElement
    await act(async () => {
      haltOption.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      haltOption.click()
      await vi.advanceTimersByTimeAsync(120)
    })
    // 倒计时期间先填原因（React 受控输入按原生 setter 触发）
    const reasonInput = document.body.querySelector(
      '[data-testid="line-status-reason"]',
    ) as HTMLInputElement
    expect(reasonInput).toBeTruthy()
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    await act(async () => {
      nativeSetter?.call(reasonInput, '转产美伐')
      reasonInput.dispatchEvent(new Event('input', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(100)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5100)
    })
    for (let i = 0; i < 6; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1100)
      })
      const ready = Array.from(
        document.body.querySelectorAll('.ant-modal .ant-btn-primary'),
      ).find((b) => !b.hasAttribute('disabled')) as HTMLElement | undefined
      if (ready) {
        await act(async () => {
          ready.click()
          await vi.advanceTimersByTimeAsync(200)
        })
        break
      }
    }
    vi.useRealTimers()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200))
    })
    expect(actions.setProductionLineStatus).toHaveBeenCalledWith(
      true,
      'FA',
      '转产美伐',
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
    // 月份选择器：顶部标题栏（L-苯丙氨酸生产线 与 生产周期 标签之间）
    const pickerInput = Array.from(container.querySelectorAll('.ant-picker input')).find(
      (i) => i.closest('.ant-space')?.textContent?.includes('L-苯丙氨酸生产线'),
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
    expect(text).toContain('历史发酵进度')
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
    authStore.state.user.role = 'user'
    authStore.state.user.permissions = []
    authStore.state.user.page_permissions = [{ page_key: 'production:overview', permissions: ['access', 'query'], data_scope: { scope_type: 'production_fermentation' } }]
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
    // 待接入占位对发酵岗可见（无敏感数据）
    expect(text).toContain('待接入')
    expect(text).not.toContain('批次台账')
    expect(text).not.toContain('成品日报')
  })

  it('shows only extraction summary for extraction-only role', async () => {
    authStore.state.user.role = 'user'
    authStore.state.user.permissions = []
    authStore.state.user.page_permissions = [{ page_key: 'production:overview', permissions: ['access', 'query'], data_scope: { scope_type: 'production_extraction' } }]
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
    // 待接入占位卡对提炼岗可见
    expect(text).toContain('待接入')
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
    expect(text).toContain('待接入')
    // 最近完成批次表已移除提炼成品/单批收率列
    expect(text).not.toContain('提炼成品(kg)')
    expect(text).not.toContain('单批收率')
    // 批次台账/成品日报卡片已下线
    expect(text).not.toContain('批次台账')
    expect(text).not.toContain('成品日报')
  })

  it('shows imported plan data with full overview scope even without legacy stage permissions', async () => {
    authStore.state.user.role = 'user'
    authStore.state.user.permissions = []
    authStore.state.user.page_permissions = [{ page_key: 'production:overview', permissions: ['access', 'query', 'operate'], data_scope: { scope_type: 'all' } }]
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('本月计划批次')
    expect(text).toContain('发酵罐实时状态')
    expect(text).toContain('提炼计划产量')
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
          product_name: 'L-苯丙氨酸',
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
          product_name: 'L-苯丙氨酸',
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
    // 默认选中第一行（201-2车间 L-苯丙氨酸），显示其计划产量与单位
    expect(text).toContain('61,000')
    expect(text).toContain('KG · 9月计划')
    // 下拉选中值带车间+产品（渲染在 Select 文本中）
    expect(text).toContain('201-2车间 L-苯丙氨酸')
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

  it('isolates the plan picker options per product tab', async () => {
    actions.getPlans.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'p-fa',
          workshop: '203车间',
          product_name: 'L-苯丙氨酸',
          plan_date: '2026-09-01',
          planned_yield: 790000,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
        {
          id: 'p-mp',
          workshop: '201-2车间',
          product_name: '霉酚酸',
          plan_date: '2026-09-01',
          planned_yield: 61000,
          unit: 'KG',
          remarks: '',
          source: 'feishu',
        },
      ],
      meta: { total: 2 },
    })
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    // FA Tab：只显示苯丙氨酸行，霉酚酸行不出现在数值位
    expect(text).toContain('790,000')
    expect(text).not.toContain('61,000')
    // 切到霉酚酸 Tab（导航显示名）：下拉与数值切换为霉酚酸行，互不影响
    const mpTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === '霉酚酸',
    ) as HTMLElement
    expect(mpTab).toBeTruthy()
    await act(async () => {
      mpTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    const textAfter = (container.textContent || '') + (document.body.textContent || '')
    expect(textAfter).toContain('61,000')
    expect(textAfter).not.toContain('790,000')
    // 切回 FA，避免产品上下文泄漏到后续用例
    const faTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === 'L-苯丙氨酸',
    ) as HTMLElement
    await act(async () => {
      faTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
  })

  it('does not echo the previous product key while the plan list refetches', async () => {
    // 两个产品的行都在首次返回里（真实同步即全量行），切 Tab 后
    // 的重新拉取延迟返回，制造取数间隙
    const planRows = [
      {
        id: 'p-fa',
        workshop: '203车间',
        product_name: 'L-苯丙氨酸',
        plan_date: '2026-09-01',
        planned_yield: 790000,
        unit: 'KG',
        remarks: '',
        source: 'feishu',
      },
      {
        id: 'p-mp',
        workshop: '201-2车间',
        product_name: '霉酚酸',
        plan_date: '2026-09-01',
        planned_yield: 61000,
        unit: 'KG',
        remarks: '',
        source: 'feishu',
      },
    ]
    const planPayload = {
      code: 200,
      message: 'success',
      data: planRows,
      meta: { total: planRows.length },
    }
    actions.getPlans
      .mockResolvedValueOnce(planPayload)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => setTimeout(() => resolve(planPayload), 300)),
      )
    await render()
    let text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('203车间 L-苯丙氨酸')
    // 切到霉酚酸 Tab：取数间隙内不得回显上一产品的选中行
    // （修复前 Select 会以原值格式短暂显示「203车间|L-苯丙氨酸」）
    const mpTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === '霉酚酸',
    ) as HTMLElement
    expect(mpTab).toBeTruthy()
    await act(async () => {
      mpTab.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).not.toContain('203车间 L-苯丙氨酸')
    expect(text).not.toContain('203车间|L-苯丙氨酸')
    // 重新拉取完成后正常回显霉酚酸行
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400))
    })
    text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('61,000')
    expect(text).toContain('201-2车间 霉酚酸')
    // 切回 FA，避免产品上下文泄漏到后续用例
    const faTab = Array.from(container.querySelectorAll('.rounded-lg')).find(
      (b) => (b.textContent || '').trim() === 'L-苯丙氨酸',
    ) as HTMLElement
    await act(async () => {
      faTab.click()
      await new Promise((r) => setTimeout(r, 120))
    })
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
