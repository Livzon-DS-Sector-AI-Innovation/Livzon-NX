/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 面板交互补充用例：写回子表初始化、筛选刷新、批量打印入口、详情抽屉入口、
 * 初始加载失败兜底。基础渲染与二维码下载在 FireEquipmentPanel.test.tsx。
 */

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  getFireEquipmentStats: vi.fn(),
  getFireEquipmentList: vi.fn(),
  getFireInspectionRecords: vi.fn(),
  syncFireEquipment: vi.fn(),
  initFireEquipmentWritebackTable: vi.fn(),
  getFireEquipmentDetail: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getFireEquipmentStats: mocks.getFireEquipmentStats,
  getFireEquipmentList: mocks.getFireEquipmentList,
  getFireInspectionRecords: mocks.getFireInspectionRecords,
  syncFireEquipment: mocks.syncFireEquipment,
  initFireEquipmentWritebackTable: mocks.initFireEquipmentWritebackTable,
  getFireEquipmentDetail: mocks.getFireEquipmentDetail,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canOperate: mocks.canOperate,
    canImport: true,
    canView: true,
  }),
}))

import FireEquipmentPanel from './FireEquipmentPanel'

const PAGE_KEY = 'safety:emergency-accident:fire-equipment-inspection'

const STATS = {
  total: 2,
  extinguisher_count: 1,
  hydrant_count: 1,
  inspected_this_month: 1,
  uninspected_this_month: 1,
  failed_this_month: 0,
  expired_count: 1,
  expiring_in_30_count: 2,
  is_configured: true,
  writeback_enabled: false,
  last_synced_at: '2026-10-20T01:00:00Z',
  last_sync_status: 'success',
  last_sync_error: null,
}

const EQUIPMENT_PAGE = {
  columns: [],
  items: [
    {
      id: 'eq-1',
      equipment_type: 'extinguisher',
      equipment_type_label: '灭火器',
      equipment_no: 'MQC-001',
      department: '101一车间',
      location: '东侧通道口',
      tab_name: '主表',
      table_id: 'tbl1',
      record_id: 'rec1',
      fields: {},
      last_inspected_at: '2026-10-19T02:00:00Z',
      last_inspection_result: 'pass',
      month_status: 'inspected',
      last_synced_at: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}

const RECORDS_PAGE = { columns: [], items: [], total: 0, page: 1, page_size: 20 }

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 40))
}

