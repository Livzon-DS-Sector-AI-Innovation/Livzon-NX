/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'

const api = vi.hoisted(() => ({
  fetchRepairRecords: vi.fn(),
  fetchRepairFrequency: vi.fn(),
  fetchRepairResults: vi.fn(),
  fetchRepairSyncStatus: vi.fn(),
  triggerRepairSync: vi.fn(),
}))

vi.mock('@/lib/api/repair-ledger', () => api)

// 配置抽屉另有测试；这里记录页面下发的 props
const drawer = vi.hoisted(() => ({
  props: [] as Array<Record<string, unknown>>,
}))
vi.mock('./RepairLedgerConfigDrawer', () => ({
  RepairLedgerConfigDrawer: (props: Record<string, unknown>) => {
    drawer.props.push(props)
    return null
  },
}))

import { RepairLedgerPage } from './RepairLedgerPage'
import type { RepairRecord } from '@/lib/api/repair-ledger'

const record = (id: string, equipment: string, overrides: Partial<RepairRecord> = {}) => ({
  id,
  workshop_code: '201-1',
  record_id: `rec-${id}`,
  workshop_text: '201一车间一楼泵房',
  equipment_text: equipment,
  repaired_at: '2026-11-02',
  person_text: '张三',
  fault_desc: '机械密封泄漏',
  spare_parts: '机械密封 1 套',
  result: '正常运行',
  remark: null,
  last_modified_at: '2026-11-02T08:00:00Z',
  ...overrides,
})

const headerTitles = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('thead th'))
    .map((th) => th.textContent?.trim() || '')
    .filter(Boolean)

