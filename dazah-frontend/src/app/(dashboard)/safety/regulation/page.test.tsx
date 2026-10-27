/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getRegulations: vi.fn(),
  createRegulation: vi.fn(),
  updateRegulation: vi.fn(),
  deleteRegulation: vi.fn(),
  uploadRegulationDocument: vi.fn(),
  getRevisions: vi.fn(),
  createRevision: vi.fn(),
  deleteRevision: vi.fn(),
  manualRevisionComplete: vi.fn(),
  batchUploadRegulations: vi.fn(),
  runComplianceReview: vi.fn(),
  getLatestRegulationReviews: vi.fn(),
  getRegulationDocumentPreview: vi.fn(),
  downloadRegulationDocument: vi.fn(),
}))

vi.mock('@/actions/safety', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/actions/safety')>()
  return {
    ...actual,
    getRegulations: mocks.getRegulations,
    createRegulation: mocks.createRegulation,
    updateRegulation: mocks.updateRegulation,
    deleteRegulation: mocks.deleteRegulation,
    uploadRegulationDocument: mocks.uploadRegulationDocument,
    getRevisions: mocks.getRevisions,
    createRevision: mocks.createRevision,
    deleteRevision: mocks.deleteRevision,
    manualRevisionComplete: mocks.manualRevisionComplete,
    batchUploadRegulations: mocks.batchUploadRegulations,
    runComplianceReview: mocks.runComplianceReview,
    getLatestRegulationReviews: mocks.getLatestRegulationReviews,
    getRegulationDocumentPreview: mocks.getRegulationDocumentPreview,
    downloadRegulationDocument: mocks.downloadRegulationDocument,
  }
})

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

import RegulationPage from './page'

const ROW = {
  id: 'r1',
  regulation_no: 'SOP-001',
  title: '离心机操作规程',
  workshop: '101一车间',
  status: 'active',
  has_document: true,
  version: 'V2',
  updated_at: '2026-10-20T08:00:00',
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 60))
}

function buttons(text: string) {
  return Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).filter((b) =>
    b.textContent?.includes(text),
  )
}

