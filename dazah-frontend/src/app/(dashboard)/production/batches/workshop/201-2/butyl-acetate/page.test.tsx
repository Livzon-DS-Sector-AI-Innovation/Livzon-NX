/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/MCSheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/MCTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import ButylAcetatePage from './page'

const RECORDS = {
  dates: ['2026-03-01', '2026-03-02'],
  equipment: ['1#储罐', '2#储罐'],
  matrix: {
    '1#储罐': { '2026-03-01': 100, '2026-03-02': 0 },
    '2#储罐': { '2026-03-01': null },
  },
  inbound: { '2026-03-01': 50, '2026-03-02': 60 },
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ButylAcetatePage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders the butyl acetate records ledger', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: RECORDS })))
    )

    act(() => {
      root.render(<ButylAcetatePage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('丁酯')
    expect(text).toContain('1#储罐')
    expect(text).toContain('乙酸丁酯台账')
  })
})
