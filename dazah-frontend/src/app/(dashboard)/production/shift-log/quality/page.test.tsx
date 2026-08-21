/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
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
      root.render(<App><QualityPage /></App>)
    })

    const text = container.textContent || ''
    expect(text).toContain('中间体质控数据台账')
    expect(text.length).toBeGreaterThan(20)
  })

  it('edits a cell value in the editable table', async () => {
    act(() => {
      root.render(<App><QualityPage /></App>)
    })
    const inputs = Array.from(container.querySelectorAll('input'))
    expect(inputs.length).toBeGreaterThan(0)
    // 修改首个输入框触发 handleCellChange
    if (inputs.length > 0) {
      await act(async () => {
        (inputs[0] as HTMLInputElement).value = '1#罐'
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 20))
      })
    }
    const text = container.textContent || ''
    expect(text).toContain('中间体质控数据台账')
  })
})
