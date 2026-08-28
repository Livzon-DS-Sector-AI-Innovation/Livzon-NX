/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import QualityPage from './page'

const flush = (ms = 80) => new Promise((r) => setTimeout(r, ms))

function setInputValue(el: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(el, value)
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

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
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(inputs[0], '1#罐')
        inputs[0].dispatchEvent(new Event('input', { bubbles: true }))
        await flush(20)
      })
    }
    const text = container.textContent || ''
    expect(text).toContain('中间体质控数据台账')
  })

  it('opens the seed IPC entry modal and adds rows', async () => {
    act(() => {
      root.render(<App><QualityPage /></App>)
    })
    const enterBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('录入数据'))
    await act(async () => { enterBtn?.click(); await flush(120) })
    expect((document.body.textContent || '')).toContain('种子 · IPC 数据录入')

    const dataRows = () =>
      Array.from(document.querySelectorAll('.ant-modal .ant-table-tbody tr')).filter((tr) => !tr.className.includes('measure')).length
    const initialRows = dataRows()
    const addBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '新增行') as HTMLButtonElement | undefined
    await act(async () => { addBtn?.click(); await flush(60) })
    expect(dataRows()).toBe(initialRows + 1)
  })

  it('opens the fermentation entry modal, navigates cells and deletes a row', async () => {
    act(() => {
      root.render(<App><QualityPage /></App>)
    })
    const enterBtns = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent?.includes('录入数据'))
    await act(async () => { enterBtns[1]?.click(); await flush(150) })
    expect((document.body.textContent || '')).toContain('发酵 · IPC 数据录入')

    const dataRows = () =>
      Array.from(document.querySelectorAll('.ant-modal .ant-table-tbody tr')).filter((tr) => !tr.className.includes('measure')).length

    const addBtn = Array.from(document.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.replace(/\s/g, '') === '新增行') as HTMLButtonElement | undefined
    await act(async () => { addBtn?.click(); await flush(60) })
    expect(dataRows()).toBe(2)

    const inputs = Array.from(document.querySelectorAll('.ant-modal input')) as HTMLInputElement[]
    await act(async () => {
      setInputValue(inputs[0], '2#罐')
      await flush(40)
      inputs[0].focus()
      inputs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
      await flush(40)
    })
    // 键盘导航应移动焦点到下一个输入框
    expect(document.activeElement).not.toBe(inputs[0])

    const before = dataRows()
    const deleteBtn = document.querySelector('.ant-modal .ant-btn-dangerous') as HTMLButtonElement | null
    await act(async () => { deleteBtn?.click(); await flush(80) })
    expect(dataRows()).toBe(before - 1)
  })
})