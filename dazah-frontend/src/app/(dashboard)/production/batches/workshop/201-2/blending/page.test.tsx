/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/Dashboard', () => ({
  default: () => <div data-testid="dashboard" />,
}))
vi.mock('@/components/production/MCSheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/MCTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import BlendingPage from './page'

const RECORD = {
  id: 'bl-1',
  batch_no: 'MC-BL-1',
  total_weight: 100,
  pack_spec: '25kg/桶',
  total_impurity: 0.4,
  content: 99.2,
  rrt_053: 0.02,
  rrt_201: 0.03,
  inputs: [
    {
      id: 'in-1',
      input_batch_no: 'MC-F2-1',
      input_weight: 50,
      rrt_053: 0.02,
      content: 99.2,
    },
  ],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/blending-records/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('BlendingPage', () => {
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

  it('renders the blending ledger with impurity columns', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<BlendingPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('混粉杂质计算')
    expect(text).toContain('MC-BL-1')
    expect(text).toContain('MC-F2-1')
    expect(text).toContain('新建混粉批次')
    expect(text).toContain('杂质标准')
  })
})
