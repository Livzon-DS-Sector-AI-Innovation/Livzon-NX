/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App as AntApp } from 'antd'

const storeMock = vi.hoisted(() => ({
  categories: [
    {
      id: 'cat-1',
      name: '反应设备',
      code: 'C1',
      parent_id: null,
      description: null,
      created_at: '',
      updated_at: '',
      created_by: null,
      updated_by: null,
    },
  ],
  locations: [
    {
      id: 'loc-1',
      name: '201二车间',
      code: 'L1',
      parent_id: null,
      description: null,
      created_at: '',
      updated_at: '',
      created_by: null,
      updated_by: null,
    },
  ],
}))

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => storeMock }))

import { buildImportFormData, EquipmentImportModal } from './EquipmentImportModal'

describe('buildImportFormData', () => {
  it('carries the file and default category/location fields', () => {
    const file = new File(['x'], 'ledger.xlsx', { type: 'application/octet-stream' })
    const formData = buildImportFormData(file, 'cat-1', 'loc-1')
    expect(formData.get('file')).toBe(file)
    expect(formData.get('default_category_id')).toBe('cat-1')
    expect(formData.get('default_location_id')).toBe('loc-1')
  })

  it('omits category and location when not provided (uncategorized import)', () => {
    const formData = buildImportFormData(new File(['x'], 'a.xlsx'))
    expect(formData.get('default_category_id')).toBeNull()
    expect(formData.get('default_location_id')).toBeNull()
  })
})

describe('EquipmentImportModal', () => {
  let container: HTMLDivElement
  let root: Root
  const onImported = vi.fn()
  const onClose = vi.fn()

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders upload area, defaults selectors and template link', () => {
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportModal open onClose={onClose} onImported={onImported} />
        </AntApp>,
      )
    })
    // antd Modal 通过 Portal 渲染到 document.body
    const text = document.body.textContent || ''
    expect(text).toContain('导入设备台账')
    expect(text).toContain('默认设备分类')
    expect(text).toContain('默认安装地点')
    expect(text).toContain('下载导入模板')
    expect(text).toContain('按设备编号增量导入')
    const templateLink = document.body.querySelector(
      'a[href="/api/v1/equipment/equipments/import-template"]',
    )
    expect(templateLink).not.toBeNull()
  })

  it('blocks submit without a file and never calls onImported', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportModal open onClose={onClose} onImported={onImported} />
        </AntApp>,
      )
    })
    const submitButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('开始导入'),
    )
    expect(submitButton).toBeTruthy()
    await act(async () => {
      submitButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(onImported).not.toHaveBeenCalled()
    expect(document.querySelector('.ant-message')?.textContent).toContain(
      '请先选择台账 .xlsx 文件',
    )
  })

  async function pickFile() {
    const input = document.body.querySelector(
      'input[type=file]',
    ) as HTMLInputElement | null
    expect(input).toBeTruthy()
    const file = new File(['bytes'], 'ledger.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input, 'files', { value: [file] })
    await act(async () => {
      input!.dispatchEvent(new Event('change', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  function findSubmitButton() {
    const button = Array.from(document.body.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('开始导入'),
    ) as HTMLButtonElement
    expect(button).toBeTruthy()
    return button
  }

  it('imports the ledger and renders the summary with failures', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            code: 200,
            data: {
              total_rows: 616,
              created: 257,
              updated: 1,
              failed: 3,
              flagged: 5,
              locations_created: 35,
              failures: [
                { row: 9, equipment_no: 'IMP-009', reason: '设备编号为空' },
              ],
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportModal open onClose={onClose} onImported={onImported} />
        </AntApp>,
      )
    })
    await pickFile()
    await act(async () => {
      findSubmitButton().dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const text = (document.body.textContent || '').replace(/\s/g, '')
    expect(text).toContain('共616行：新建257台、更新1台、失败3行')
    expect(text).toContain('新建位置35处')
    expect(text).toContain('第9行（IMP-009）：设备编号为空')
    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('surfaces backend import errors and keeps the modal open', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ code: 400, message: '文件不是有效的台账模板' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportModal open onClose={onClose} onImported={onImported} />
        </AntApp>,
      )
    })
    await pickFile()
    await act(async () => {
      findSubmitButton().dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(document.body.textContent).toContain('文件不是有效的台账模板')
    expect(onImported).not.toHaveBeenCalled()
  })

  it('reports network failures with a retry hint', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline'))))
    act(() => {
      root.render(
        <AntApp>
          <EquipmentImportModal open onClose={onClose} onImported={onImported} />
        </AntApp>,
      )
    })
    await pickFile()
    await act(async () => {
      findSubmitButton().dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(document.body.textContent).toContain('导入失败，请稍后重试')
  })
})
