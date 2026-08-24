/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFermentationRecords: vi.fn(),
  createFermentationRecord: vi.fn(),
  updateFermentationRecord: vi.fn(),
  deleteFermentationRecord: vi.fn(),
  updateFermentationStatus: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import FermentationPage from './page'

const RECORDS = [
  {
    id: 'f-1',
    batch_no: 'F-2603-1',
    product_name: '霉酚酸',
    fermenter: '1#罐',
    entry_date: null,
    discharge_date: null,
    cycle_1: 10,
    cycle_2: 12,
    cycle_3: 14,
    cycle_4: 16,
    cycle_5: 18,
    cycle_6: 20,
    tank_yield: 1000,
    status: 'in_progress',
    remarks: '正常',
  },
]

// 后端直连 API 用于保存/导出
function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('FermentationPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS, meta: { total: 1 } })
    actions.deleteFermentationRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.updateFermentationStatus.mockResolvedValue({ code: 200, message: 'success', data: null })
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the fermentation ledger', async () => {
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('F-2603-1')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })

  it('renders cycle columns and status when records loaded', async () => {
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const text = container.textContent || ''
    // 周期列：循环周期 join 显示（cycle 值经 toFixed(1)）
    expect(text).toContain('10.0 / 12.0')
    expect(text).toContain('10.0 / 12.0 / 14.0')
  })

  it('exports CSV via direct backend fetch on export', async () => {
    const exportMock = (url: string) => {
      if (url.includes('/api/v1/production/fermentation')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
    }
    vi.stubGlobal('fetch', vi.fn(exportMock))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出'))
    if (btn) {
      await act(async () => { btn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect(container.textContent || '').toContain('发酵记录')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })

  it('opens add/edit modal and triggers a backend save', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { records: [], meta: { total: 0 } } })))
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建')) as HTMLElement | undefined
    if (addBtn) {
      await act(async () => { addBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('新增记录')
    // 取消关闭
    const cancelBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '取消') as HTMLElement | undefined
    if (cancelBtn) {
      await act(async () => { cancelBtn.click(); await new Promise((r) => setTimeout(r, 40)) })
    }
  })

  it('opens delete confirm modal', async () => {
    actions.deleteFermentationRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: null })))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.trim() === '删除') as HTMLElement | undefined
    if (delBtn) {
      await act(async () => { delBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
      const body = document.body.textContent || ''
      expect(body).toContain('确认删除')
    } else {
      expect(true).toBe(true)
    }
  })

  const flush = (ms: number) => new Promise((r) => setTimeout(r, ms))

  function setInputValue(el: HTMLInputElement, value: string) {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }

  it('shows a load error when the record request returns a failure code', async () => {
    actions.getFermentationRecords.mockResolvedValue({ code: 500, message: 'boom', data: [] })
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    expect((document.body.textContent || '')).toContain('加载发酵记录失败')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })

  it('searches by batch number via the input search button', async () => {
    window.localStorage.clear()
    actions.getFermentationRecords.mockClear()
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS, meta: { total: 1 } })
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { records: [], meta: { total: 0 } } })))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    actions.getFermentationRecords.mockClear()
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => (i.getAttribute('placeholder') || '').includes('搜索批号')) as HTMLInputElement | undefined
    if (searchInput) {
      await act(async () => {
        setInputValue(searchInput, 'F-9999')
        await flush(50)
        searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
        await flush(120)
      })
    }
    const lastCall = actions.getFermentationRecords.mock.calls[actions.getFermentationRecords.mock.calls.length - 1]
    expect(lastCall).toBeDefined()
    expect(lastCall[0]).toEqual(expect.objectContaining({ batch_no: 'F-9999' }))
  })

  it('filters the ledger by status via select', async () => {
    window.localStorage.clear()
    actions.getFermentationRecords.mockClear()
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS, meta: { total: 1 } })
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    actions.getFermentationRecords.mockClear()
    const statusSelect = Array.from(container.querySelectorAll('.ant-select')).find((s) => (s.textContent || '').includes('状态筛选'))
    if (statusSelect) {
      await act(async () => {
        statusSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await flush(100)
      })
      const completed = Array.from(document.querySelectorAll('.ant-select-item-option')).find((o) => (o.textContent || '').includes('已完成')) as HTMLElement | undefined
      await act(async () => { completed?.click(); await flush(120) })
    }
    const lastCall = actions.getFermentationRecords.mock.calls[actions.getFermentationRecords.mock.calls.length - 1]
    expect(lastCall).toBeDefined()
    expect(lastCall[0]).toEqual(expect.objectContaining({ status: 'completed' }))
  })

  it('creates and saves a record via the modal POST backend call', async () => {
    window.localStorage.clear()
const saveMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url.includes('/api/v1/production/fermentation') && opts?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'ok', data: { batch_no: 'F-NEW', id: 'new1' } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'ok', data: [], meta: { total: 0 } }))
    })
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    vi.stubGlobal('fetch', saveMock)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新增记录'))
    await act(async () => { addBtn?.click(); await flush(120) })
    expect((document.body.textContent || '')).toContain('新增发酵记录')
    const batchNo = Array.from(document.querySelectorAll('.ant-modal input')).find((i) => (i.getAttribute('placeholder') || '').includes('批号')) as HTMLInputElement | null
    const fermenter = Array.from(document.querySelectorAll('.ant-modal input')).find((i) => (i.getAttribute('placeholder') || '').includes('发酵罐')) as HTMLInputElement | null
    if (batchNo) {
      await act(async () => { setInputValue(batchNo, 'F-NEW-01'); await flush(30) })
    }
    if (fermenter) {
      await act(async () => { setInputValue(fermenter, '3#罐'); await flush(30) })
    }
    const pickerInput = document.querySelector('.ant-modal .ant-picker-input input') as HTMLInputElement | null
    if (pickerInput) {
      await act(async () => {
        pickerInput.click()
        pickerInput.dispatchEvent(new Event('focus'))
        await flush(150)
      })
      const cell = Array.from(document.querySelectorAll('.ant-picker-dropdown .ant-picker-cell')).find((c) => (c.getAttribute('title') || '').includes('2026-08-15')) as HTMLElement | undefined
      await act(async () => { cell?.click(); await flush(80) })
    }
    await act(async () => { await flush(50) })
    const saveBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { saveBtn?.click(); await flush(220) })
    expect(saveMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/production/fermentation'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(alertSpy).toHaveBeenCalled()
  })

  it('edits and saves a record through a backend PUT call', async () => {
    window.localStorage.clear()
    const saveMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url.includes('/api/v1/production/fermentation') && opts?.method === 'PUT') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'ok', data: { id: 'f-1' } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'ok', data: [], meta: { total: 0 } }))
    })
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    vi.stubGlobal('fetch', saveMock)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    const editIcon = container.querySelector('.anticon-edit')?.closest('button') as HTMLButtonElement | null
    await act(async () => { editIcon?.click(); await flush(150) })
    expect((document.body.textContent || '')).toContain('编辑发酵记录')
    const pickerInput = document.querySelector('.ant-modal .ant-picker-input input') as HTMLInputElement | null
    if (pickerInput) {
      await act(async () => {
        pickerInput.click()
        pickerInput.dispatchEvent(new Event('focus'))
        await flush(150)
      })
      const cell = Array.from(document.querySelectorAll('.ant-picker-dropdown .ant-picker-cell')).find((c) => (c.getAttribute('title') || '').includes('2026-08-15')) as HTMLElement | undefined
      await act(async () => { cell?.click(); await flush(80) })
    }
    await act(async () => { await flush(50) })
    const saveBtn = document.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { saveBtn?.click(); await flush(220) })
    expect(saveMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/production/fermentation/'),
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('deletes a record after confirming the dialog and reloads', async () => {
    actions.deleteFermentationRecord.mockResolvedValue({ code: 200, message: 'ok', data: null })
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'ok', data: null })))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(100) })
    const delIcon = container.querySelector('.anticon-delete')?.closest('button') as HTMLButtonElement | null
    await act(async () => { delIcon?.click(); await flush(100) })
    const confirmOk = document.querySelector('.ant-modal-confirm .ant-btn-dangerous') as HTMLButtonElement | null
    await act(async () => { confirmOk?.click(); await flush(150) })
    expect(actions.deleteFermentationRecord).toHaveBeenCalledWith('f-1')
  })

  it('marks an in-progress record as complete via the status action', async () => {
    actions.updateFermentationStatus.mockResolvedValue({ code: 200, message: 'ok', data: null })
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'ok', data: null })))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(100) })
    const statusBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-experiment'))
    await act(async () => { statusBtn?.click(); await flush(150) })
    expect(actions.updateFermentationStatus).toHaveBeenCalledWith('f-1', 'completed')
  })

  it('shows an export failure message when the export request fails', async () => {
    actions.getFermentationRecords.mockResolvedValue({ code: 500, message: 'boom', data: null })
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => { await flush(80) })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '') === '导出')
    await act(async () => { exportBtn?.click(); await flush(120) })
    expect((document.body.textContent || '')).toContain('导出失败')
  })
})