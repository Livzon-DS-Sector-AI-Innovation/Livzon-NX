/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
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
})
