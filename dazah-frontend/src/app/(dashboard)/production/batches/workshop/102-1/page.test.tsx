/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  { id: 'f1', batch_no: 'F-2026-01', product_name: '多拉菌素', fermenter: '1#', entry_date: '2026-03-01',
    discharge_date: '2026-03-02', cycle_1: 10, cycle_2: 12, cycle_3: 14, cycle_4: 16, cycle_5: 18, cycle_6: 20,
    tank_yield: 1200, status: 'completed', remarks: '' },
]

describe('FermentationPage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the doramectin fermentation list with data', async () => {
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
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
    expect(text).toContain('F-2026-01')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })
})
