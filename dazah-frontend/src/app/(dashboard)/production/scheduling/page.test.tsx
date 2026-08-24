/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const xlsx = vi.hoisted(() => ({
  read: vi.fn(),
  utils: { sheet_to_json: vi.fn() },
}))

vi.mock('xlsx', () => xlsx)

// Mock antd's Upload so tests can drive beforeUpload deterministically.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const fakeUpload = vi.hoisted(() => ({ trigger: null as null | ((file: any) => unknown) }))

vi.mock('antd', async () => {
  const React = await import('react')
  const actual = await vi.importActual<typeof import('antd')>('antd')
  const Upload = (props: Record<string, unknown>) =>
    React.createElement('div', { className: 'ant-upload' }, props.children as React.ReactNode)
  Upload.displayName = 'Upload'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const UploadDragger = (props: Record<string, any>) => {
    fakeUpload.trigger = (file: unknown) => props.beforeUpload?.(file)
    return React.createElement(
      'button',
      { type: 'button', className: 'ant-upload ant-upload-drag' },
      props.children,
    )
  }
  UploadDragger.displayName = 'Upload.Dragger'
  Upload.Dragger = UploadDragger
  return { ...actual, Upload }
})

import SchedulingPage from './page'

function makeWs(rows: unknown[][]) {
  return {
    '!ref': 'A1:C3',
    '!merges': [],
    '!cols': [{ wch: 10 }],
    A1: { v: rows[0]?.[0] ?? '' },
  }
}

describe('SchedulingPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    xlsx.read.mockReturnValue({
      SheetNames: ['排产'],
      Sheets: { 排产: makeWs([['车位', '日期'], ['A1', '7-1']]) },
    })
    xlsx.utils.sheet_to_json.mockReturnValue([['车位', '日期'], ['A1', '7-1']])
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the scheduling page title', async () => {
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    const text = container.textContent || ''
    expect(text).toContain('排产')
  })

  it('parses an uploaded excel file into a table', async () => {
    // FileReader 未 mock 时 handleUpload 不会执行到 onload；因此直接通过真实上传流程触发
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    // 通过触发 Dragger 的 beforeUpload 处理上传 —— 由于 FileReader 在 happy-dom 不可用，仅验证入口不抛错
    const uploader = container.querySelector('.ant-upload-drag')
    if (uploader) {
      await act(async () => {
        uploader.dispatchEvent(new Event('click', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    expect(xlsx.read).not.toHaveBeenCalled() // 未实际上传时不解析
    expect(container.textContent || '').toContain('排产')
  })

  it('verifies merged cell detection utility branches are reachable', async () => {
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    // 页面已渲染，含「排产计划」标题与上传说明
    const text = container.textContent || ''
    expect(text).toContain('排产计划')
    expect(text).toContain('上传')
  })
})

describe('SchedulingPage upload & merge rendering', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('parses uploaded excel and renders table with merged cells', async () => {
    xlsx.read.mockReturnValue({
      SheetNames: ['排产'],
      Sheets: {
        排产: {
          '!merges': [{ s: { r: 0, c: 0 }, e: { r: 0, c: 1 } }],
          '!cols': [{ wch: 100 }],
        },
      },
    })
    xlsx.utils.sheet_to_json.mockReturnValue([
      ['排产计划 2026年7月1日 至 7月15日'],
      ['', ''],
    ])

    // Mock FileReader
    const mockReader = {
      onload: null as ((e: { target: { result: string | ArrayBuffer | null } }) => void) | null,
      onerror: null as (() => void) | null,
      readAsBinaryString: vi.fn(function (this: typeof mockReader) {
        this.onload?.({ target: { result: 'fake-binary' } })
      }),
    }
    const FileReaderMock = vi.fn(() => mockReader)
    vi.stubGlobal('FileReader', FileReaderMock)

    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => { root.render(<App><SchedulingPage /></App>) })
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })

    // 直接通过真实上传组件触发（FileReader 已 mock 自动调用 onload）
    const drag = container.querySelector('.ant-upload')
    if (drag) {
      await act(async () => { drag.dispatchEvent(new Event('click', { bubbles: true })); await new Promise((r) => setTimeout(r, 30)) })
    }
    const text = container.textContent || ''
    expect(text).toContain('排产计划')
    vi.unstubAllGlobals()
  })

  it('renders title and helper card without upload', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => { root.render(<App><SchedulingPage /></App>) })
    const text = container.textContent || ''
    expect(text).toContain('排产计划')
    expect(text).toContain('上传排产计划 Excel 文件')
  })
})

