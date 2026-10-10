/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  generateScheduleDraft: vi.fn(),
  exportScheduleDraft: vi.fn(),
  getScheduleDraftRecords: vi.fn(),
  getScheduleDraftRecord: vi.fn(),
  deleteScheduleDraftRecord: vi.fn(),
  downloadScheduleDraftRecordFile: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

vi.mock('@/lib/download', () => ({ downloadBytes: vi.fn() }))

import dayjs, { type Dayjs } from 'dayjs'
import { downloadBytes } from '@/lib/download'
import { setProductionAdminForTest } from '@/test/production-auth'
import { useAuthStore } from '@/stores/auth'
import AutoSchedulingPage from './page'
import { accountingPeriodOf, alignedPeriodHint } from './aligned-period'

const DRAFT_RESULT = {
  code: 200,
  message: '草稿已生成',
  data: {
    days: [
      {
        date: '2026-11-27',
        seed_batch: 'FA26432',
        seed_tank: '201A',
        seed_note: '',
        transfer: { batch_no: 'FA26431', tank_no: '302A' },
        transfer_note: '',
        dumps: [{ batch_no: 'FA26428', tank_no: '302A' }],
        dump_inflight: true,
        idle_tanks: [],
      },
      {
        date: '2026-11-28',
        seed_batch: null,
        seed_note: '次日跳过进罐，不接种',
        transfer: null,
        transfer_note: '跳过进罐日',
        dumps: [{ batch_no: 'FA26429', tank_no: '303A' }],
        dump_inflight: true,
        idle_tanks: ['303A'],
      },
      {
        date: '2026-11-29',
        seed_batch: 'FA26433',
        seed_note: '',
        transfer: { batch_no: 'FA26432', tank_no: '303A' },
        transfer_note: '',
        dumps: [],
        dump_inflight: false,
        idle_tanks: [],
      },
    ],
    summary: {
      period: { start: '2026-11-27', end: '2026-12-26' },
      transfer_count: 29,
      seed_count: 29,
      dump_count: 29,
      dump_target: null,
      skip_dates: ['2026-11-28'],
      no_seed_days: ['2026-11-27'],
      idle_tank_days: 1,
      tank_blocks: [
        { tank_no: '302A', from_date: '2026-12-01', to_date: '2026-12-05' },
      ],
      inflight_batches: [
        { batch_no: 'FA26428', tank_no: '302A' },
        { batch_no: 'FA26429', tank_no: '303A' },
        { batch_no: 'FA26430', tank_no: '304A' },
      ],
      turnaround_hours: 8,
    },
    validation: {
      issues: [
        {
          level: 'info',
          rule: 'constraint_missing',
          text: '以下检查因排产约束未配置被跳过：月计划批数核对',
          block: null,
          date: null,
          tank_no: null,
          batch_no: null,
        },
      ],
      summary: { warn: 0, info: 1 },
    },
  },
}

function setViewUser(permissions: string[]) {
  useAuthStore.getState().setUser({
    id: 'auto-user',
    name: '排产用户',
    role: 'user',
    page_permissions: [
      {
        page_key: 'production:plan:auto-scheduling',
        module_code: 'production',
        source: 'user',
        permissions,
        visible_sections: null,
        data_scope: { scope_type: 'all' },
      },
    ],
  } as never)
}

