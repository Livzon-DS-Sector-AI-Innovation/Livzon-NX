/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MCTraceButton from './MCTraceButton'

describe('MCTraceButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders trace button control', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><MCTraceButton initialModule="sub_tank" /></App>)
    })
    // 追溯按钮 title 为 "追溯"
    expect(Array.from(container.querySelectorAll('button')).map((b) => b.title || '').join(' ')).toContain('追溯')
  })
})
