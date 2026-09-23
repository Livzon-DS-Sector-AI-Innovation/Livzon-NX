/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { ResizableHeaderCell } from './ResizableTableHeader'

it('preserves fixed-column positioning while keeping the resize handle usable', async () => {
  const container = document.createElement('div')
  const root = createRoot(container)
  const resize = vi.fn()
  await act(async () => root.render(<table><thead><tr>
    <ResizableHeaderCell style={{ position: 'sticky', right: 0 }} width={220} resizable onResizeStart={resize}>操作</ResizableHeaderCell>
    <ResizableHeaderCell width={107}>偏差编号</ResizableHeaderCell>
  </tr></thead></table>))
  const cells = container.querySelectorAll('th')
  expect(cells[0].style.position).toBe('sticky')
  expect(cells[0].style.right).toBe('0px')
  expect(cells[1].style.position).toBe('')
  await act(async () => cells[0].querySelectorAll('div')[1].dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  expect(resize).toHaveBeenCalledOnce()
  await act(async () => root.unmount())
})
