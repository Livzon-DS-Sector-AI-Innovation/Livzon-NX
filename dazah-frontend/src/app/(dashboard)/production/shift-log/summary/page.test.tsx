/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import SummaryPage from './page'

describe('ShiftLogSummaryPage', () => {
  let root: ReturnType<typeof createRoot>
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

  it('renders the shift-log summary page', () => {
    act(() => {
      root.render(<SummaryPage />)
    })
    const text = container.textContent || ''
    expect(text).toContain('班次运行摘要')
    expect(text).toContain('待开发')
  })
})