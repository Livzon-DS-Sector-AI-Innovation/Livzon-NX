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
  kpis: {
    month_planned: 31,
    month_done_planned: 10,
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
    // 未接入的实际指标显示 --
    expect(text).toContain('染菌数｜染菌率')
    expect(text).toContain('--')
  })

  it('renders recent planned batches and the alert ticker', async () => {
    await render()
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('最近完成批次')
    expect(text).toContain('FA26231')
    expect(text).toContain('待接种批次 FA26235')
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
