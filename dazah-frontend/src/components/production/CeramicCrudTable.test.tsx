/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CeramicCrudTable from './CeramicCrudTable'

const api = {
  list: vi.fn().mockResolvedValue({ code: 200, data: [{ id: 1, batch_no: 'CB-1' }] }),
  create: vi.fn().mockResolvedValue({ code: 200, data: {} }),
  update: vi.fn().mockResolvedValue({ code: 200, data: {} }),
  delete: vi.fn().mockResolvedValue({ code: 200, data: {} }),
}

const FORM_FIELDS = <div>表单</div>

describe('CeramicCrudTable', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the ceramic CRUD table with records', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><CeramicCrudTable api={api} columns={[{ title: '批号', dataIndex: 'batch_no' }]} searchField="batch_no" searchPlaceholder="搜索" formFields={FORM_FIELDS} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(api.list).toHaveBeenCalled()
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('CB-1')
  })

  it('renders empty when no records', async () => {
    api.list.mockResolvedValueOnce({ code: 200, data: [] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><CeramicCrudTable api={api} columns={[]} searchField="batch_no" searchPlaceholder="搜索" formFields={FORM_FIELDS} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('新建')
  })
})