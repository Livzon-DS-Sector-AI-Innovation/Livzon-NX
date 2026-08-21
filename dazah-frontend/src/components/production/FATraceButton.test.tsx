/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import FATraceButton from './FATraceButton'

describe('FATraceButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders FA trace button control', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FATraceButton initialModule="fermentation" /></App>)
    })
    expect(Array.from(container.querySelectorAll('button')).map((b) => b.title || '').join(' ')).toContain('批次追溯')
  })
})
