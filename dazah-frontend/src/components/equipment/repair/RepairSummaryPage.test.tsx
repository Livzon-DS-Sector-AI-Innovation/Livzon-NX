/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'
import dayjs from 'dayjs'

const api = vi.hoisted(() => ({
  fetchRepairSummary: vi.fn(),
  fetchRepairSummarySettings: vi.fn(),
  saveRepairSummarySettings: vi.fn(),
  resetRepairSummarySettings: vi.fn(),
  fetchRepairRecords: vi.fn(),
  fetchRepairFilterOptions: vi.fn(),
  fetchRepairResults: vi.fn(),
  exportRepairRecords: vi.fn(),
}))

vi.mock('@/lib/api/repair-ledger', () => api)
vi.mock('@/components/shared/ThemedEChart', () => ({ default: () => null }))

import { RepairSummaryPage } from './RepairSummaryPage'
import type { RepairRecord, RepairSummary } from '@/lib/api/repair-ledger'

const summaryFixture = (): RepairSummary => ({
  kpi: {
    total_count: 4,
    equipment_count: 3,
    workshop_count: 2,
    total_workshops: 3,
    person_count: 3,
    abnormal_count: 2,
    daily_average: 0.4,
    previous_total_count: 3,
    change_rate: 33.3,
  },
  workshops: [
    {
      workshop_code: '102-1',
      workshop_name: '102一车间',
      repair_count: 3,
      equipment_count: 2,
      person_count: 2,
      abnormal_count: 2,
      last_repaired_at: '2026-11-20',
      last_synced_at: '2026-11-25T01:00:00Z',
      last_sync_status: 'success',
      configured: true,
      enabled: true,
      status: 'normal',
    },
    {
      workshop_code: '101-2',
      workshop_name: '101二车间',
      repair_count: 0,
      equipment_count: 0,
      person_count: 0,
      abnormal_count: 0,
      last_repaired_at: null,
      last_synced_at: null,
      last_sync_status: null,
      configured: false,
      enabled: false,
      status: 'not_configured',
    },
  ],
  top_equipment: [
    {
      workshop_code: '102-1',
      workshop_name: '102一车间',
      equipment_text: '离心泵A',
      times: 2,
      last_repaired_at: '2026-11-20',
    },
  ],
  top_faults: [
    {
      fault_desc: '机封漏水',
      times: 2,
      equipment_count: 1,
      workshops: [
        { workshop_code: '102-1', workshop_name: '102一车间', times: 2 },
        { workshop_code: '203', workshop_name: '203车间', times: 1 },
        { workshop_code: '201-1', workshop_name: '201一车间', times: 1 },
      ],
      last_repaired_at: '2026-11-20',
    },
  ],
  top_persons: [
    {
      name: '张三',
      open_id: null,
      avatar_url: null,
      times: 3,
      workshop_count: 3,
      workshops: [
        { workshop_code: '102-1', workshop_name: '102一车间', times: 1 },
        { workshop_code: '103', workshop_name: '103车间', times: 1 },
        { workshop_code: 'power', workshop_name: '动力部', times: 1 },
      ],
      last_repaired_at: '2026-11-20',
    },
  ],
  trend: [
    {
      period: '2026-11-17',
      workshop_code: '102-1',
      workshop_name: '102一车间',
      count: 2,
      equipment_count: 1,
    },
  ],
  trend_granularity: 'week',
})

const record: RepairRecord = {
  id: 'r1',
  workshop_code: '102-1',
  record_id: 'rec-1',
  workshop_text: '102一车间泵房',
  equipment_text: '离心泵A',
  repaired_at: '2026-11-20',
  person_text: '张三',
  persons: [{ name: '张三', open_id: 'ou_a', avatar_url: 'https://img/a.png' }],
  fault_desc: '机封漏水',
  spare_parts: '机封一套',
  result: '正常',
  remark: null,
  last_modified_at: '2026-11-20T08:00:00Z',
}

