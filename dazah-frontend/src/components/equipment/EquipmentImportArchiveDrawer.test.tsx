/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'
import type { EquipmentImportArchive } from '@/types/equipment'

const actionsMock = vi.hoisted(() => ({
  getEquipmentImportArchives: vi.fn(),
  getEquipmentImportArchive: vi.fn(),
  deleteEquipmentImportArchive: vi.fn(),
}))

vi.mock('@/actions/equipment', () => actionsMock)

import {
  buildMergeMap,
  EquipmentImportArchiveDrawer,
} from './EquipmentImportArchiveDrawer'

const listEnvelope = (items: unknown[], total = items.length) => ({
  code: 200,
  message: 'success',
  data: items,
  meta: { page: 1, page_size: 10, total },
})

const archiveItem = {
  id: 'arc-1',
  workshop_code: '103',
  file_name: '103台账.xlsx',
  sheet_name: 'Sheet1',
  row_count: 2,
  col_count: 3,
  import_summary: { created: 2, updated: 0, failed: 0 },
  created_by_name: '测试员',
  created_at: '2026-10-14T06:00:00Z',
}

const archiveDetail: EquipmentImportArchive = {
  ...archiveItem,
  rows: [
    ['设备编号', '设备名称', '安装地点'],
    ['FF1-1-1-001', '150L培养罐1', '103车间'],
  ],
  merges: [],
  col_widths: [100, 120, 100],
}

describe('buildMergeMap', () => {
  it('maps anchor spans and covered-cell hide directions', () => {
    const map = buildMergeMap([
      { s: { r: 0, c: 1 }, e: { r: 1, c: 1 } }, // 纵向合并 B1:B2
      { s: { r: 0, c: 0 }, e: { r: 0, c: 0 } }, // 单格（等于不合并）
    ])
    expect(map.get('0:1')).toEqual({ rowSpan: 2, colSpan: 1 })
    // 被上方行覆盖 → rowSpan:0
    expect(map.get('1:1')).toEqual({ rowSpan: 0 })
    // 单格合并产生 1×1 锚点，与普通单元格等价
    expect(map.get('0:0')).toEqual({ rowSpan: 1, colSpan: 1 })
  })

  it('marks same-row covered cells with colSpan zero', () => {
    const map = buildMergeMap([{ s: { r: 1, c: 0 }, e: { r: 1, c: 2 } }])
    expect(map.get('1:0')).toEqual({ rowSpan: 1, colSpan: 3 })
    expect(map.get('1:1')).toEqual({ colSpan: 0 })
    expect(map.get('1:2')).toEqual({ colSpan: 0 })
  })
})

describe('EquipmentImportArchiveDrawer', () => {
  let container: HTMLDivElement
  let root: Root
  const onClose = vi.fn()

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  function render(workshopCode?: string) {
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportArchiveDrawer
            open
            onClose={onClose}
            workshopCode={workshopCode}
          />
        </AntApp>,
      )
    })
  }

  it('loads and renders the archive list with summary', async () => {
    actionsMock.getEquipmentImportArchives.mockResolvedValue(
      listEnvelope([archiveItem]),
    )
    render('103')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actionsMock.getEquipmentImportArchives).toHaveBeenCalledWith(
      1,
      10,
      '103',
    )
    const text = document.body.textContent || ''
    expect(text).toContain('台账上传历史')
    expect(text).toContain('103台账.xlsx')
    expect(text).toContain('新建 2')
    expect(text).toContain('测试员')
  })

  it('shows the snapshot table when opening an archive', async () => {
    actionsMock.getEquipmentImportArchives.mockResolvedValue(
      listEnvelope([archiveItem]),
    )
    actionsMock.getEquipmentImportArchive.mockResolvedValue({
      code: 200,
      message: 'success',
      data: archiveDetail,
    })
    render('103')
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const viewButton = Array.from(
      document.body.querySelectorAll('button'),
    ).find((button) => button.textContent?.includes('查看'))
    expect(viewButton).toBeTruthy()
    await act(async () => {
      viewButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actionsMock.getEquipmentImportArchive).toHaveBeenCalledWith('arc-1')
    const text = document.body.textContent || ''
    expect(text).toContain('FF1-1-1-001')
    expect(text).toContain('150L培养罐1')
  })

  it('surfaces a load failure message without crashing', async () => {
    actionsMock.getEquipmentImportArchives.mockRejectedValue(
      new Error('网络异常'),
    )
    render()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('台账上传历史')
  })
})

