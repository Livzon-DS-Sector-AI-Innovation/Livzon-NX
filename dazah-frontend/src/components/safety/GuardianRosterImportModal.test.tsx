/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  parseGuardianRosterImport: vi.fn(),
  importGuardianRoster: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  parseGuardianRosterImport: mocks.parseGuardianRosterImport,
  importGuardianRoster: mocks.importGuardianRoster,
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  // Dragger 探测按钮：直调 beforeUpload 触发解析链
  const DraggerStub = (props: Record<string, unknown>) =>
    createElement(
      'div',
      null,
      props.children as ReactNode,
      createElement(
        'button',
        {
          type: 'button',
          'data-testid': 'dragger-probe',
          onClick: () => {
            const file = new File(['x'], '监护人名单.xlsx') as File & { uid: string }
            file.uid = 'rc-1'
            ;(
              props as {
                beforeUpload?: (file: File) => unknown
              }
            ).beforeUpload?.(file)
          },
        },
        'probe-upload',
      ),
    )
  return {
    ...actual,
    Upload: Object.assign(DraggerStub, { Dragger: DraggerStub }),
    App: { useApp: () => ({ message: mocks.message }) },
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ImportOutlined: Icon, InboxOutlined: Icon }
})

import GuardianRosterImportModal from './GuardianRosterImportModal'

const PREVIEW = {
  sheets: [
    {
      sheet: '汇总',
      row_count: 3,
      workshops: ['101/102车间', '103车间'],
      default_selected: true,
      sample: [
        { person_name: '张三', workshop: '103车间', phone: '13800000000', position: '消毒', score: 85, exam_date: '2026-10-22' },
      ],
      errors: [],
    },
    {
      sheet: '103',
      row_count: 3,
      workshops: ['103车间'],
      default_selected: false,
      sample: [],
      errors: [],
    },
    {
      sheet: '说明',
      row_count: 0,
      default_selected: false,
      sample: [],
      errors: [],
    },
  ],
  duplicate_across_sheets: 3,
  current_total: 12,
  merged_total: 3,
}

const RESULT = {
  replaced: 12,
  imported: 3,
  duplicates_merged: 3,
  row_errors: [],
  archive_path: 'uploads/safety/guardian-import/x.xlsx',
}

let root: Root | undefined

function flush(ms = 40) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

beforeEach(() => {
  mocks.parseGuardianRosterImport.mockResolvedValue({
    code: 200,
    data: PREVIEW,
  })
  mocks.importGuardianRoster.mockResolvedValue({ code: 200, data: RESULT })
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
    root = undefined
  }
  document.body.replaceChildren()
  vi.clearAllMocks()
})

async function renderModal(
  handlers: { onClose?: () => void; onImported?: () => void } = {},
) {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <GuardianRosterImportModal
        open
        onClose={handlers.onClose ?? (() => {})}
        onImported={handlers.onImported ?? (() => {})}
      />,
    )
  })
  await flush()
}

async function probeUpload() {
  const probe = document.body.querySelector<HTMLButtonElement>(
    'button[data-testid="dragger-probe"]',
  )
  expect(probe).toBeTruthy()
  await act(async () => {
    probe!.click()
  })
  await flush()
}

describe('监护人名单导入弹窗', () => {
  it('上传后解析预览：默认勾选汇总子表且展示整表替换警示', async () => {
    await renderModal()
    expect(document.body.textContent).toContain('导入监护人考试合格名单')
    expect(document.body.textContent).toContain('导入将整表替换现有名单')
    await probeUpload()
    expect(mocks.parseGuardianRosterImport).toHaveBeenCalled()
    // 默认只勾选 default_selected 的汇总子表
    expect(document.body.textContent).toContain('汇总')
    expect(document.body.textContent).toContain('103')
    const importButton = buttons('导入选中子表并替换现有名单')[0]
    expect(importButton.disabled).toBe(false)
    // 0 行子表勾选框禁用
    const disabledBox = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ).find((n) => n.disabled)
    expect(disabledBox).toBeTruthy()
  })

  it('确认导入：携带选中子表、展示替换结果并触发 onImported', async () => {
    const onImported = vi.fn()
    await renderModal({ onImported })
    await probeUpload()
    await act(async () => {
      buttons('导入选中子表并替换现有名单')[0].click()
    })
    await flush()
    expect(mocks.importGuardianRoster).toHaveBeenCalledWith(
      expect.anything(),
      ['汇总'],
      'safety:ops-safety:guardian-roster',
    )
    expect(document.body.textContent).toContain(
      '本次写入 3 人，替换前原有 12 人',
    )
    expect(document.body.textContent).toContain('原始文件已存档')
    // 导入成功即触发 onImported（父面板刷新），不等关闭
    expect(onImported).toHaveBeenCalled()
  })

  it('解析失败提示错误且导入按钮保持禁用', async () => {
    mocks.parseGuardianRosterImport.mockResolvedValue({
      code: 422,
      message: '表格格式不识别',
    })
    await renderModal()
    await probeUpload()
    expect(mocks.message.error).toHaveBeenCalledWith('表格格式不识别')
    const importButton = buttons('导入选中子表并替换现有名单')[0]
    expect(importButton.disabled).toBe(true)
  })

  it('解析异常兜底提示', async () => {
    mocks.parseGuardianRosterImport.mockRejectedValue(new Error('down'))
    await renderModal()
    await probeUpload()
    expect(mocks.message.error).toHaveBeenCalledWith('解析失败，请稍后重试')
  })

  it('导入失败提示错误且不触发 onImported', async () => {
    const onImported = vi.fn()
    mocks.importGuardianRoster.mockResolvedValue({
      code: 500,
      message: '导入失败',
    })
    await renderModal({ onImported })
    await probeUpload()
    await act(async () => {
      buttons('导入选中子表并替换现有名单')[0].click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('导入失败')
    expect(onImported).not.toHaveBeenCalled()
  })

  it('取消关闭不触发 onImported', async () => {
    const onClose = vi.fn()
    const onImported = vi.fn()
    await renderModal({ onClose, onImported })
    await act(async () => {
      buttons('取消')[0].click()
    })
    await flush()
    expect(onClose).toHaveBeenCalled()
    expect(onImported).not.toHaveBeenCalled()
  })
})