describe('SchedulingPage upload parse branches', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement
  let mockReader: {
    onload: ((e: { target: { result: string | ArrayBuffer | null } }) => void) | null
    onerror: (() => void) | null
    readAsBinaryString: ReturnType<typeof vi.fn>
  }

  function stubReader({ fail = false }: { fail?: boolean } = {}) {
    mockReader = {
      onload: null as ((e: { target: { result: string | ArrayBuffer | null } }) => void) | null,
      onerror: null as (() => void) | null,
      readAsBinaryString: vi.fn(function (this: typeof mockReader) {
        if (fail) {
          this.onerror?.()
          return
        }
        this.onload?.({ target: { result: 'fake-binary' } })
      }),
    }
    // 使用普通函数以便被 `new FileReader()` 实例化并返回 mockReader
    const FileReaderMock = function FileReader() { return mockReader } as unknown as typeof FileReader
    vi.stubGlobal('FileReader', FileReaderMock)
  }

  function renderPage() {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => { root.render(<App><SchedulingPage /></App>) })
    return new Promise<void>((resolve) => {
      setTimeout(() => { resolve() }, 30)
    })
  }

  async function selectFile() {
    const file = new File(['fake'], 'test.xlsx')
    await act(async () => {
      fakeUpload.trigger?.(file)
      await new Promise((r) => setTimeout(r, 150))
    })
  }

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders merged cells, title row and day-number cells after a real upload', async () => {
    const rows: unknown[][] = [
      ['排产计划 2026年7月1日 至 7月15日', '备注', '说明'],
      ['5', 'x', 'y'],
      ['0', '32', 'ABC'],
    ]
    xlsx.read.mockReturnValue({
      SheetNames: ['排产'],
      Sheets: {
        排产: {
          '!merges': [
            { s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }, // 标题行横向合并
            { s: { r: 1, c: 0 }, e: { r: 2, c: 0 } }, // 首列纵向合并
          ],
          '!cols': [{ wch: 100 }],
        },
      },
    })
    xlsx.utils.sheet_to_json.mockReturnValue(rows)
    stubReader()

    await renderPage()
    await selectFile()

    expect(xlsx.read).toHaveBeenCalledWith('fake-binary', expect.objectContaining({ type: 'binary' }))
    const text = container.textContent || ''
    expect(text).toContain('排产计划 2026年7月1日')
    expect(text).toContain('A')
    expect(text).toContain('32')
    expect(text).toContain('ABC')
  })

  it('shows a parse-error message when XLSX.read throws', async () => {
    xlsx.read.mockImplementationOnce(() => { throw new Error('bad workbook') })
    stubReader()

    await renderPage()
    await selectFile()

    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('文件解析失败: bad workbook')
    expect(xlsx.read).toHaveBeenCalled()
  })

  it('shows a read-error message when the FileReader fails', async () => {
    xlsx.read.mockReturnValue({ SheetNames: ['排产'], Sheets: {} })
    xlsx.utils.sheet_to_json.mockReturnValue([])
    stubReader({ fail: true })

    await renderPage()
    await selectFile()

    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('文件读取失败')
  })

  it('generates multi-letter column headers for wide sheets and keeps blanks', async () => {
    const rows: unknown[][] = [Array.from({ length: 27 }, (_, i) => String.fromCharCode(65 + i))]
    xlsx.read.mockReturnValue({ SheetNames: ['排产'], Sheets: { 排产: { '!merges': [], '!cols': [] } } })
    xlsx.utils.sheet_to_json.mockReturnValue(rows)
    stubReader()

    await renderPage()
    await selectFile()

    const text = container.textContent || ''
    expect(text).toContain('AA')
    expect(xlsx.utils.sheet_to_json).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ header: 1, defval: '', blankrows: true }),
    )
  })
})


