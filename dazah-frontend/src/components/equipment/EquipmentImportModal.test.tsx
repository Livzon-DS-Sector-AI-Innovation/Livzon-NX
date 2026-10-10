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
})