describe('EquipmentImportArchiveDrawer 操作覆盖', () => {
  let container: HTMLDivElement
  let root: Root
  const onClose = vi.fn()

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  function render() {
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportArchiveDrawer open onClose={onClose} />
        </AntApp>,
      )
    })
  }

  function findButton(text: string) {
    return Array.from(document.body.querySelectorAll('button')).find(
      (button) => button.textContent?.includes(text),
    )
  }

  async function settle(ms = 80) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, ms))
    })
  }

  it('deletes an archive after confirmation and reloads the list', async () => {
    actionsMock.getEquipmentImportArchives.mockResolvedValue(
      listEnvelope([archiveItem]),
    )
    actionsMock.deleteEquipmentImportArchive.mockResolvedValue(null)
    render()
    await settle()
    const deleteButton = findButton('删除')
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    // 确认弹窗的确定按钮（antd Modal.confirm 渲染在 body）
    const confirmOk = Array.from(
      document.body.querySelectorAll('.ant-modal .ant-btn-primary, .ant-modal-confirm-btns .ant-btn-primary'),
    ).at(-1) as HTMLButtonElement | undefined
    expect(confirmOk).toBeTruthy()
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actionsMock.deleteEquipmentImportArchive).toHaveBeenCalledWith(
      'arc-1',
    )
    // 删除成功后重新加载列表（第二次调用）
    expect(actionsMock.getEquipmentImportArchives).toHaveBeenCalledTimes(2)
  })

  it('returns from detail view back to the list', async () => {
    actionsMock.getEquipmentImportArchives.mockResolvedValue(
      listEnvelope([archiveItem]),
    )
    actionsMock.getEquipmentImportArchive.mockResolvedValue({
      code: 200,
      message: 'success',
      data: archiveDetail,
    })
    render()
    await settle()
    await act(async () => {
      findButton('查看')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(document.body.textContent).toContain('FF1-1-1-001')
    // 抽屉标题里的返回按钮是第一个按钮
    const backButton = document.querySelector(
      '.ant-drawer-header button',
    ) as HTMLButtonElement | null
    expect(backButton).toBeTruthy()
    await act(async () => {
      backButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 40))
    })
    // 回到列表：查看按钮重新出现，快照内容消失
    expect(findButton('查看')).toBeTruthy()
    expect(document.body.textContent).not.toContain('FF1-1-1-001')
  })

  it('switches list pages through pagination', async () => {
    const many = Array.from({ length: 11 }, (_, i) => ({
      ...archiveItem,
      id: `arc-${i + 1}`,
      file_name: `台账第${i + 1}次.xlsx`,
    }))
    actionsMock.getEquipmentImportArchives.mockImplementation(async (
      page: number,
    ) => listEnvelope(many.slice((page - 1) * 10, page * 10), 11))
    render()
    await settle()
    const pageTwo = Array.from(
      document.body.querySelectorAll('.ant-pagination li'),
    ).find((li) => li.getAttribute('title') === '2')
    expect(pageTwo).toBeTruthy()
    await act(async () => {
      pageTwo?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actionsMock.getEquipmentImportArchives).toHaveBeenCalledWith(
      2,
      10,
      undefined,
    )
    expect(document.body.textContent).toContain('台账第11次.xlsx')
  })
})
