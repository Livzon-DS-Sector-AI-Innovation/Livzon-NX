/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import QualityPage from './page'

describe('ShiftLogQualityPage', () => {
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

  it('renders the shift quality info page', async () => {
    act(() => {
      root.render(<QualityPage />)
    })

    const text = container.textContent || ''
    expect(text.length).toBeGreaterThan(20)
  })
})
