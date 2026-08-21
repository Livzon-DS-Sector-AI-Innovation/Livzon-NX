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
})