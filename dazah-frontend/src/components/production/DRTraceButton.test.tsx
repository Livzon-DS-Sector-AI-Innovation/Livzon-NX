/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DRTraceButton from './DRTraceButton'

describe('DRTraceButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders DR trace button control', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTraceButton initialModule="second_refinement" /></App>)
    })
    expect(Array.from(container.querySelectorAll('button')).map((b) => b.title || '').join(' ')).toContain('追溯')
  })
})
