/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LineStatusConfirmModal from './line-status-confirm-modal'

const actions = vi.hoisted(() => ({
  getLineHaltEvents: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

describe('LineStatusConfirmModal', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getLineHaltEvents.mockResolvedValue({ code: 200, data: { events: [] } })
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
    onConfirm?: (reason: string) => void
    onCancel?: () => void
    onOpenHistory?: () => void
  }) {
    act(() => {
      root.render(
        <LineStatusConfirmModal
          productName="霉酚酸"
          productCode="MC"
          pendingHalted={props.pendingHalted}
          onConfirm={props.onConfirm ?? vi.fn()}
          onCancel={props.onCancel ?? vi.fn()}
          onOpenHistory={props.onOpenHistory ?? vi.fn()}
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

  it('keeps confirm disabled until countdown ends AND a reason is entered', async () => {
    vi.useFakeTimers()
    try {
      const onConfirm = vi.fn()
      act(() => {
        root.render(
          <LineStatusConfirmModal
            productName="霉酚酸"
            productCode="MC"
            pendingHalted={true}
            onConfirm={onConfirm}
            onCancel={() => {}}
            onOpenHistory={() => {}}
          />,
        )
      })
      const okOf = () =>
        document.body.querySelector(
          '.ant-modal .ant-btn-primary',
        ) as HTMLButtonElement | null
      // 倒计时结束但原因未填：确认仍禁用，并出现红字提示
      for (let i = 0; i < 8; i++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(1100)
        })
        if ((okOf()?.textContent || '').includes('确认（') === false) break
      }
      expect(okOf()?.disabled).toBe(true)
      expect(document.body.textContent || '').toContain('请填写原因后再确认')
      // 填入原因后才能确认
      const reasonInput = document.body.querySelector(
        '[data-testid="line-status-reason"]',
      ) as HTMLInputElement
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set
      await act(async () => {
        nativeSetter?.call(reasonInput, '检修滤芯')
        reasonInput.dispatchEvent(new Event('input', { bubbles: true }))
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(okOf()?.disabled).toBe(false)
      expect(document.body.textContent || '').not.toContain('请填写原因后再确认')
      // 全空白原因同样视为未填
      await act(async () => {
        nativeSetter?.call(reasonInput, '   ')
        reasonInput.dispatchEvent(new Event('input', { bubbles: true }))
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(okOf()?.disabled).toBe(true)
      await act(async () => {
        nativeSetter?.call(reasonInput, '检修滤芯')
        reasonInput.dispatchEvent(new Event('input', { bubbles: true }))
        await vi.advanceTimersByTimeAsync(100)
      })
      await act(async () => {
        okOf()!.click()
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(onConfirm).toHaveBeenCalledWith('检修滤芯')
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

  it('shows the latest event and a full-history link in the confirm modal', async () => {
    actions.getLineHaltEvents.mockResolvedValue({
      code: 200,
      data: {
        events: [
          {
            product_code: 'MC',
            halted: true,
            reason: '转产洛伐',
            operator_name: '张三',
            created_at: '2026-09-21T10:30:00',
          },
        ],
      },
    })
    const onConfirm = vi.fn()
    const onOpenHistory = vi.fn()
    vi.useFakeTimers()
    try {
      act(() => {
        root.render(
          <LineStatusConfirmModal
            productName="霉酚酸"
            productCode="MC"
            pendingHalted={true}
            onConfirm={onConfirm}
            onCancel={() => {}}
            onOpenHistory={onOpenHistory}
          />,
        )
      })
      // 先推进少量时间让最近事件请求的微任务落地
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })
      // 只取最近一条，长历史不进确认框（避免把按钮顶下去）
      expect(actions.getLineHaltEvents).toHaveBeenCalledWith('MC', 1)
      const body = document.body.textContent || ''
      expect(body).toContain('最近：2026-09-21 10:30　停产 · 转产洛伐 · 张三')
      expect(body).toContain('查看完整历史')
      // 链接打开独立历史弹窗，不触发确认
      const link = document.body.querySelector(
        '[data-testid="line-status-history-link"]',
      ) as HTMLElement
      await act(async () => {
        link.click()
        await vi.advanceTimersByTimeAsync(100)
      })
      expect(onOpenHistory).toHaveBeenCalled()
      expect(onConfirm).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})
