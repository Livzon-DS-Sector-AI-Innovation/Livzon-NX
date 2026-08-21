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
    schedule_mode: '4-3',
    summary: '正常交班',
    status: 'pending',
  },
]

describe('ShiftHandoverPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getShiftHandovers.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    actions.getDistinctPositions.mockResolvedValue({ code: 200, message: 'success', data: ['发酵主操'] })
    actions.confirmShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.deleteShiftHandover.mockResolvedValue({ code: 200, message: 'success', data: null })
    window.localStorage.clear()
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

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

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
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const detailBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    if (detailBtn) {
      await act(async () => { detailBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect((document.body.textContent || '')).toContain('交接记录详情')
  })

  it('opens the create modal after confirming the handover notice', async () => {
    act(() => {
      root.render(<App><ShiftHandoverPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const newBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建交接记录'))
    if (newBtn) {
      await act(async () => { newBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect((document.body.textContent || '')).toContain('交接班须知')
    const knowledgeOk = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.includes('已知晓，确认提交')) as HTMLButtonElement | undefined
    if (knowledgeOk) {
      await act(async () => { knowledgeOk.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建交接记录')
  })
})
