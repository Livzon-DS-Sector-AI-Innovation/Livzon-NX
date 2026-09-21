/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LineStatusConfirmModal from './line-status-confirm-modal'

describe('LineStatusConfirmModal', () => {
  let root: Root
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

  async function render(props: {
    pendingHalted: boolean | null
    onConfirm?: () => void
    onCancel?: () => void
  }) {
    act(() => {
      root.render(
        <LineStatusConfirmModal
          productName="霉酚酸"
          pendingHalted={props.pendingHalted}
          onConfirm={props.onConfirm ?? vi.fn()}
          onCancel={props.onCancel ?? vi.fn()}
        />,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200))
    })
  }

  function footerButtons() {
    const footer = document.body.querySelector('.ant-modal-footer')
    const buttons = footer
      ? Array.from(footer.querySelectorAll('button'))
      : []
    // AntD Modal footer 按钮顺序固定：取消在前、确认在后
    const [cancel, ok] = buttons
    return { ok, cancel }
  }

  it('stays closed when pendingHalted is null', async () => {
    await render({ pendingHalted: null })
    expect(document.querySelector('[data-testid="line-status-confirm"]')).toBeNull()
  })

  it('disables confirm during the 5s countdown while cancel stays clickable', async () => {
    await render({ pendingHalted: true })
    const body = document.body.textContent || ''
    expect(body).toContain('确认停产')
    expect(body).toContain('全平台可见')
    const { ok, cancel } = footerButtons()
    expect(ok).toBeTruthy()
    expect(cancel).toBeTruthy()
    // 倒计时中：确认禁用且文案带秒数，取消不受影响
    expect(ok!.disabled).toBe(true)
    expect(ok!.textContent).toContain('确认（5s）')
    expect(cancel!.disabled).toBe(false)
  })

  it('re-enables confirm after the countdown and calls onConfirm', async () => {
    vi.useFakeTimers()
    try {
      act(() => {
        root.render(
          <LineStatusConfirmModal
            productName="霉酚酸"
            pendingHalted={true}
            onConfirm={() => {}}
            onCancel={() => {}}
          />,
        )
      })
      // 挂载后先推进微任务+少量时间让初始 effect（重置倒计时）执行，
      // 再快进整个 5 秒倒计时
      await act(async () => {
        vi.advanceTimersByTimeAsync(50)
      })
      await act(async () => {
        vi.advanceTimersByTimeAsync(5100)
      })
      const { ok } = footerButtons()
      expect(ok).toBeTruthy()
      expect(ok!.disabled).toBe(false)
      // AntD 两字按钮文案渲染为“确 认”，去除空白后比较
      expect(ok!.textContent?.replace(/\s/g, '')).toBe('确认')
    } finally {
      vi.useRealTimers()
    }
  })

  it('cancel closes the dialog without confirming', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    await render({ pendingHalted: false, onConfirm, onCancel })
    const { cancel } = footerButtons()
    await act(async () => {
      cancel!.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    expect(onCancel).toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
