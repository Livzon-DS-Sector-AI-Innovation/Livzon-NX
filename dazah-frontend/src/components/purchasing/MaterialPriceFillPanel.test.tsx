/* @vitest-environment happy-dom */
/**
 * 表格补价面板：真实 antd 渲染，mock 补价接口，验证上传识别、列映射与下载。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from 'antd'
import { MaterialPriceFillPanel } from './MaterialPriceFillPanel'

const actions = vi.hoisted(() => ({
  previewMaterialPriceFill: vi.fn(),
  generateMaterialPriceFill: vi.fn(),
}))

vi.mock('@/actions/purchasing', () => actions)

function mockMatchMedia() {
  window.matchMedia =
    window.matchMedia ??
    ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
}

function mockResizeObserver() {
  if (!(globalThis as any).ResizeObserver) {
    ;(globalThis as any).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

function previewResponse(overrides?: Record<string, unknown>) {
  return {
    code: 200,
    message: 'success',
    data: {
      mapping: {
        sheet_name: '申购单',
        header_row: 1,
        code_column: 1,
        name_column: 2,
        price_column: 3,
        quantity_column: null,
        amount_column: null,
      },
      total_rows: 3,
      matched_rows: 2,
      unmatched_rows: 1,
      headers: ['物料编码', '物料名称', '单价', '备注'],
      rows: [
        {
          row_number: 2,
          material_code: '51069308',
          material_name: '隔膜垫,DN15卫生级',
          matched_code: '51069308',
          matched_name: '隔膜垫,DN15卫生级',
          unit: '片',
          unit_price: '29.00',
          source: 'live',
          message: '仓储实时入库',
        },
        {
          row_number: 3,
          material_code: '',
          material_name: '查无此物',
          matched_code: null,
          matched_name: null,
          unit: '',
          unit_price: null,
          source: 'unmatched',
          message: '未匹配',
        },
      ],
    },
    ...overrides,
  }
}

function buildXlsxFile(name = '申购单.xlsx'): File {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

function triggerUpload(file: File) {
  const input = container.querySelector<HTMLInputElement>(
    'input[type="file"]',
  )
  expect(input).not.toBeNull()
  Object.defineProperty(input!, 'files', { value: [file] })
  act(() => {
    input!.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function flush(times = 3) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

let container: HTMLDivElement
let root: Root

beforeAll(() => {
  mockMatchMedia()
  mockResizeObserver()
})

beforeEach(() => {
  actions.previewMaterialPriceFill.mockReset()
  actions.generateMaterialPriceFill.mockReset()
  actions.previewMaterialPriceFill.mockResolvedValue(previewResponse())
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => {
    root.unmount()
  })
  container.remove()
})

function render() {
  act(() => {
    root.render(<App>{<MaterialPriceFillPanel />}</App>)
  })
}

describe('MaterialPriceFillPanel', () => {
  it('uploads a table, previews matched rows and shows column selectors', async () => {
    render()
    triggerUpload(buildXlsxFile())
    await flush()
    expect(actions.previewMaterialPriceFill).toHaveBeenCalledTimes(1)
    const text = container.textContent ?? ''
    expect(text).toContain('物料编码列')
    expect(text).toContain('已匹配')
    expect(text).toContain('51069308')
    // happy-dom 下 antd Tag 的可见文本不含前缀，来源标签只出现「实时入库」
    expect(text).toContain('实时入库')
    expect(text).toContain('查无此物')
  })

  it('rejects xls files before calling the API', async () => {
    render()
    triggerUpload(buildXlsxFile('老表格.xls'))
    await flush()
    expect(actions.previewMaterialPriceFill).not.toHaveBeenCalled()
  })

  it('shows the failure message when preview fails', async () => {
    actions.previewMaterialPriceFill.mockResolvedValue({
      code: 422,
      message: '未能识别物料列或单价列，请重新指定列映射',
      data: null,
    })
    render()
    triggerUpload(buildXlsxFile())
    await flush()
    expect(container.textContent).not.toContain('已匹配')
  })

  it('changes a column mapping and re-runs the preview', async () => {
    render()
    triggerUpload(buildXlsxFile())
    await flush()
    expect(actions.previewMaterialPriceFill).toHaveBeenCalledTimes(1)

    const selectInput = container.querySelector<HTMLInputElement>(
      '.ant-select input.ant-select-input, .ant-select input',
    )
    expect(selectInput).not.toBeNull()
    act(() => {
      selectInput?.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true }),
      )
    })
    await flush(2)
    const option = Array.from(
      document.querySelectorAll('.ant-select-item-option'),
    ).find((item) => item.textContent?.includes('2.'))
    expect(option).not.toBeNull()
    act(() => {
      option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(actions.previewMaterialPriceFill).toHaveBeenCalledTimes(2)
    const sent = actions.previewMaterialPriceFill.mock.calls[1][0] as FormData
    const mappingRaw = sent.get('mapping')
    expect(mappingRaw).toBeTruthy()
    const mapping = JSON.parse(String(mappingRaw))
    expect(mapping.code_column).toBe(2)
  })

  it('rejects oversized tables before calling the API', async () => {
    render()
    const file = buildXlsxFile('超大表格.xlsx')
    Object.defineProperty(file, "size", { value: 21 * 1024 * 1024 })
    triggerUpload(file)
    await flush()
    expect(actions.previewMaterialPriceFill).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('表格不能超过 20MB')
  })

  it('shows the failure message when generating fails', async () => {
    actions.generateMaterialPriceFill.mockResolvedValue({
      ok: false,
      message: '生成失败：服务器内部错误',
    })
    render()
    triggerUpload(buildXlsxFile())
    await flush()
    const button = Array.from(container.querySelectorAll('button')).find(
      (item) => item.textContent?.includes('生成并下载'),
    )
    await act(async () => {
      button?.click()
      await Promise.resolve()
    })
    await flush(2)
    expect(document.body.textContent).toContain('生成失败：服务器内部错误')
    expect(container.textContent).toContain('生成并下载')
  })

  it('reports a preview network failure', async () => {
    actions.previewMaterialPriceFill.mockRejectedValue(new Error("network down"))
    render()
    triggerUpload(buildXlsxFile())
    await flush()
    expect(document.body.textContent).toContain('表格解析失败，请稍后重试')
    expect(container.textContent).not.toContain('已匹配')
  })

  it('downloads the filled workbook with the filled count', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    ;(globalThis as any).URL.createObjectURL = createObjectURL
    ;(globalThis as any).URL.revokeObjectURL = revokeObjectURL
    actions.generateMaterialPriceFill.mockResolvedValue({
      ok: true,
      filename: '补价_申购单.xlsx',
      base64: 'UEsDBA==',
      filledCount: 2,
    })

    render()
    triggerUpload(buildXlsxFile())
    await flush(5)
    const button = Array.from(container.querySelectorAll('button')).find(
      (item) => item.textContent?.includes('生成并下载'),
    )
    expect(button).not.toBeNull()
    await act(async () => {
      button?.click()
      await Promise.resolve()
    })
    await flush(5)
    expect(actions.generateMaterialPriceFill.mock.calls.length).toBe(1)
    const sent = actions.generateMaterialPriceFill.mock.calls[0][0] as FormData
    expect(sent.get('only_blank')).toBe('true')
    expect(createObjectURL).toHaveBeenCalled()
    expect(document.body.textContent).toContain('已填入 2 个单元格')
  })
})