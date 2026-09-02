/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const store: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (k: string) => store[k] ?? null,
  setItem: (k: string, v: string) => { store[k] = v },
  removeItem: (k: string) => { delete store[k] },
  clear: () => { Object.keys(store).forEach(k => delete store[k]) },
})

const actions = vi.hoisted(() => ({
  getShiftHandovers: vi.fn(),
  createShiftHandover: vi.fn(),
  updateShiftHandover: vi.fn(),
  deleteShiftHandover: vi.fn(),
  confirmShiftHandover: vi.fn(),
  getDistinctPositions: vi.fn(),
}))

vi.mock('@/actions/shift-handover', () => actions)

import ShiftHandoverPage from './page'

const RECORDS = [
  {
    id: 'sh-1',
    shift_date: '2026-03-01',
    position: '发酵主操',
    workshop: '101车间',
    handover_from: '张三',
    handover_to: '李四',
    handover_time: '2026-03-01 08:00:00',
    shift: 'day',
    schedule_mode: '4-3',
    summary: '正常交班',
    status: 'pending',
  },
]

const flush = (ms = 80) => new Promise((r) => setTimeout(r, ms))

function setInputValue(el: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(el, value)
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('ShiftHandoverPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getShiftHandovers.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    actions.getDistinctPositions.mockResolvedValue({ code: 200, message: 'success', data: ['发酵主操'] })
    actions.confirmShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.deleteShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.createShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.updateShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
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

  it('renders handover records with position filter', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })

    await act(async () => { await flush(50) })

    const text = container.textContent || ''
    expect(text).toContain('交接')
    expect(text).toContain('张三')
    expect(text).toContain('李四')
    expect(text).toContain('发酵主操')
    expect(actions.getShiftHandovers).toHaveBeenCalled()
    expect(actions.getDistinctPositions).toHaveBeenCalled()
  })

  it('opens the handover detail modal for a row', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(50) })
    const detailBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    if (detailBtn) {
      await act(async () => { detailBtn.click(); await flush(50) })
    }
    expect((document.body.textContent || '')).toContain('交接记录详情')
  })

  it('opens the create modal after confirming the handover notice', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(50) })
    const newBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建交接记录'))
    if (newBtn) {
      await act(async () => { newBtn.click(); await flush(50) })
    }
    expect((document.body.textContent || '')).toContain('交接班须知')
    const knowledgeOk = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.includes('已知晓，确认提交')) as HTMLButtonElement | undefined
    if (knowledgeOk) {
      await act(async () => { knowledgeOk.click(); await flush(60) })
    }
    expect((document.body.textContent || '')).toContain('新建交接记录')
  })

  it('shows an error message when the handover request fails with a non-success code', async () => {
    actions.getShiftHandovers.mockResolvedValue({ code: 500, message: 'boom', data: [] })
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    expect((document.body.textContent || '')).toContain('加载失败')
    expect(actions.getShiftHandovers).toHaveBeenCalled()
  })

  it('shows an error message when the handover request rejects', async () => {
    actions.getShiftHandovers.mockRejectedValue(new Error('network down'))
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    expect(actions.getShiftHandovers).toHaveBeenCalled()
  })

  it('cancels the handover notice dialog without opening the create form', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const newBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建交接记录'))
    await act(async () => { if (newBtn) { newBtn.click(); await flush(60) } })
    expect((document.body.textContent || '')).toContain('交接班须知')
    const cancelBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '取消') as HTMLButtonElement | undefined
    await act(async () => { if (cancelBtn) { cancelBtn.click(); await flush(200) } })
    // 取消后不会打开新建表单（notice 关闭，不会进入 create modal）
    expect(document.querySelector('.ant-modal .ant-form')).toBe(null)
    expect(actions.createShiftHandover).not.toHaveBeenCalled()
  })

  it('searches feishu users through autocomplete when creating a handover', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ code: 200, data: [{ name: '王五', department: '发酵车间' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const newBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建交接记录'))
    await act(async () => { if (newBtn) { newBtn.click(); await flush(60) } })
    const knowledgeOk = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.includes('已知晓，确认提交')) as HTMLButtonElement | undefined
    await act(async () => { if (knowledgeOk) { knowledgeOk.click(); await flush(120) } })
    const autos = Array.from(document.querySelectorAll('.ant-modal input[role="combobox"]')) as HTMLInputElement[]
    const autocomplete = autos[autos.length - 2]
    if (autocomplete) {
      await act(async () => {
        autocomplete.focus()
        setInputValue(autocomplete, '王')
        await flush(150)
      })
    }
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/search-users?q='), expect.anything())
  })

  it('edits and updates a handover record', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    await act(async () => { if (editBtn) { editBtn.click(); await flush(80) } })
    expect((document.body.textContent || '')).toContain('编辑交接记录')
    const submitBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '提交') as HTMLButtonElement | undefined
    await act(async () => { if (submitBtn) { submitBtn.click(); await flush(150) } })
    expect(actions.updateShiftHandover).toHaveBeenCalledWith('sh-1', expect.objectContaining({ position: '发酵主操' }))
  })

  it('deletes a handover record after confirming the dialog', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除'))
    await act(async () => { if (delBtn) { delBtn.click(); await flush(80) } })
    expect((document.body.textContent || '')).toContain('确认删除')
    const confirmOk = document.querySelector('.ant-modal-confirm .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { confirmOk?.click(); await flush(150) })
    expect(actions.deleteShiftHandover).toHaveBeenCalledWith('sh-1')
  })

  it('confirms shift handover after the notice countdown', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const confirmBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('确认接班'))
    await act(async () => { if (confirmBtn) { confirmBtn.click() } })
    await act(async () => { await flush(100) })
    expect((document.body.textContent || '')).toContain('交接班须知')
    await act(async () => { await flush(3300) })
    const modalOk = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '确认接班') as HTMLButtonElement | undefined
    await act(async () => { modalOk?.click(); await flush(150) })
    expect(actions.confirmShiftHandover).toHaveBeenCalledWith('sh-1')
  }, 15000)

  it('filters the list by position and queries again', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    const posSelect = Array.from(container.querySelectorAll('.ant-select')).find((s) => (s.textContent || '').includes('岗位'))
    if (posSelect) {
      await act(async () => {
        posSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await flush(100)
      })
      const opt = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('发酵主操')) as HTMLElement | undefined
      await act(async () => { opt?.click(); await flush(100) })
    }
    const queryBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('查询'))
    await act(async () => { queryBtn?.click(); await flush(100) })
    expect(actions.getShiftHandovers).toHaveBeenCalledWith(expect.objectContaining({ position: '发酵主操' }))
  })

  it('queries with a date range selected in the range picker', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => { await flush(80) })
    // 用当月日期定位面板单元格，避免默认面板月份导致目标日期格子不存在
    const nowDate = new Date()
    const year = nowDate.getFullYear()
    const month = String(nowDate.getMonth() + 1).padStart(2, '0')
    const dateFrom = `${year}-${month}-20`
    const dateTo = `${year}-${month}-22`
    const pickerInput = document.querySelector('.ant-picker-input input') as HTMLInputElement | null
    if (pickerInput) {
      await act(async () => {
        pickerInput.click()
        pickerInput.dispatchEvent(new Event('focus'))
        await flush(150)
      })
      const cells = Array.from(document.querySelectorAll('.ant-picker-dropdown .ant-picker-cell')).filter((c) => (c.getAttribute('title') || '').startsWith(`${year}-`))
      const first = cells.find((c) => c.getAttribute('title') === dateFrom) as HTMLElement | undefined
      const second = cells.find((c) => c.getAttribute('title') === dateTo) as HTMLElement | undefined
      await act(async () => { first?.click(); await flush(80) })
      await act(async () => { second?.click(); await flush(80) })
    }
    const queryBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('查询'))
    await act(async () => { queryBtn?.click(); await flush(100) })
    const calls = actions.getShiftHandovers.mock.calls
    const lastCall = calls[calls.length - 1]
    expect(lastCall).toBeDefined()
    expect(lastCall[0]).toEqual(expect.objectContaining({ date_from: dateFrom, date_to: dateTo }))
  })
})
