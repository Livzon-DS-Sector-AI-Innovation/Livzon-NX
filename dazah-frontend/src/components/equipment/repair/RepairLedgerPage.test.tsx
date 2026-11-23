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
vi.mock('./RepairLedgerConfigDrawer', () => ({ RepairLedgerConfigDrawer: () => null }))

import { RepairLedgerPage } from './RepairLedgerPage'

const record = (id: string, equipment: string, overrides: Record<string, unknown> = {}) => ({
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

const findButton = (text: string) =>
  Array.from(document.querySelectorAll('button')).find(
    (button) => button.textContent?.includes(text),
  )

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
    expect(text).toContain('13')
    expect(text).toContain('薄膜蒸发器 4')
    expect(text).toContain('最近 2026-11-04')
    expect(text).not.toContain('本车间尚未连接检修表')
    expect(api.fetchRepairFrequency).toHaveBeenCalledWith('201-1', expect.any(String))
    expect(api.fetchRepairRecords).toHaveBeenCalledWith(
      expect.objectContaining({ workshop: '201-1', page: 1, page_size: 20 }),
    )
  })

  it('filters the table to one equipment when its ranking item is clicked, and clears on second click', async () => {
    await renderPage()

    const rankButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.getAttribute('title') === '离心泵A：13 次',
    )
    expect(rankButton).toBeTruthy()

    await act(async () => {
      rankButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: '离心泵A', page: 1 }),
    )
    expect(container.textContent).toContain('设备：离心泵A')

    await act(async () => {
      rankButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(api.fetchRepairRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ equipment: undefined }),
    )
    expect(container.textContent).not.toContain('设备：离心泵A')
  })

  it('syncs from Feishu on demand and reloads the data', async () => {
    await renderPage()
    const callsBefore = api.fetchRepairRecords.mock.calls.length

    await act(async () => {
      findButton('飞书同步')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(api.triggerRepairSync).toHaveBeenCalledWith('201-1')
    expect(api.fetchRepairRecords.mock.calls.length).toBeGreaterThan(callsBefore)
    expect(api.fetchRepairFrequency).toHaveBeenCalled()
  })

  it('tells the user to connect the repair table when the workshop is not configured', async () => {
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

    const text = container.textContent || ''
    expect(text).toContain('本车间尚未连接检修表')
    expect(findButton('去配置')).toBeTruthy()
  })
})
