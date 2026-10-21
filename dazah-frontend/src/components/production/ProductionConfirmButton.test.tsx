/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProductionConfirmButton from './ProductionConfirmButton'

describe('ProductionConfirmButton', () => {
  let root: Root
  let container: HTMLDivElement
  const confirm = vi.fn<() => Promise<boolean | void>>()
  const tick = () => new Promise(resolve => setTimeout(resolve, 40))
  const dialog = () => document.querySelector<HTMLElement>('[role="dialog"]')
  const button = (label: string) => [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')]
    .find(el => el.textContent?.replace(/\s/g, '') === label)!

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    confirm.mockReset().mockResolvedValue(undefined)
  })
  afterEach(() => { act(() => root.unmount()); container.remove() })

  async function render(visible = true) {
    await act(async () => {
      root.render(<ConfigProvider theme={{ token: { motion: false } }}><App>
        {visible && <ProductionConfirmButton title="删除测试记录？" description="对象：FA-TEST。删除后不可恢复。"
          confirmText="删除" danger onConfirm={confirm}>删除入口</ProductionConfirmButton>}
      </App></ConfigProvider>)
      await tick()
    })
  }
  async function open() {
    await act(async () => { container.querySelector('button')!.click(); await tick() })
    expect(dialog()?.textContent).toContain('对象：FA-TEST')
  }

  it('opens a named dialog and cancellation never writes', async () => {
    await render(); await open()
    expect(dialog()?.getAttribute('aria-labelledby')).toBeTruthy()
    await act(async () => { button('取消').click(); await tick() })
    expect(dialog()).toBeNull()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('submits once, blocks cancellation while pending and closes after success', async () => {
    let finish!: () => void
    confirm.mockReturnValue(new Promise<void>(resolve => { finish = resolve }))
    await render(); await open()
    await act(async () => { button('删除').click(); button('删除').click(); await tick() })
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(button('取消').disabled).toBe(true)
    await act(async () => { finish(); await tick() })
    expect(dialog()).toBeNull()
  })

  it('preserves the target after a business failure and allows retry', async () => {
    confirm.mockResolvedValueOnce(false)
    await render(); await open()
    await act(async () => { button('删除').click(); await tick() })
    expect(dialog()?.textContent).toContain('FA-TEST')
    expect(button('取消').disabled).toBe(false)
    await act(async () => { button('删除').click(); await tick() })
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(dialog()).toBeNull()
  })

  it('shows request failure and retains the dialog for retry', async () => {
    confirm.mockRejectedValueOnce(new Error('offline'))
    await render(); await open()
    await act(async () => { button('删除').click(); await tick() })
    expect(document.body.textContent).toContain('操作请求失败，请重试')
    expect(dialog()?.textContent).toContain('FA-TEST')
    expect(button('取消').disabled).toBe(false)
  })

  it('removes an open dialog when its permission-controlled trigger unmounts', async () => {
    await render(); await open(); await render(false)
    expect(dialog()).toBeNull()
    expect(confirm).not.toHaveBeenCalled()
  })
})
