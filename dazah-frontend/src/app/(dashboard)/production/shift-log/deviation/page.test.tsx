/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getNCEs: vi.fn(),
  createNCE: vi.fn(),
  updateNCE: vi.fn(),
  deleteNCE: vi.fn(),
}))

vi.mock('@/actions/nce', () => actions)

import DeviationPage from './page'

const RECORDS = [
  {
    id: 'nce-1',
    event_no: 'NCE-2603-1',
    title: '温度偏差',
    event_type: 'temperature',
    workshop: '101车间',
    event_time: '2026-03-01 10:00',
    description: '反应温度超上限',
    severity: 'major',
    status: 'open',
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ShiftLogDeviationPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getNCEs.mockResolvedValue({ code: 200, message: 'success', data: RECORDS, meta: { total: 1 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the deviation records ledger', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))))

    act(() => {
      root.render(<DeviationPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('反应温度超上限')
    expect(text).toContain('101车间')
    expect(actions.getNCEs).toHaveBeenCalled()
  })

  it('shows an error message when the deviation load fails with a non-success code', async () => {
    actions.getNCEs.mockResolvedValue({ code: 500, message: 'boom', data: [], meta: { total: 0 } })
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    expect((document.body.textContent || '')).toContain('加载失败')
    expect(actions.getNCEs).toHaveBeenCalled()
  })

  it('shows an error message when the deviation load rejects', async () => {
    actions.getNCEs.mockRejectedValue(new Error('network down'))
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    expect(actions.getNCEs).toHaveBeenCalled()
  })

  it('opens the create modal and validates required fields', async () => {
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    const newBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建事件'))
    await act(async () => { newBtn?.click(); await new Promise((r) => setTimeout(r, 80)) })
    expect((document.body.textContent || '')).toContain('新建事件')
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 150)) })
      expect((document.body.textContent || '')).toContain('请检查表单')
    }
  })

  it('edits and updates an NCE record', async () => {
    actions.updateNCE.mockResolvedValue({ code: 200, message: 'ok', data: null })
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑'))
    await act(async () => { editBtn?.click(); await new Promise((r) => setTimeout(r, 80)) })
    expect((document.body.textContent || '')).toContain('编辑事件')
    const okBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 150)) })
      expect(actions.updateNCE).toHaveBeenCalledWith('nce-1', expect.objectContaining({ event_type: 'temperature' }))
    }
  })

  it('deletes an NCE after confirming the dialog', async () => {
    actions.deleteNCE.mockResolvedValue({ code: 200, message: 'ok', data: null })
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除'))
    await act(async () => { delBtn?.click(); await new Promise((r) => setTimeout(r, 80)) })
    expect((document.body.textContent || '')).toContain('确认删除')
    const confirmOk = document.querySelector('.ant-modal-confirm .ant-btn-primary') as HTMLButtonElement | null
    await act(async () => { confirmOk?.click(); await new Promise((r) => setTimeout(r, 150)) })
    expect(actions.deleteNCE).toHaveBeenCalledWith('nce-1')
  })

  it('fetches and displays affected batches in the detail modal', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'ok', data: [{ id: 'b-1', fermenter_name: '1#罐', batch_no: '202A-2601', product_name: '霉酚酸', entry_date: '2026-03-01' }] }))))
    act(() => {
      root.render(<App><DeviationPage /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
    const detailBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    await act(async () => { detailBtn?.click(); await new Promise((r) => setTimeout(r, 150)) })
    expect((document.body.textContent || '')).toContain('事件详情')
    expect((document.body.textContent || '')).toContain('202A-2601')
    expect(globalThis.fetch).toHaveBeenCalled()
  })
})