describe('AutoSchedulingPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    setProductionAdminForTest()
    actions.getScheduleDraftRecords.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
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
      root.render(
        <App>
          <AutoSchedulingPage />
        </App>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  it('renders parameter card and empty state before generating', async () => {
    await render()
    const text = container.textContent || ''
    expect(text).toContain('自动排产（FA）')
    expect(text).toContain('目标周期')
    expect(text).toContain('起始批号')
    expect(text).toContain('跳过进罐日')
    expect(text).toContain('罐占用窗口')
    expect(text).toContain('生成草稿')
    expect(text).toContain('基于最新 FA 排产无缝接续')
    expect(actions.generateScheduleDraft).not.toHaveBeenCalled()
  })

  it('generates a draft and renders summary, validation and day table', async () => {
    actions.generateScheduleDraft.mockResolvedValue(DRAFT_RESULT)
    await render()
    const btn = [...container.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('生成草稿'),
    ) as HTMLElement
    expect(btn).toBeTruthy()
    await act(async () => {
      btn.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actions.generateScheduleDraft).toHaveBeenCalledTimes(1)
    // 默认参数：周期空（后端取下一周期）、无跳过、无占用
    expect(actions.generateScheduleDraft.mock.calls[0][0]).toEqual({
      period_start: null,
      period_end: null,
      batch_start_no: null,
      skip_dates: [],
      tank_blocks: [],
    })
    const text = container.textContent || ''
    expect(text).toContain('2026-11-27 ～ 2026-12-26')
    expect(text).toContain('移种 29 批')
    expect(text).toContain('放罐 29 批')
    expect(text).toContain('上期在制接续 3 批')
    expect(text).toContain('空拍 1 罐·天')
    expect(text).toContain('需确认 0 项 / 提示 1 项')
    expect(text).toContain('302A 12/01~12/05')
    expect(text).toContain('FA26431')
    expect(text).toContain('201A')
    expect(text).toContain('（上期在制）')
    expect(text).toContain('跳过进罐日')
    expect(text).toContain('月计划批数核对')
  })

  it('toggles skip on a day row and regenerates with the updated instruction', async () => {
    actions.generateScheduleDraft.mockResolvedValue(DRAFT_RESULT)
    await render()
    const generateBtn = [...container.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('生成草稿'),
    ) as HTMLElement
    await act(async () => {
      generateBtn.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    const skipBtn = [...container.querySelectorAll('table button')].find(
      (b) => b.textContent?.includes('跳过该日'),
    ) as HTMLElement | undefined
    expect(skipBtn).toBeTruthy()
    await act(async () => {
      skipBtn!.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actions.generateScheduleDraft).toHaveBeenCalledTimes(2)
    expect(actions.generateScheduleDraft.mock.calls[1][0].skip_dates).toEqual([
      '2026-11-27',
    ])
  })

  it('downloads the exported excel through the bytes helper', async () => {
    actions.generateScheduleDraft.mockResolvedValue(DRAFT_RESULT)
    actions.exportScheduleDraft.mockResolvedValue({
      bytes: new ArrayBuffer(8),
      filename: 'FA排产草稿_2026-11-27_2026-12-26.xlsx',
    })
    await render()
    const generateBtn = [...container.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('生成草稿'),
    ) as HTMLElement
    await act(async () => {
      generateBtn.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    const downloadBtn = [...container.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('下载 Excel'),
    ) as HTMLElement
    await act(async () => {
      downloadBtn.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actions.exportScheduleDraft).toHaveBeenCalledTimes(1)
    expect(downloadBytes).toHaveBeenCalledWith(
      expect.any(ArrayBuffer),
      'FA排产草稿_2026-11-27_2026-12-26.xlsx',
    )
  })

  it('disables generate and download without operate permission', async () => {
    setViewUser(['access', 'query'])
    await render()
    const generateBtn = [...container.querySelectorAll('button')].find(
      (b) => b.textContent?.includes('生成草稿'),
    ) as HTMLButtonElement
    expect(generateBtn.disabled).toBe(true)
    const text = container.textContent || ''
    expect(text).toContain('无操作权限，仅可查看')
    expect(actions.generateScheduleDraft).not.toHaveBeenCalled()
  })

  it('shows access notice when the page is not granted', async () => {
    useAuthStore.getState().setUser({
      id: 'no-access',
      name: '无权用户',
      role: 'user',
      page_permissions: [],
    } as never)
    await render()
    expect(container.textContent || '').toContain('暂无自动排产页面权限')
  })

  it('renders generation history with variant tags and actions', async () => {
    actions.getScheduleDraftRecords.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [
        {
          id: 'rec-1',
          params: {
            period_start: '2026-10-27',
            period_end: '2026-11-26',
            batch_start_no: null,
            skip_dates: ['2026-11-05'],
            tank_blocks: [
              { tank_no: '302A', from_date: '2026-11-01', to_date: '2026-11-05' },
            ],
          },
          summary: {
            period: { start: '2026-10-27', end: '2026-11-26' },
            transfer_count: 29,
            dump_count: 29,
          },
          downloaded_at: '2026-10-01T08:00:00Z',
          file_name: 'FA排产草稿_2026-10-27_2026-11-26.xlsx',
          created_at: '2026-10-01T07:00:00Z',
          created_by_name: '系统管理员',
        },
      ],
    })
    await render()
    const text = container.textContent || ''
    expect(text).toContain('生成历史')
    expect(text).toContain('2026-10-27～2026-11-26')
    expect(text).toContain('移种 29')
    expect(text).toContain('跳过 1 天')
    expect(text).toContain('占罐 1 段')
    expect(text).toContain('已导出')
    expect(text).toContain('系统管理员')
    expect(
      [...container.querySelectorAll('button')].some((b) =>
        b.textContent?.includes('载入参数'),
      ),
    ).toBe(true)
  })
})

describe('alignedPeriodHint', () => {
  it('maps arbitrary dates to their accounting periods', () => {
    // 10/20 落在 9/27~10/26；11/15 落在 10/27~11/26
    const hint = alignedPeriodHint([
      dayjs('2026-10-20'),
      dayjs('2026-11-15'),
    ] as [Dayjs | null, Dayjs | null])
    expect(hint).toBe(
      '将生成 2026/09/27～2026/11/26（起止各自对齐到所在扎帐周期）',
    )
    // 两天都落在同一周期 → 单月
    const single = alignedPeriodHint([
      dayjs('2026-11-03'),
      dayjs('2026-11-20'),
    ] as [Dayjs | null, Dayjs | null])
    expect(single).toContain('2026/10/27～2026/11/26')
    // 跨度超过两个月 → 超限提示
    const overlong = alignedPeriodHint([
      dayjs('2026-08-20'),
      dayjs('2026-11-15'),
    ] as [Dayjs | null, Dayjs | null])
    expect(overlong).toContain('超过两个月')
    // 未选择时无提示
    expect(alignedPeriodHint(null)).toBeNull()
  })

  it('handles year boundary accounting periods', () => {
    const [start, end] = accountingPeriodOf(dayjs('2026-12-10'))
    expect(start.format('YYYY-MM-DD')).toBe('2026-11-27')
    expect(end.format('YYYY-MM-DD')).toBe('2026-12-26')
    const [start2, end2] = accountingPeriodOf(dayjs('2027-01-05'))
    expect(start2.format('YYYY-MM-DD')).toBe('2026-12-27')
    expect(end2.format('YYYY-MM-DD')).toBe('2027-01-26')
  })
})
