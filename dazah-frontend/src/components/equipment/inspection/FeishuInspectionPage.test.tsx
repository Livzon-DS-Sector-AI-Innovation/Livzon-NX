/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchInspectionFeishuRecords: vi.fn(),
  fetchInspectionFeishuDevices: vi.fn(),
  fetchInspectionFeishuSyncStatus: vi.fn(),
  fetchInspectionFeishuTodaySummary: vi.fn(),
  triggerInspectionFeishuSync: vi.fn(),
  fetchInspectionFeishuConfig: vi.fn(),
  updateInspectionFeishuConfig: vi.fn(),
  testInspectionFeishuConfig: vi.fn(),
}))

vi.mock('@/lib/api/inspection-feishu', () => api)

import { FeishuInspectionPage } from './FeishuInspectionPage'

const todayRecord = {
  id: 'rec-1',
  source: 'today',
  record_date: '2026-10-10',
  equipment_name: '酸化罐 1',
  equipment_no: 'XT1-1-1-028',
  am_clean: '√',
  pm_clean: '×',
  anomaly_note: '下午清洁异常',
  process_status: null,
  has_abnormal: true,
}

const device = {
  record_id: 'dev-1',
  equipment_name: '酸化罐 1',
  equipment_no: 'XT1-1-1-028',
  model: 'PJ-3000L',
  location_name: '201二车间',
  in_ledger: true,
  today_status: 'abnormal',
}

function paged(items: unknown[]) {
  return { items, total: items.length, page: 1, page_size: 20 }
}

async function flush(ms = 80) {
  await act(async () => {
    await new Promise((r) => setTimeout(r, ms))
  })
}

describe('FeishuInspectionPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchInspectionFeishuRecords.mockResolvedValue(paged([todayRecord]))
    api.fetchInspectionFeishuDevices.mockResolvedValue([device])
    api.fetchInspectionFeishuSyncStatus.mockResolvedValue({
      enabled: true,
      tables: [
        {
          table_key: 'today',
          total_rows: 48,
          last_run_at: '2026-10-10T08:00:00Z',
          last_status: 'success',
          last_message: null,
        },
        {
          table_key: 'history',
          total_rows: 50,
          last_run_at: '2026-10-10T08:00:00Z',
          last_status: 'failed',
          last_message: '飞书访问失败',
        },
      ],
    })
    api.fetchInspectionFeishuTodaySummary.mockResolvedValue({
      date: '2026-10-10',
      total_devices: 49,
      inspected: 46,
      abnormal: 2,
    })
    api.triggerInspectionFeishuSync.mockResolvedValue({
      today: { synced: 2, total: 48 },
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  function renderPage() {
    act(() => {
      root.render(
        <AntApp>
          <FeishuInspectionPage />
        </AntApp>,
      )
    })
    return flush()
  }

  function findButton(text: string) {
    const button = [...document.body.querySelectorAll('button')].find((b) =>
      b.textContent?.replace(/\s/g, '').includes(text.replace(/\s/g, '')),
    ) as HTMLButtonElement | undefined
    expect(button, `button not found: ${text}`).toBeTruthy()
    return button!
  }

  it('renders the header, sync bar, summary card and today table', async () => {
    await renderPage()
    const text = document.body.textContent || ''
    expect(text).toContain('设备巡检')
    expect(text).toContain('岗位巡检记录（飞书多维表格镜像，只读展示）')
    expect(text).toContain('巡检数据在飞书多维表格录入，平台每 5 分钟自动同步')
    expect(text).toContain('最近同步')
    expect(text).toContain('镜像 98 行')
    expect(text).toContain('查看原因')
    expect(text).toContain('今日进度（2026-10-10）')
    expect(text).toContain('46 / 49')
    expect(text).toContain('含异常')
    expect(text).toContain('酸化罐 1')
    expect(text).toContain('XT1-1-1-028')
    expect(text).toContain('下午清洁异常')
    expect(api.fetchInspectionFeishuRecords).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'today' }),
    )
  })

  it('triggers a manual sync and refreshes the page data', async () => {
    await renderPage()
    await act(async () => {
      findButton('飞书同步').click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(api.triggerInspectionFeishuSync).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('飞书同步完成，本次更新 2 条')
  })

  it('shows the unconfigured state when the mirror is disabled', async () => {
    api.fetchInspectionFeishuSyncStatus.mockResolvedValue({
      enabled: false,
      tables: [],
    })
    await renderPage()
    expect(document.body.textContent).toContain('飞书镜像同步未配置')
  })

  it('switches to the history tab with the process status column', async () => {
    api.fetchInspectionFeishuRecords.mockResolvedValue(
      paged([{ ...todayRecord, source: 'history', process_status: '已拆分' }]),
    )
    await renderPage()
    const historyTab = [...document.body.querySelectorAll('.ant-tabs-tab')].find(
      (t) => t.textContent?.includes('巡检记录'),
    ) as HTMLElement | undefined
    expect(historyTab).toBeTruthy()
    await act(async () => {
      historyTab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(api.fetchInspectionFeishuRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ source: 'history' }),
    )
    const text = document.body.textContent || ''
    expect(text).toContain('处理状态')
    expect(text).toContain('已拆分')
  })

  it('lists mirrored devices with ledger links and today status', async () => {
    await renderPage()
    const devicesTab = [...document.body.querySelectorAll('.ant-tabs-tab')].find(
      (t) => t.textContent?.includes('巡检设备'),
    ) as HTMLElement | undefined
    expect(devicesTab).toBeTruthy()
    await act(async () => {
      devicesTab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      for (let i = 0; i < 20 && api.fetchInspectionFeishuDevices.mock.calls.length === 0; i += 1) {
        await new Promise((r) => setTimeout(r, 50))
      }
    })
    expect(api.fetchInspectionFeishuDevices).toHaveBeenCalled()
    const text = document.body.textContent || ''
    expect(text).toContain('已关联')
    expect(text).toContain('PJ-3000L')
    expect(text).toContain('201二车间')
    expect(text).toContain('异常')
  })

  it('reports sync failures with a readable message', async () => {
    api.triggerInspectionFeishuSync.mockRejectedValue(
      new Error('同步失败（HTTP 500）'),
    )
    await renderPage()
    await act(async () => {
      findButton('飞书同步').click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent).toContain('同步失败（HTTP 500）')
  })
})
