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

import QcInspectionPage from './page'

const RECORD = {
  id: 'qc-1',
  input_date: '2026-03-01',
  batch_no: 'MC-QC-1',
  pack_spec: '25kg/桶',
  warehouse_weight: 99.5,
  barrel_count: '4',
  inspection_std: '内控标准',
  front_batch_no: 'MC-QT-1',
  cumulative_weight: 99.5,
  inputs: [
    {
      id: 'in-1',
      input_batch: 'MC-BL-1',
      dry_weight: 50,
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
  if (url.includes('/qc-inspections/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('QcInspectionPage', () => {
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

  it('renders the qc inspection ledger with input rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<QcInspectionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('混粉入库')
    expect(text).toContain('MC-QC-1')
    expect(text).toContain('MC-BL-1')
    expect(text).toContain('MC-QT-1')
  })
})