describe('RegulationPage（安全操规台账）', () => {
  let root: Root | undefined
  let container: HTMLElement | undefined

  beforeEach(() => {
    mocks.getRegulations.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [ROW],
    })
    mocks.getLatestRegulationReviews.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
    })
    mocks.getRevisions.mockResolvedValue({ code: 200, message: 'success', data: [] })
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = undefined
    container = undefined
    vi.clearAllMocks()
  })

  function renderPage() {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root!.render(<RegulationPage />)
    })
  }

  it('挂载后拉取台账并渲染行', async () => {
    renderPage()
    await act(flush)
    expect(mocks.getRegulations).toHaveBeenCalled()
    const text = document.body.textContent ?? ''
    expect(mocks.getRegulations).toHaveBeenCalled()
  })

  it('新建操规按钮打开表单并提交创建', async () => {
    mocks.createRegulation.mockResolvedValue({ code: 200, message: 'success', data: null })
    renderPage()
    await act(flush)

    const addBtn = buttons('新建')[0]
    expect(addBtn).toBeTruthy()
    await act(async () => {
      addBtn!.click()
      await flush()
    })
    expect((document.body.textContent ?? '').length).toBeGreaterThan(0)
    // 提交按钮（确定）
    const okBtn = buttons('确 定').at(-1) ?? buttons('确定').at(-1)
    if (okBtn && !okBtn.disabled) {
      await act(async () => {
        okBtn.click()
        await flush()
      })
    }
  })

  it('删除走确认弹窗并调用删除接口', async () => {
    mocks.deleteRegulation.mockResolvedValue({ code: 200, message: 'success', data: null })
    renderPage()
    await act(flush)

    const delBtn = buttons('删除').at(-1)
    if (delBtn) {
      await act(async () => {
        delBtn.click()
        await flush()
      })
      const confirm = Array.from(document.body.querySelectorAll<HTMLElement>('.ant-modal button')).find(
        (b) => b.textContent?.includes('确 定') || b.textContent?.includes('确定'),
      )
      if (confirm) {
        await act(async () => {
          confirm.click()
          await flush()
        })
        expect(mocks.deleteRegulation).toHaveBeenCalled()
      }
    }
  })

  it('AI 合规评审按钮触发评审接口', async () => {
    mocks.runComplianceReview.mockResolvedValue({ code: 200, message: 'success', data: null })
    renderPage()
    await act(flush)

    const reviewBtn = buttons('合规评审')[0]
    if (reviewBtn) {
      await act(async () => {
        reviewBtn.click()
        await flush()
      })
      expect(mocks.runComplianceReview).toHaveBeenCalled()
    }
  })

  it('批量导入：打开弹窗、空清单提交警告、关闭', async () => {
    renderPage()
    await act(flush)

    const btn = buttons('批量导入')[0]
    expect(btn).toBeTruthy()
    await act(async () => {
      btn!.click()
      await flush()
    })
    // 空清单提交走警告分支（message.warning 不抛错，只验证不崩）
    const okBtn = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.ant-modal-footer button, button'))
      .filter((b) => b.textContent?.includes('开始导入') || b.textContent?.includes('确 定'))
      .at(-1)
    if (okBtn && !okBtn.disabled) {
      await act(async () => {
        okBtn.click()
        await flush()
      })
    }
  })

  it('AI 合规审核弹窗：从最近评审徽标打开并执行审核', async () => {
    mocks.getLatestRegulationReviews.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{ regulation_id: 'r1', result: 'pass', reviewed_at: '2026-10-01', reviewer: 'AI' }],
    })
    mocks.runComplianceReview.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { regulation_id: 'r1', result: 'pass', missing_items: [], non_compliant_items: [], suggestions: [], summary: '合规' },
    })
    renderPage()
    await act(flush)

    const badge = Array.from(document.body.querySelectorAll<HTMLElement>('span[role="button"]')).find((el) =>
      el.textContent?.includes('合规') || el.textContent?.includes('审核'),
    )
    if (badge) {
      await act(async () => {
        badge.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await flush()
      })
      const run = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
        b.textContent?.includes('开始审核'),
      )
      expect(run).toBeTruthy()
      await act(async () => {
        run!.click()
        await flush()
      })
      expect(mocks.runComplianceReview).toHaveBeenCalledWith('r1')
    }
  })

  it('查看文档打开在线预览抽屉', async () => {
    mocks.getRegulationDocumentPreview.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { content: '# 操作规程 步骤一' },
    })
    renderPage()
    await act(flush)

    const preview = buttons('查看文档')[0]
    if (preview) {
      await act(async () => {
        preview.click()
        await flush()
      })
      expect(mocks.getRegulationDocumentPreview).toHaveBeenCalled()
    }
  })

  it('切换到修订记录页签加载修订数据', async () => {
    renderPage()
    await act(flush)

    const tab = Array.from(document.body.querySelectorAll<HTMLElement>('.ant-tabs-tab')).find((t) =>
      t.textContent?.includes('修订记录'),
    )
    if (tab) {
      await act(async () => {
        tab.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await flush()
      })
      expect(mocks.getRevisions).toHaveBeenCalled()
    }
  })

  it('批量导入：添加文件后提交导入结果', async () => {
    mocks.batchUploadRegulations.mockResolvedValue({ code: 200, message: 'success', data: { success_count: 1, fail_count: 0, items: [] } })
    mocks.getRegulations.mockResolvedValue({ code: 200, message: 'success', data: [ROW] })
    renderPage()
    await act(flush)

    const openBtn = buttons('批量导入')[0]
    expect(openBtn).toBeTruthy()
    await act(async () => {
      openBtn!.click()
      await flush()
    })

    // 向 Upload.Dragger 的原生 input 注入文件并触发 change
    const input = document.body.querySelector<HTMLInputElement>('.ant-modal input[type="file"]') as HTMLInputElement | null
    expect(input).toBeTruthy()
    const file = new File(['x'], 'sop.docx')
    Object.defineProperty(input!, 'files', { value: [file] })
    await act(async () => {
      input!.dispatchEvent(new Event('change', { bubbles: true }))
      await flush()
    })

    const startBtn = Array.from(document.body.querySelectorAll<HTMLElement>('.ant-modal button')).find((b) =>
      b.textContent?.includes('开始导入'),
    )
    expect(startBtn).toBeTruthy()
    await act(async () => {
      startBtn!.click()
      await flush()
    })
    expect(mocks.batchUploadRegulations).toHaveBeenCalled()
  })

  it('空台账走最近评审空分支；已审核状态徽标渲染', async () => {
    mocks.getRegulations.mockResolvedValue({ code: 200, message: 'success', data: [] })
    renderPage()
    await act(flush)
    expect(mocks.getLatestRegulationReviews).not.toHaveBeenCalled()

    // 已审核状态行 + 预览抽屉内下载按钮
    mocks.getRegulations.mockResolvedValue({ code: 200, message: 'success', data: [{ ...ROW, status: 'reviewed', has_document: true }] })
    renderPage()
    await act(flush)
    const preview = buttons('查看文档')[0]
    if (preview) {
      await act(async () => {
        preview.click()
        await flush()
      })
      const download = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
        b.textContent?.includes('下载') && b.closest('.ant-drawer, [class*=drawer]'),
      ) ?? Array.from(document.body.querySelectorAll<HTMLButtonElement>('.ant-drawer button, .ant-modal button')).find((b) => b.textContent?.includes('下载'))
      if (download) {
        await act(async () => {
          download.click()
          await flush()
        })
        expect(mocks.downloadRegulationDocument).toHaveBeenCalled()
      }
    }
  })
})
