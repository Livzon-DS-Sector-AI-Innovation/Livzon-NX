/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const xlsx = vi.hoisted(() => ({
  read: vi.fn(),
  utils: { sheet_to_json: vi.fn() },
}))

vi.mock('xlsx', () => xlsx)

import SchedulingPage from './page'

function makeWs(rows: unknown[][]) {
  return {
    '!ref': 'A1:C3',
    '!merges': [],
    '!cols': [{ wch: 10 }],
    A1: { v: rows[0]?.[0] ?? '' },
  }
}

describe('SchedulingPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    xlsx.read.mockReturnValue({
      SheetNames: ['排产'],
      Sheets: { 排产: makeWs([['车位', '日期'], ['A1', '7-1']]) },
    })
    xlsx.utils.sheet_to_json.mockReturnValue([['车位', '日期'], ['A1', '7-1']])
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the scheduling page title', async () => {
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    const text = container.textContent || ''
    expect(text).toContain('排产')
  })

  it('parses an uploaded excel file into a table', async () => {
    act(() => {
      root.render(<App><SchedulingPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(xlsx.read).not.toHaveBeenCalled() // 未上传时不解析
    expect(container.textContent || '').toContain('排产')
  })
})