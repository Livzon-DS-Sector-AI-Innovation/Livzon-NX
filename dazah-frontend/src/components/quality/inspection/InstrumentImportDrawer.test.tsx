/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clientMocks = vi.hoisted(() => ({
  previewInstrumentImport: vi.fn(),
  confirmInstrumentImport: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => clientMocks)

import { InstrumentImportDrawer } from './InstrumentImportDrawer'

const PREVIEW = {
  file_name: '仪器台账.xlsx',
  create_count: 2,
  update_count: 1,
  error_count: 0,
  skipped_empty: 0,
  unmatched_columns: ['备注'],
  person_unresolved: ['王五'],
  column_map: { device_no: '设备编号', name: '设备名称' },
  rows: [
    {
      row_number: 1,
      values: { '设备编号': 'EQUIP-01', '设备名称': '压片机' },
      warnings: [],
      error: null,
      mode: 'create',
    },
    {
      row_number: 2,
      values: { '设备编号': 'EQUIP-02', '设备名称': '包衣机' },
      warnings: [],
      error: null,
      mode: 'update',
    },
  ],
}

let container: HTMLDivElement
let root: Root

function makeFile(name = '仪器台账.xlsx'): File {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

function renderDrawer(overrides: { onSuccess?: () => void } = {}) {
  const props = { open: true, onClose: vi.fn(), onSuccess: vi.fn(), ...overrides }
  act(() => {
    root.render(
      <App>
        <InstrumentImportDrawer {...props} />
      </App>,
    )
  })
  return props
}

async function renderDrawerMounted(overrides: { onSuccess?: () => void } = {}) {
  const props = renderDrawer(overrides)
  await flush(60)
  return props
}

function selectFile(file: File) {
  const input = document.querySelector('#instrument-import-file-input') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  act(() => {
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

function clickButton(label: string) {
  const norm = label.replace(/\s+/g, '')
  const button = Array.from(document.querySelectorAll('button')).find(
    (item) => item.textContent?.replace(/\s+/g, '').includes(norm),
  ) as HTMLButtonElement | undefined
  act(() => {
    button?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function flush(ms = 30) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  clientMocks.previewInstrumentImport.mockResolvedValue(PREVIEW)
  clientMocks.confirmInstrumentImport.mockResolvedValue({
    created: 2,
    updated: 1,
    failed: 0,
    error_details: [],
  })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body
    .querySelectorAll('.ant-drawer, .ant-message')
    .forEach((node) => node.remove())
  vi.clearAllMocks()
})

describe('InstrumentImportDrawer', () => {
  it('previews the workbook then confirms the import', async () => {
    const props = await renderDrawerMounted()
    selectFile(makeFile())
    clickButton('预览数据')
    await flush()

    expect(clientMocks.previewInstrumentImport).toHaveBeenCalled()
    const text = document.body.textContent || ''
    expect(text).toContain('压片机')
    expect(text).toContain('包衣机')

    clickButton('确认导入')
    await flush()
    expect(clientMocks.confirmInstrumentImport).toHaveBeenCalled()
    expect(document.body.textContent).toContain('导入成功：新增 2 条、更新 1 条')
    expect(props.onSuccess).toHaveBeenCalled()
  })

  it('surfaces preview failures', async () => {
    clientMocks.previewInstrumentImport.mockRejectedValue(new Error('文件解析失败'))
    renderDrawer()
    selectFile(makeFile())
    clickButton('预览数据')
    await flush()
    expect(document.body.textContent).toContain('文件解析失败')
  })

  it('reports partial failures with the first error detail', async () => {
    clientMocks.confirmInstrumentImport.mockResolvedValue({
      created: 1,
      updated: 0,
      failed: 2,
      error_details: [{ row_number: 3, message: '资产编码重复' }],
    })
    renderDrawer()
    selectFile(makeFile())
    clickButton('预览数据')
    await flush()
    clickButton('确认导入')
    await flush()
    const text = document.body.textContent || ''
    expect(text).toContain('导入完成：新增 1 条、更新 0 条，失败 2 条')
    expect(text).toContain('第 3 行 资产编码重复')
  })

  it('closing the drawer resets state and calls onClose', async () => {
    const props = await renderDrawerMounted()
    selectFile(makeFile())
    await flush()
    clickButton('预览数据')
    await flush()
    clickButton('关闭')
    expect(props.onClose).toHaveBeenCalled()
  })

  it('shows import errors and keeps the drawer open', async () => {
    clientMocks.confirmInstrumentImport.mockRejectedValue(new Error('飞书写入超时'))
    const props = await renderDrawerMounted()
    selectFile(makeFile())
    clickButton('预览数据')
    await flush()
    clickButton('确认导入')
    await flush()
    expect(document.body.textContent).toContain('飞书写入超时')
    expect(props.onSuccess).not.toHaveBeenCalled()
  })
})