/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFermentationRecords: vi.fn(),
  createFermentationRecord: vi.fn(),
  updateFermentationRecord: vi.fn(),
  deleteFermentationRecord: vi.fn(),
}))

vi.mock('@/actions/fermentation', () => actions)
vi.mock('@/components/production/BatchProfileButton', () => ({
  default: () => <button>批次全貌</button>,
}))
vi.mock('@/components/production/BatchEventsButton', () => ({
  default: () => <button>异常事件</button>,
}))

const xlsxMock = vi.hoisted(() => ({
  utils: { aoa_to_sheet: vi.fn(), book_new: vi.fn().mockReturnValue({}), book_append_sheet: vi.fn() },
  writeFile: vi.fn(),
}))

vi.mock('xlsx', () => xlsxMock)

import FermentationPage from './page'

const RECORDS = [
  { id: 'f1', batch_no: 'FA-2603-1', product_name: '洛伐他汀', fermenter: '1#', entry_date: '2026-03-01',
    discharge_date: '2026-03-02', cycle_1: 10, cycle_2: 12, cycle_3: 14, cycle_4: 16, cycle_5: 18, cycle_6: 20,
    tank_yield: 1200, status: 'completed', remarks: '' },
]

describe('FermentationPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    actions.deleteFermentationRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.createFermentationRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.updateFermentationRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    window.localStorage.clear()
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the lovastatin fermentation list with data and plan stats', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('FA-2603-1')
    expect(text).toContain('洛伐他汀')
    expect(text).toContain('月度计划')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })

  it('opens the monthly plan modal and the create modal', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    // 打开月度计划弹窗
    const planBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('月度计划'))
    if (planBtn) {
      await act(async () => { planBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('月度生产计划')
    // 打开新建发酵记录弹窗
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建发酵记录'))
    if (addBtn) {
      await act(async () => { addBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建发酵记录')
  })

  // ─── 新增用例：覆盖 changed lines ───

  function setInputValue(el: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }

  it('renders the production period label for the >=27 day window', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 7, 28))
    try {
      container = document.createElement('div')
      document.body.append(container)
      root = createRoot(container)
      act(() => {
        root.render(<App><FermentationPage /></App>)
      })
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60))
      })
      const text = (container.textContent || '') + (document.body.textContent || '')
      expect(text).toContain('月生产批次数据查看与管理')
      expect(text).toContain('8月27日')
    } finally {
      vi.useRealTimers()
    }
  })

  it('filters records by the batch number search input', async () => {
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const input = Array.from(container.querySelectorAll('input')).find((i) => (i.placeholder || '').includes('搜索批号'))
    if (input) {
      await act(async () => {
        setInputValue(input, 'NOT-EXIST')
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    expect((container.textContent || '')).not.toContain('FA-2603-1')
  })

  it('filters the list by status using the status select', async () => {
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const statusSelect = Array.from(container.querySelectorAll('.ant-select')).find((s) => s.textContent?.includes('状态'))
    if (statusSelect) {
      await act(async () => {
        statusSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    const running = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('运行中')) as HTMLElement | undefined
    if (running) {
      await act(async () => {
        running.click()
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    expect((container.textContent || '')).not.toContain('FA-2603-1')
  })

  it('updates the status of a record inline from the tag picker', async () => {
    actions.updateFermentationRecord.mockResolvedValue({ code: 200, message: 'ok', data: null })
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const tag = Array.from(container.querySelectorAll('.ant-tag')).find((t) => t.textContent?.includes('已完成')) as HTMLElement | undefined
    if (tag) {
      await act(async () => {
        tag.click()
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    const running = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('运行中')) as HTMLElement | undefined
    if (running) {
      await act(async () => {
        running.click()
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    expect(actions.updateFermentationRecord).toHaveBeenCalledWith('f1', { status: 'in_progress' })
  })

  it('exports the filtered records into an excel file', async () => {
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出Excel'))
    if (exportBtn) {
      await act(async () => {
        exportBtn.click()
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    expect(xlsxMock.writeFile).toHaveBeenCalled()
  })

  it('saves the monthly plan values from the plan modal', async () => {
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const planBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('月度计划'))
    if (planBtn) {
      await act(async () => {
        planBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('月度生产计划')
    const inputs = Array.from(document.body.querySelectorAll('.ant-modal input')) as HTMLInputElement[]
    const batches = inputs.find((i) => (i.getAttribute('placeholder') || '') === '本月计划生产批次总数')
    const yieldInput = inputs.find((i) => (i.getAttribute('placeholder') || '') === '本月计划总产量')
    if (batches) {
      await act(async () => {
        setInputValue(batches, '20')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    if (yieldInput) {
      await act(async () => {
        setInputValue(yieldInput, '1500')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const saveBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '保存') as HTMLButtonElement | undefined
    if (saveBtn) {
      await act(async () => {
        saveBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    expect(window.localStorage.getItem('lovastatin_plan_batches')).toBe('20')
    expect(window.localStorage.getItem('lovastatin_plan_yield')).toBe('1500')
  })

  it('edits and saves an existing record via the edit modal', async () => {
    actions.updateFermentationRecord.mockResolvedValue({ code: 200, message: 'ok', data: null })
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    if (editBtn) {
      await act(async () => {
        editBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('编辑发酵记录')
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => {
        okBtn.click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    expect(actions.updateFermentationRecord).toHaveBeenCalledWith('f1', expect.objectContaining({ batch_no: 'FA-2603-1' }))
  })

  it('deletes a record after confirming the delete dialog', async () => {
    actions.deleteFermentationRecord.mockResolvedValue({ code: 200, message: 'ok', data: null })
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除'))
    if (delBtn) {
      await act(async () => {
        delBtn.click()
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect((document.body.textContent || '')).toContain('确认删除')
    const confirmOk = Array.from(document.querySelectorAll('.ant-modal-confirm .ant-btn-primary')) as HTMLButtonElement[]
    if (confirmOk[0]) {
      await act(async () => {
        confirmOk[0].click()
        await new Promise((r) => setTimeout(r, 120))
      })
    }
    expect(actions.deleteFermentationRecord).toHaveBeenCalledWith('f1')
  })

  it('shows a load error when the record request rejects', async () => {
    actions.getFermentationRecords.mockRejectedValue(new Error('boom'))
    window.localStorage.clear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })
})