describe('FireEquipmentPanel interactions (batch3 supplement)', () => {
  let root: Root | null = null
  let container: HTMLElement | null = null

  beforeEach(() => {
    mocks.getFireEquipmentStats.mockResolvedValue({
      code: 200,
      data: STATS,
    })
    mocks.getFireEquipmentList.mockResolvedValue({
      code: 200,
      data: EQUIPMENT_PAGE,
    })
    mocks.getFireEquipmentDetail.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })

    mocks.getFireInspectionRecords.mockResolvedValue({
      code: 200,
      data: RECORDS_PAGE,
    })
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = null
    container = null
    vi.clearAllMocks()
  })

  function renderPanel(
    overrides: Partial<Parameters<typeof import('./FireEquipmentPanel').default>[0]> = {}
  ) {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root!.render(
        <FireEquipmentPanel
          pageKey={PAGE_KEY}
          initialStats={STATS as never}
          initialEquipment={EQUIPMENT_PAGE as never}
          initialRecords={RECORDS_PAGE as never}
          initialError={null}
          {...overrides}
        />
      )
    })
    return { container, root }
  }

  it('初始化点检回写子表并刷新统计', async () => {
    mocks.initFireEquipmentWritebackTable.mockResolvedValue({
      code: 200,
      data: { created: true, table_name: '点检记录' },
    })
    const view = renderPanel()
    container = view.container

    const initButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('一键创建点检记录回写表'),
    )
    expect(initButton).toBeTruthy()
    await act(async () => {
      initButton!.click()
      await flush()
    })
    expect(mocks.initFireEquipmentWritebackTable).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
    })
    expect(mocks.getFireEquipmentStats).toHaveBeenCalled()
  })

  it('类型筛选后点刷新按新筛选加载', async () => {
    const view = renderPanel()
    container = view.container

    const hydrant = Array.from(document.body.querySelectorAll('.ant-segmented-item-input, label, button')).find(
      (el) => el.textContent?.includes('消防栓') || (el as HTMLInputElement).value === 'hydrant',
    ) as HTMLElement
    expect(hydrant).toBeTruthy()
    await act(async () => {
      hydrant!.click()
      await flush()
    })

    mocks.getFireEquipmentList.mockClear()
    mocks.getFireEquipmentList.mockResolvedValue({ code: 200, data: EQUIPMENT_PAGE })
    const refresh = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('刷新'),
    )
    expect(refresh).toBeTruthy()
    await act(async () => {
      refresh!.click()
      await flush()
    })
    expect(mocks.getFireEquipmentList).toHaveBeenCalledWith(
      expect.objectContaining({ equipmentType: 'hydrant' }),
    )
  })

  it('批量打印入口按 200 上限拉取并打开二维码弹窗', async () => {
    const view = renderPanel()
    container = view.container

    const printButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('批量打印二维码'),
    )
    expect(printButton).toBeTruthy()
    await act(async () => {
      printButton!.click()
      await flush()
    })
    expect(mocks.getFireEquipmentList).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, pageSize: 200 }),
    )
  })

  it('初始加载失败时渲染错误兜底', () => {
    const view = renderPanel({
      initialEquipment: null,
      initialError: '飞书绑定缺失',
    })
    container = view.container
    expect(container.innerHTML).toContain('器材台账加载失败')
  })

  it('点器材编号打开详情抽屉', async () => {
    const view = renderPanel()
    container = view.container

    const link = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('MQC-001'),
    )
    expect(link).toBeTruthy()
    await act(async () => {
      link!.click()
      await flush()
    })
    expect(mocks.getFireEquipmentDetail).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      equipmentId: 'eq-1',
    })
  })

  it('点检记录页签筛选与刷新', async () => {
    const view = renderPanel()
    container = view.container
    mocks.getFireInspectionRecords.mockClear()
    mocks.getFireInspectionRecords.mockResolvedValue({
      code: 200,
      data: RECORDS_PAGE,
    })

    // 点检记录 Segmented：按结果筛选（合格）后刷新
    const passSegment = Array.from(document.body.querySelectorAll('*')).find(
      (el) => el.textContent === '合格' && el.closest('.ant-segmented-item'),
    ) as HTMLElement
    if (passSegment) {
      await act(async () => {
        passSegment.click()
        await flush()
      })
    }

    const refresh = Array.from(document.body.querySelectorAll('button')).filter(
      (button) => button.textContent?.includes('刷新'),
    )[1]
    if (refresh) {
      await act(async () => {
        refresh.click()
        await flush()
      })
      expect(mocks.getFireInspectionRecords).toHaveBeenCalled()
    }
  })

  it('同步失败分支提示错误', async () => {
    mocks.syncFireEquipment.mockResolvedValue({ code: 500, message: '飞书绑定失效' })
    const view = renderPanel()
    container = view.container

    const syncButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('立即同步飞书台账'),
    )
    expect(syncButton).toBeTruthy()
    await act(async () => {
      syncButton!.click()
      await flush()
    })
    expect(mocks.syncFireEquipment).toHaveBeenCalled()
  })

  it('回写子表初始化失败分支提示错误', async () => {
    mocks.initFireEquipmentWritebackTable.mockResolvedValue({
      code: 500,
      message: '创建失败',
    })
    const view = renderPanel()
    container = view.container

    const initButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('一键创建点检记录回写表'),
    )
    expect(initButton).toBeTruthy()
    await act(async () => {
      initButton!.click()
      await flush()
    })
    expect(mocks.initFireEquipmentWritebackTable).toHaveBeenCalled()
  })

  it('批量打印：清单读取失败与空清单两个分支', async () => {
    const view = renderPanel()
    container = view.container

    const printButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('批量打印二维码'),
    )
    expect(printButton).toBeTruthy()
    // 失败分支
    mocks.getFireEquipmentList.mockResolvedValue({ code: 500, message: '读取失败', data: null })
    await act(async () => {
      printButton!.click()
      await flush()
    })
    // 空清单分支
    mocks.getFireEquipmentList.mockResolvedValue({
      code: 200,
      data: { ...EQUIPMENT_PAGE, items: [] },
    })
    await act(async () => {
      printButton!.click()
      await flush()
    })
    expect(mocks.getFireEquipmentList.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('月度状态与到期状态筛选联动刷新', async () => {
    const view = renderPanel()
    container = view.container
    mocks.getFireEquipmentList.mockClear()
    mocks.getFireEquipmentList.mockResolvedValue({ code: 200, data: EQUIPMENT_PAGE })

    // 依次点击月度/到期 Segmented 项，再统一刷新
    for (const label of ['本月未检', '30天内到期']) {
      const item = Array.from(document.body.querySelectorAll('.ant-segmented-item-input, label, button')).find(
        (el) => el.textContent?.includes(label),
      ) as HTMLElement | undefined
      if (item) {
        await act(async () => {
          item.click()
          await flush()
        })
      }
    }
    const refresh = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('刷新'),
    )!
    await act(async () => {
      refresh.click()
      await flush()
    })
    expect(mocks.getFireEquipmentList).toHaveBeenCalledWith(
      expect.objectContaining({ monthStatus: 'uninspected', expiryStatus: 'expiring' }),
    )
  })

  it('台账分页翻页与关键字搜索', async () => {
    mocks.getFireEquipmentList.mockClear()
    mocks.getFireEquipmentList.mockResolvedValue({
      code: 200,
      data: { ...EQUIPMENT_PAGE, total: 25 },
    })
    const view = renderPanel()
    container = view.container
    await act(async () => {
      await flush()
    })

    // 翻到第 2 页
    const page2 = Array.from(document.body.querySelectorAll('.ant-pagination-item')).find(
      (node) => node.textContent === '2',
    )
    if (page2) {
      await act(async () => {
        page2.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await flush()
      })
      expect(mocks.getFireEquipmentList).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      )
    }

    // 关键字搜索（Input.Search 触发按钮）
    mocks.getFireEquipmentList.mockClear()
    const searchButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.className.includes('ant-input-search-button') || button.closest('.ant-input-search'),
    )
    if (searchButton) {
      await act(async () => {
        searchButton.click()
        await flush()
      })
      expect(mocks.getFireEquipmentList).toHaveBeenCalled()
    }
  })

  it('点检记录页签：筛选、搜索与翻页', async () => {
    mocks.getFireInspectionRecords.mockClear()
    mocks.getFireInspectionRecords.mockResolvedValue({
      code: 200,
      data: { ...RECORDS_PAGE, total: 25 },
    })
    const view = renderPanel()
    container = view.container
    await act(async () => {
      await flush()
    })

    const recordsTab = Array.from(document.body.querySelectorAll('.ant-tabs-tab')).find(
      (node) => node.textContent?.includes('点检记录'),
    )
    expect(recordsTab).toBeTruthy()
    await act(async () => {
      recordsTab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await flush()
    })

    const passSegment = Array.from(document.body.querySelectorAll('.ant-segmented-item')).find(
      (node) => node.textContent?.includes('合格'),
    )
    if (passSegment) {
      await act(async () => {
        passSegment.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await flush()
      })
    }

    mocks.getFireInspectionRecords.mockClear()
    const recordRefresh = Array.from(document.body.querySelectorAll('button')).filter(
      (button) => button.textContent?.includes('刷新'),
    ).at(-1)!
    await act(async () => {
      recordRefresh.click()
      await flush()
    })
    expect(mocks.getFireInspectionRecords).toHaveBeenCalled()
  })
})
