/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  previewOotLimitImport: vi.fn(),
  confirmOotLimitImport: vi.fn(),
}))

vi.mock('@/actions/quality', () => mocks)

import { OotLimitImportDrawer } from './OotLimitImportDrawer'

const PREVIEW_OK = [
  {
    filename: '2026 洛伐他汀OOT限度通知单.docx',
    status: 'ok' as const,
    mode: 'update' as const,
    matched_product_code: 'P01',
    product_name: '洛伐他汀',
    document_year: '2026',
    item_count: 12,
    warnings: ['第 3 行单位为空'],
    row_errors: [],
  },
]

const PREVIEW_ERROR = [
  {
    filename: '损坏文件.docx',
    status: 'error' as const,
    error: '无法解析文档结构',
  },
]

let container: HTMLElement
let root: Root

function makeFile(name: string): File {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
}

function renderDrawer(overrides: { onClose?: () => void; onSuccess?: () => void } = {}) {
  const props = { isOpen: true, onClose: vi.fn(), onSuccess: vi.fn(), ...overrides }
  act(() => {
    root.render(<OotLimitImportDrawer {...props} />)
  })
  return props
}

function selectFiles(names: string[]) {
  const input = document.querySelector('#oot-limit-import-file') as HTMLInputElement
  Object.defineProperty(input, 'files', {
    value: names.map(makeFile),
    configurable: true,
  })
  act(() => {
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

function clickButton(label: string) {
  const button = Array.from(document.querySelectorAll('button')).find(
    (item) => item.textContent?.replace(/\s+/g, '') === label,
  ) as HTMLButtonElement | undefined
  act(() => {
    button?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20))
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

describe('OotLimitImportDrawer', () => {
  it('rejects non-docx files with a clear message', async () => {
    renderDrawer()
    selectFiles(['说明.pdf', '告知单.docx'])
    expect(document.body.textContent).toContain('不是 Word 文档（.docx）：说明.pdf')
  })

  it('previews parsed results and confirms the import', async () => {
    mocks.previewOotLimitImport.mockResolvedValue({ files: PREVIEW_OK })
    mocks.confirmOotLimitImport.mockResolvedValue({
      created_count: 0,
      update_count: 1,
      error_count: 0,
    })
    const props = renderDrawer()

    selectFiles(['2026 洛伐他汀OOT限度通知单.docx'])
    clickButton('预览解析结果')
    await flush()

    expect(mocks.previewOotLimitImport).toHaveBeenCalled()
    expect(document.body.textContent).toContain('更新产品（P01）')
    expect(document.body.textContent).toContain('洛伐他汀')
    expect(document.body.textContent).toContain('限度 12 项')
    expect(document.body.textContent).toContain('第 3 行单位为空')

    clickButton('确认导入')
    await flush()
    expect(mocks.confirmOotLimitImport).toHaveBeenCalled()
    expect(document.body.textContent).toContain('导入完成：新建 0 个产品，更新 1 个产品')
  })

  it('shows fetch/parse failures from the preview step', async () => {
    mocks.previewOotLimitImport.mockRejectedValue(new Error('服务端解析超时'))
    renderDrawer()
    selectFiles(['a.docx'])
    clickButton('预览解析结果')
    await flush()
    expect(document.body.textContent).toContain('服务端解析超时')
  })

  it('disables confirm when every preview entry fails', async () => {
    mocks.previewOotLimitImport.mockResolvedValue({ files: PREVIEW_ERROR })
    const props = renderDrawer()
    selectFiles(['损坏文件.docx'])
    clickButton('预览解析结果')
    await flush()

    expect(document.body.textContent).toContain('无法解析文档结构')
    const confirmButton = Array.from(document.querySelectorAll('button')).find(
      (item) => item.textContent?.replace(/\s+/g, '') === '确认导入',
    ) as HTMLButtonElement
    expect(confirmButton.disabled).toBe(true)
    expect(props.onSuccess).not.toHaveBeenCalled()
  })

  it('surfaces import failures and keeps the drawer open', async () => {
    mocks.previewOotLimitImport.mockResolvedValue({ files: PREVIEW_OK })
    mocks.confirmOotLimitImport.mockRejectedValue(new Error('后端写入失败'))
    const props = renderDrawer()
    selectFiles(['a.docx'])
    clickButton('预览解析结果')
    await flush()
    clickButton('确认导入')
    await flush()

    expect(document.body.textContent).toContain('后端写入失败')
    expect(props.onClose).not.toHaveBeenCalled()
  })

  it('closes and invokes onSuccess after a finished import', async () => {
    mocks.previewOotLimitImport.mockResolvedValue({ files: PREVIEW_OK })
    mocks.confirmOotLimitImport.mockResolvedValue({
      created_count: 1,
      update_count: 0,
      error_count: 0,
    })
    const props = renderDrawer()
    selectFiles(['a.docx'])
    clickButton('预览解析结果')
    await flush()
    clickButton('确认导入')
    await flush()

    expect(document.body.textContent).toContain('导入完成')
    // 2.5s 后自动关闭并通知刷新
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2600))
    })
    expect(props.onClose).toHaveBeenCalled()
    expect(props.onSuccess).toHaveBeenCalled()
  })
})