const flush = async (turns = 6) => {
  for (let i = 0; i < turns; i++) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

const lastNotice = () =>
  Array.from(document.querySelectorAll('.ant-message-notice'))
    .map((node) => node.textContent?.trim())
    .filter((text): text is string => Boolean(text))
    .at(-1)

describe('RepairSummaryPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.ResizeObserver =
      globalThis.ResizeObserver ||
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    vi.clearAllMocks()
    document.querySelectorAll('.ant-message').forEach((node) => node.remove())
    api.fetchRepairSummary.mockResolvedValue(summaryFixture())
    api.fetchRepairSummarySettings.mockResolvedValue({
      sort_field: 'workshop',
      sort_order: 'ascend',
      range_key: '30d',
      workshops: null,
      updated_by_name: '管理员',
      updated_at: '2026-11-25T08:00:00Z',
      can_edit: true,
    })
    api.fetchRepairRecords.mockResolvedValue({
      items: [record],
      total: 1,
      page: 1,
      page_size: 20,
    })
    api.fetchRepairFilterOptions.mockResolvedValue({
      persons: ['张三'],
      faults: ['机封漏水'],
      equipments: ['离心泵A'],
    })
    api.fetchRepairResults.mockResolvedValue(['正常', '待处理'])
    api.exportRepairRecords.mockResolvedValue(undefined)
    api.saveRepairSummarySettings.mockResolvedValue({
      sort_field: 'workshop',
      sort_order: 'ascend',
      range_key: '30d',
      workshops: null,
      updated_by_name: '管理员',
      updated_at: '2026-11-25T09:00:00Z',
      can_edit: true,
    })
    api.resetRepairSummarySettings.mockResolvedValue({
      sort_field: 'workshop',
      sort_order: 'ascend',
      range_key: '30d',
      workshops: null,
      updated_by_name: '管理员',
      updated_at: '2026-11-25T09:10:00Z',
      can_edit: true,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.querySelectorAll('.ant-message').forEach((node) => node.remove())
  })

  const renderPage = async () => {
    await act(async () => {
      root.render(
        <AntApp>
          <RepairSummaryPage />
        </AntApp>,
      )
    })
    await flush()
  }

  const buttonNamed = (text: string) =>
    Array.from(container.querySelectorAll('button')).find(
      (button) => (button.textContent ?? '').replace(/\s+/g, '') === text,
    )

  const click = async (node: Element | null | undefined) => {
    await act(async () => {
      node?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
  }

  // 表格排序后还要等一次宏任务，让 antd Table 完成重渲染
  const settle = async () => {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await flush()
  }

  it('renders KPI, workshop comparison, rankings and the not-configured banner', async () => {
    await renderPage()

    const text = container.textContent || ''
    expect(text).toContain('检修汇总')
    expect(text).toContain('维修次数')
    expect(text).toContain('102一车间')
    expect(text).toContain('1 个车间未接入检修表，未计入汇总')
    expect(text).toContain('展开 未接入车间（1）')
    // 未接入车间默认收起，主表只留有配置的车间
    expect(text).not.toContain('101二车间')
    await click(buttonNamed('展开未接入车间（1）'))
    expect(container.textContent).toContain('101二车间')
    expect(container.textContent).toContain('去配置')
    expect(text).toContain('高频设备 TOP10')
    expect(text).toContain('离心泵A')
    expect(text).toContain('高频故障 TOP10')
    expect(text).toContain('机封漏水')
    // 故障条目只列前 2 个车间 + 总数，完整次数在悬停提示里
    expect(text).toContain('102一车间、203车间 等 3 个车间')
    expect(text).toContain('人员工作量 TOP10')
    expect(text).toContain('张三')
    // 人员条目显示前 2 个车间 + 总数
    expect(text).toContain('102一车间、103车间 等 3 个车间')
    expect(text).toContain('维修趋势')
    expect(text).toContain('维修明细')

    const firstCall = api.fetchRepairSummary.mock.calls[0][0]
    expect(firstCall).toEqual(
      expect.objectContaining({
        date_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        top_limit: 10,
      }),
    )
  })

  it('drills into a workshop and returns to the whole factory', async () => {
    await renderPage()

    const rows = Array.from(
      container.querySelectorAll('.ant-table-tbody .ant-table-row'),
    )
    const target = rows.find((row) => row.textContent?.includes('102一车间'))
    expect(target).toBeTruthy()
    await click(target)

    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ workshops: ['102-1'] }),
    )
    expect(container.textContent).toContain('返回全厂')
    expect(container.textContent).toContain('102一车间 · 高频设备')

    await click(buttonNamed('返回全厂'))
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ workshops: undefined }),
    )
  })

  it('applies a ranking click and clears it when the same item is clicked again', async () => {
    await renderPage()

    const findRank = () =>
      Array.from(container.querySelectorAll('button')).find((button) =>
        button.textContent?.includes('离心泵A'),
      )
    expect(findRank()).toBeTruthy()
    await click(findRank())

    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: '离心泵A' }),
    )
    // 卡片头部出现可关闭的“已筛选”标签
    expect(container.textContent).toContain('已筛选：离心泵A')

    // 再点同一项：取消筛选，返回完整榜单
    await click(findRank())
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
    expect(container.textContent).not.toContain('已筛选：离心泵A')
  })

  it('supports the last-year preset for viewing earlier data', async () => {
    await renderPage()

    const lastYear = Array.from(
      container.querySelectorAll('.ant-segmented-item'),
    ).find((item) => item.textContent?.trim() === '去年')
    expect(lastYear).toBeTruthy()
    await click(lastYear?.querySelector('input'))

    const year = new Date().getFullYear() - 1
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({
        date_from: `${year}-01-01`,
        date_to: `${year}-12-31`,
      }),
    )
  })

  it('applies the saved global defaults before loading the summary', async () => {
    api.fetchRepairSummarySettings.mockResolvedValue({
      sort_field: 'repair_count',
      sort_order: 'descend',
      range_key: '90d',
      workshops: ['102-1'],
      updated_by_name: '管理员',
      updated_at: '2026-11-25T08:00:00Z',
      can_edit: true,
    })
    await renderPage()

    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({
        date_from: dayjs().subtract(89, 'day').format('YYYY-MM-DD'),
        workshops: ['102-1'],
      }),
    )
  })

  it('saves the current settings as the global default', async () => {
    await renderPage()

    const saveButton = buttonNamed('保存为默认')
    expect(saveButton).toBeTruthy()
    await click(saveButton)

    expect(api.saveRepairSummarySettings).toHaveBeenCalledWith({
      sort_field: 'workshop',
      sort_order: 'ascend',
      range_key: '30d',
      workshops: null,
    })
    expect(lastNotice()).toContain('已保存为全厂默认设置')
  })

  it('hides the save controls for users without operate permission', async () => {
    api.fetchRepairSummarySettings.mockResolvedValue({
      sort_field: 'workshop',
      sort_order: 'ascend',
      range_key: '30d',
      workshops: null,
      updated_by_name: '管理员',
      updated_at: '2026-11-25T08:00:00Z',
      can_edit: false,
    })
    await renderPage()

    expect(buttonNamed('保存为默认')).toBeUndefined()
    expect(buttonNamed('恢复默认')).toBeUndefined()
  })

  it('resets the global defaults with confirmation', async () => {
    await renderPage()

    const resetButton = buttonNamed('恢复默认')
    expect(resetButton).toBeTruthy()
    await click(resetButton)

    const confirm = Array.from(document.querySelectorAll('button')).find(
      (button) =>
        (button.textContent || '').replace(/\s+/g, '') === '恢复' &&
        button.closest('.ant-popover'),
    )
    expect(confirm).toBeTruthy()
    await click(confirm)

    expect(api.resetRepairSummarySettings).toHaveBeenCalledTimes(1)
    expect(lastNotice()).toContain('已恢复系统默认设置')
  })

  it('reports a save failure instead of claiming success', async () => {
    await renderPage()

    api.saveRepairSummarySettings.mockRejectedValueOnce(
      new Error('没有保存默认设置的权限'),
    )
    await click(buttonNamed('保存为默认'))
    expect(lastNotice()).toContain('没有保存默认设置的权限')
  })

  it('sorts by equipment, abnormal, person and last repair date', async () => {
    const custom = summaryFixture()
    const base = custom.workshops[0]
    custom.workshops = [
      {
        ...base,
        workshop_code: '203',
        workshop_name: '203车间',
        repair_count: 1,
        equipment_count: 5,
        abnormal_count: 3,
        person_count: 4,
        last_repaired_at: '2026-11-20',
      },
      {
        ...base,
        workshop_code: '102-1',
        workshop_name: '102一车间',
        repair_count: 1,
        equipment_count: 1,
        abnormal_count: 0,
        person_count: 1,
        last_repaired_at: '2026-11-10',
      },
    ]
    api.fetchRepairSummary.mockResolvedValue(custom)
    await renderPage()

    const clickHeader = async (label: string) => {
      const header = Array.from(container.querySelectorAll('thead th')).find(
        (th) => th.textContent?.includes(label),
      )
      const sorter = header?.querySelector('.ant-table-column-sorters') ?? header
      await click(sorter)
      await settle()
    }
    const firstRow = () =>
      Array.from(
        container.querySelectorAll('.ant-table-tbody .ant-table-row'),
      )[0]?.textContent || ''

    for (const label of ['设备数', '异常', '人数', '最近维修']) {
      await clickHeader(label)
      expect(firstRow()).toContain('203车间')
    }
  })

  it('reports summary and detail load failures', async () => {
    api.fetchRepairSummary.mockRejectedValueOnce(new Error('汇总加载失败'))
    api.fetchRepairRecords.mockRejectedValueOnce(new Error('明细加载失败'))
    await renderPage()

    const notices = Array.from(
      document.querySelectorAll('.ant-message-notice'),
    )
      .map((node) => node.textContent || '')
      .join(' ')
    expect(notices).toContain('汇总加载失败')
    expect(notices).toContain('明细加载失败')
  })

  it('clears the active ranking filter from the tag close icon', async () => {
    await renderPage()

    const rank = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('离心泵A'),
    )
    await click(rank)
    expect(container.textContent).toContain('已筛选：离心泵A')

    const close = container.querySelector('.ant-tag-close-icon')
    expect(close).toBeTruthy()
    await click(close)
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
  })

  it('clears all filters with the reset button', async () => {
    await renderPage()

    const rank = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('离心泵A'),
    )
    await click(rank)
    expect(container.textContent).toContain('已筛选：离心泵A')

    await click(buttonNamed('重置'))
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
    expect(container.textContent).not.toContain('已筛选：离心泵A')
  })

  it('reports export failures instead of claiming a download started', async () => {
    await renderPage()

    api.exportRepairRecords.mockRejectedValueOnce(
      new Error('符合条件的记录超过导出上限'),
    )
    await click(buttonNamed('导出'))
    expect(lastNotice()).toContain('超过导出上限')
  })

  it('switches between this-year and all-time presets', async () => {
    await renderPage()

    const clickPreset = async (label: string) => {
      const item = Array.from(container.querySelectorAll('.ant-segmented-item')).find(
        (node) => node.textContent?.trim() === label,
      )
      await click(item?.querySelector('input'))
    }

    await clickPreset('今年')
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({
        date_from: dayjs().startOf('year').format('YYYY-MM-DD'),
      }),
    )
    await clickPreset('全部')
    expect(api.fetchRepairSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ date_from: undefined }),
    )
  })

  it('defaults to workshop order and toggles header sorting between two directions', async () => {
    const custom = summaryFixture()
    const base = custom.workshops[0]
    custom.workshops = [
      {
        ...base,
        workshop_code: '203',
        workshop_name: '203车间',
        repair_count: 5,
        equipment_count: 5,
        person_count: 2,
      },
      {
        ...base,
        workshop_code: '102-1',
        workshop_name: '102一车间',
        repair_count: 1,
        equipment_count: 1,
        person_count: 1,
      },
    ]
    api.fetchRepairSummary.mockResolvedValue(custom)
    await renderPage()

    const rowTexts = () =>
      Array.from(container.querySelectorAll('.ant-table-tbody .ant-table-row'))
        .map((row) => row.textContent || '')
        .filter((text) => text.trim())

    // 默认按注册表顺序（102-1 在 203 前），不是按次数
    expect(rowTexts()[0]).toContain('102一车间')
    expect(rowTexts()[1]).toContain('203车间')

    const clickCountHeader = async () => {
      const header = Array.from(container.querySelectorAll('thead th')).find(
        (th) => th.textContent?.includes('维修次数'),
      )
      expect(header).toBeTruthy()
      const sorter =
        header?.querySelector('.ant-table-column-sorters') ?? header
      await click(sorter)
      await settle()
    }

    // 第一次点击：次数降序
    await clickCountHeader()
    expect(rowTexts()[0]).toContain('203车间')
    // 第二次点击：切升序（两态，不会取消排序）
    await clickCountHeader()
    expect(rowTexts()[0]).toContain('102一车间')
    // 第三次点击：回到降序
    await clickCountHeader()
    expect(rowTexts()[0]).toContain('203车间')
  })

  it('exports the current filters and reports that the download started', async () => {
    await renderPage()

    const exportButton = buttonNamed('导出')
    expect(exportButton).toBeTruthy()
    await click(exportButton)

    expect(api.exportRepairRecords).toHaveBeenCalledTimes(1)
    expect(api.exportRepairRecords).toHaveBeenCalledWith(
      expect.objectContaining({
        workshops: undefined,
        date_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
    )
    expect(lastNotice()).toContain('Excel 已开始下载')
  })

  it('shows empty states when the range has no records', async () => {
    const empty = summaryFixture()
    empty.kpi = { ...empty.kpi, total_count: 0, abnormal_count: 0 }
    empty.top_equipment = []
    empty.top_faults = []
    empty.top_persons = []
    empty.trend = []
    api.fetchRepairSummary.mockResolvedValue(empty)
    api.fetchRepairRecords.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    })

    await renderPage()

    expect(container.textContent).toContain('暂无趋势数据')
    expect(container.textContent).toContain('所选范围内没有检修记录')
  })
})