const flush = async () => {
  for (let i = 0; i < 6; i++) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

const lastDrawerProps = () => drawer.props.at(-1) ?? {}

const lastNotice = () =>
  Array.from(document.querySelectorAll('.ant-message-notice'))
    .map((node) => node.textContent?.trim())
    .filter((text): text is string => Boolean(text))
    .at(-1)

describe('RepairLedgerPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    // happy-dom 没有 ResizeObserver，表格组件用它计算滚动高度
    globalThis.ResizeObserver =
      globalThis.ResizeObserver ||
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    vi.clearAllMocks()
    drawer.props.length = 0
    document.querySelectorAll('.ant-message').forEach((node) => node.remove())
    api.fetchRepairRecords.mockResolvedValue({
      items: [
        record('1', '离心泵A'),
        record('2', '薄膜蒸发器 4', { repaired_at: '2026-11-04' }),
      ],
      total: 2,
      page: 1,
      page_size: 20,
    })
    api.fetchRepairFrequency.mockResolvedValue([
      { equipment_text: '离心泵A', times: 13, last_repaired_at: '2026-11-02' },
      { equipment_text: '薄膜蒸发器 4', times: 6, last_repaired_at: '2026-11-04' },
    ])
    api.fetchRepairResults.mockResolvedValue(['正常运行', '待观察'])
    api.fetchRepairSyncStatus.mockResolvedValue({
      workshop_code: '201-1',
      total_rows: 2,
      last_synced_at: '2026-11-23T06:00:00Z',
      last_run_at: '2026-11-23T06:00:00Z',
      last_status: 'success',
      last_message: null,
      enabled: true,
    })
    api.triggerRepairSync.mockResolvedValue({ '201-1': { synced: 2, total: 2 } })
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
          <RepairLedgerPage workshopCode="201-1" workshopLabel="201一车间" />
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

  const rankButton = (equipment: string) =>
    Array.from(container.querySelectorAll('button')).find(
      (button) => button.getAttribute('title') === `${equipment}：${equipment === '离心泵A' ? 13 : 6} 次`,
    )

  const recordsCalls = () => api.fetchRepairRecords.mock.calls.map(([params]) => params)

  it('renders the repair records table and the frequency ranking for this workshop', async () => {
    await renderPage()

    expect(headerTitles(container)).toEqual([
      '维修日期',
      '设备名称/型号',
      '故障描述/原因',
      '维修人员',
      '更换备件',
      '维修后状态',
    ])
    const text = container.textContent || ''
    expect(text).toContain('机械密封泄漏')
    expect(text).toContain('正常运行')
    // 频次榜：设备名、次数、最近维修日期
    expect(text).toContain('薄膜蒸发器 4')
    expect(text).toContain('最近 2026-11-04')
    expect(text).not.toContain('本车间尚未连接检修表')
    // 已连接时显示最近同步时间
    expect(text).toContain('最近同步')
    expect(api.fetchRepairFrequency).toHaveBeenCalledWith('201-1', expect.any(String))
    expect(recordsCalls()[0]).toEqual(expect.objectContaining({
      workshop: '201-1', page: 1, page_size: 20,
    }))
    // 配置抽屉默认关闭，拿到当前车间
    expect(lastDrawerProps()).toMatchObject({ open: false, workshopCode: '201-1', workshopLabel: '201一车间' })
  })

  it('filters the table to one equipment when its ranking item is clicked, and clears on second click', async () => {
    await renderPage()

    await click(rankButton('离心泵A'))
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: '离心泵A', page: 1 }),
    )
    expect(container.textContent).toContain('设备：离心泵A')

    await click(rankButton('离心泵A'))
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
    expect(container.textContent).not.toContain('设备：离心泵A')
  })

  it('clears the equipment filter from the tag and shows a failed sync reason', async () => {
    api.fetchRepairSyncStatus.mockResolvedValue({
      workshop_code: '201-1',
      total_rows: 2,
      last_synced_at: '2026-11-23T06:00:00Z',
      last_run_at: '2026-11-23T06:00:00Z',
      last_status: 'failed',
      last_message: '飞书多维表格访问失败：99991672',
      enabled: true,
    })
    await renderPage()
    expect(container.textContent).toContain('同步失败')

    await click(rankButton('离心泵A'))
    expect(container.textContent).toContain('设备：离心泵A')
    await click(container.querySelector('.ant-tag .ant-tag-close-icon'))
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
  })

  it('applies the keyword on enter and drops it when the input is cleared', async () => {
    await renderPage()

    const search = container.querySelector('input[placeholder^="搜索"]') as HTMLInputElement
    expect(search).toBeTruthy()
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(search, '密封')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      search.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }))
    })
    await flush()
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: '密封', page: 1 }),
    )

    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(search, '')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await flush()
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: undefined }),
    )
  })

  it('narrows the ranking and the table when another time range is picked', async () => {
    await renderPage()
    const firstRange = recordsCalls().at(-1)?.date_from
    const firstRankRange = api.fetchRepairFrequency.mock.calls.at(-1)?.[1]

    const thisYear = Array.from(container.querySelectorAll('.ant-segmented-item'))
      .find((item) => item.textContent?.trim() === '今年')
    await click(thisYear?.querySelector('input'))

    expect(recordsCalls().at(-1)?.date_from).toMatch(/^\d{4}-01-01$/)
    expect(api.fetchRepairFrequency.mock.calls.at(-1)?.[1]).toMatch(/^\d{4}-01-01$/)
    expect(firstRange).not.toBe(firstRankRange === recordsCalls().at(-1)?.date_from ? firstRange : undefined)
  })

  it('collapses and expands the frequency ranking without refetching', async () => {
    await renderPage()
    const callsBefore = api.fetchRepairFrequency.mock.calls.length
    expect(rankButton('离心泵A')).toBeTruthy()

    await click(buttonNamed('收起'))
    expect(rankButton('离心泵A')).toBeUndefined()

    await click(buttonNamed('展开'))
    expect(rankButton('离心泵A')).toBeTruthy()
    expect(api.fetchRepairFrequency.mock.calls.length).toBe(callsBefore)
  })

  it('opens the config drawer from the toolbar and passes paging through to the records request', async () => {
    api.fetchRepairRecords.mockResolvedValue({
      items: [record('1', '离心泵A')],
      total: 50,
      page: 1,
      page_size: 20,
    })
    await renderPage()
    await click(buttonNamed('配置'))
    expect(lastDrawerProps()).toMatchObject({ open: true, workshopCode: '201-1' })

    const pager = container.querySelector('.ant-pagination-item-2') as HTMLElement | null
    await click(pager)
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    )
  })

  it('opens the config drawer from the first-time notice and explains why nothing is shown', async () => {
    api.fetchRepairSyncStatus.mockResolvedValue({
      workshop_code: '201-1',
      total_rows: 0,
      last_synced_at: null,
      last_run_at: null,
      last_status: null,
      last_message: null,
      enabled: false,
    })
    api.fetchRepairRecords.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    api.fetchRepairFrequency.mockResolvedValue([])

    await renderPage()

    expect(container.textContent).toContain('本车间尚未连接检修表')
    expect(container.textContent).toContain('未连接检修表')
    expect(container.textContent).toContain('所选时间范围内没有检修记录')
    await click(buttonNamed('去配置'))
    expect(lastDrawerProps()).toMatchObject({ open: true })
  })

  it('syncs from Feishu on demand and reloads the data', async () => {
    await renderPage()
    const callsBefore = api.fetchRepairRecords.mock.calls.length

    await click(buttonNamed('飞书同步'))

    expect(api.triggerRepairSync).toHaveBeenCalledWith('201-1')
    expect(api.fetchRepairRecords.mock.calls.length).toBeGreaterThan(callsBefore)
    expect(api.fetchRepairFrequency).toHaveBeenCalled()
    expect(lastNotice()).toContain('共 2 条检修记录')
  })

  it('reports sync problems instead of pretending the sync succeeded', async () => {
    await renderPage()

    api.triggerRepairSync.mockResolvedValueOnce({ '201-1': { error: '飞书多维表格访问失败：99991672' } })
    await click(buttonNamed('飞书同步'))
    expect(lastNotice()).toContain('99991672')

    api.triggerRepairSync.mockResolvedValueOnce({})
    await click(buttonNamed('飞书同步'))
    expect(lastNotice()).toContain('未启用检修表同步')

    api.triggerRepairSync.mockRejectedValueOnce(new Error('同步失败（HTTP 502）'))
    await click(buttonNamed('飞书同步'))
    expect(lastNotice()).toContain('HTTP 502')
  })
})
