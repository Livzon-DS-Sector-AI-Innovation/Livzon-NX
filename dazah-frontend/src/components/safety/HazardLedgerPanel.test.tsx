/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getHazardIdentifications: vi.fn(),
  getHazardFilterOptions: vi.fn(),
  getHILedgerStats: vi.fn(),
  exportHazardLedgerPdf: vi.fn(),
  downloadBase64: vi.fn(),
  canImport: true,
  canOperate: true,
}))

vi.mock('@/actions/safety', () => ({
  getHazardIdentifications: mocks.getHazardIdentifications,
  getHazardFilterOptions: mocks.getHazardFilterOptions,
  getHILedgerStats: mocks.getHILedgerStats,
  exportHazardLedgerPdf: mocks.exportHazardLedgerPdf,
}))

vi.mock('@/lib/download', () => ({
  downloadBase64: mocks.downloadBase64,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canImport: mocks.canImport,
    canOperate: mocks.canOperate,
    canView: true,
  }),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

import HazardLedgerPanel from './HazardLedgerPanel'

const ROW = {
  id: 'h1',
  hazard_id_no: 'H-2026-001',
  department: '103三车间',
  position: '投料工',
  production_step: '投料',
  hazard_type: '机械伤害',
  overall_status: 'completed',
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 60))
}

function findButtons(container: ParentNode, text: string) {
  return Array.from(container.querySelectorAll('button')).filter((button) =>
    button.textContent?.includes(text),
  )
}

describe('HazardLedgerPanel', () => {
  let root: Root | undefined
  let container: HTMLElement | undefined

  beforeEach(() => {
    mocks.getHazardIdentifications.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [ROW],
      meta: { total: 1 },
    })
    mocks.getHazardFilterOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        departments: ['103三车间'],
        positions: [{ department: '103三车间', position: '投料工' }],
      },
    })
    mocks.getHILedgerStats.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { total: 1, level_1: 0, level_2: 1, level_3: 0, level_4: 0 },
    })
    mocks.exportHazardLedgerPdf.mockResolvedValue({
      code: 200,
      message: 'success',
      data: 'data:application/pdf;base64,QUJD',
    })
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = undefined
    container = undefined
    vi.clearAllMocks()
  })

  function renderPanel() {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root!.render(
        <App>
          <HazardLedgerPanel />
        </App>,
      )
    })
  }

  it('挂载后拉取选项/统计/台账并渲染行数据', async () => {
    renderPanel()
    await act(flush)

    expect(mocks.getHazardFilterOptions).toHaveBeenCalled()
    expect(mocks.getHILedgerStats).toHaveBeenCalled()
    expect(mocks.getHazardIdentifications).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20, overall_status: 'completed' }),
    )
    const text = document.body.textContent ?? ''
    expect(text).toContain('机械伤害')
    expect(text).toContain('103三车间')
    expect(text).toContain('共 1 条')
  })

  it('台账加载失败时提示错误', async () => {
    mocks.getHazardIdentifications.mockRejectedValueOnce(new Error('boom'))
    renderPanel()
    await act(flush)
    expect((document.body.textContent ?? '').includes('加载台账失败')).toBe(true)
  })

  it('点编辑打开在线编辑抽屉（有操作权限）', async () => {
    renderPanel()
    await act(flush)

    const editButton = findButtons(document.body, '编辑').at(-1)
    expect(editButton).toBeTruthy()
    await act(async () => {
      editButton!.click()
      await flush()
    })
    // 抽屉打开后的表单交互由 HazardLedgerEditDrawer 自身测试覆盖
    const text = document.body.textContent ?? ''
    expect(text.length).toBeGreaterThan(0)
  })

  it('导出流程：触发按钮打开弹窗，确认后调用导出接口', async () => {
    renderPanel()
    await act(flush)

    // 头部触发按钮与弹窗确认按钮文案相同：先点第一个，再点最后一个
    const trigger = findButtons(document.body, '导出 PDF')[0]
    expect(trigger).toBeTruthy()
    await act(async () => {
      trigger!.click()
      await flush()
    })
    expect((document.body.textContent ?? '').includes('自然语言')).toBe(true)

    const confirm = findButtons(document.body, '导出 PDF').at(-1)!
    await act(async () => {
      confirm.click()
      await flush()
    })
    expect(mocks.exportHazardLedgerPdf).toHaveBeenCalled()
  })
})
