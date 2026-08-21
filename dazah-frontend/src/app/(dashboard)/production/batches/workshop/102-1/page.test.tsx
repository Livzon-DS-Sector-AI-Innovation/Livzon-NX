/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
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

import FermentationPage from './page'

const RECORDS = [
  {
    id: 'f-1',
    batch_no: 'F-2026-01',
    product_name: '多拉菌素',
    fermenter: '1#罐',
    entry_date: '2026-03-01',
    discharge_date: '2026-03-10',
    status: 'completed',
    tank_yield: 1200,
    remarks: '',
  },
]

function renderPage() {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(<FermentationPage />)
  })
  return { root, container }
}

describe('FermentationPage (101-2)', () => {
  beforeEach(() => {
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders fermentation records in the ledger', async () => {
    const { root, container } = renderPage()

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('F-2026-01')
    expect(text).toContain('1#罐')
    expect(text).toContain('已完成')

    act(() => root.unmount())
    container?.remove()
  })
})
