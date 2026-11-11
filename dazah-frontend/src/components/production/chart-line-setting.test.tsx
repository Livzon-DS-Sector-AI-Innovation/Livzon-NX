/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChartLineSetting from './ChartLineSetting'

// 警戒线配置入口：按钮开弹窗回显、保存回调、失败不关弹窗。

const onSave = vi.fn<(k: string, t: number) => Promise<boolean>>()

let container: HTMLDivElement
let root: Root

function renderHarness(override?: { onSave: typeof onSave }) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => {
    root.render(
      <App>
        <ChartLineSetting
          configs={[{ key: 'yield', label: '收率警戒线', unit: '%' }]}
          values={{ yield: 92 }}
          onSave={override?.onSave ?? onSave}
        />
      </App>,
    )
  })
  act(() => { void Promise.resolve() })
}

function queryButton(text: string): HTMLElement | undefined {
  return [...document.querySelectorAll('button')].find((b) =>
    (b.textContent || '').trim().includes(text),
  )
}

function visibleModal(): HTMLElement | null {
  const modals = [...document.querySelectorAll('.ant-modal')] as HTMLElement[]
  // happy-dom 关闭动画不结束旧弹窗会残留，取最后一个可见弹窗
  return modals.filter((m) => m.offsetParent !== null).at(-1) ?? null
}

function modalOkButton(): HTMLButtonElement | undefined {
  const modal = visibleModal()
  const btns = [...(modal?.querySelectorAll('button') ?? [])]
  return (btns.find((b) => (b.textContent || '').includes('保 存')) ??
    btns.find((b) => (b.textContent || '').trim() === '保存') ??
    [...(modal?.querySelectorAll('button.ant-btn-primary') ?? [])].at(-1)) as
    | HTMLButtonElement
    | undefined
}

beforeEach(() => {
  onSave.mockReset().mockResolvedValue(true)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('ChartLineSetting', () => {
  it('按钮打开弹窗并回显当前线值', async () => {
    renderHarness()
    expect(visibleModal()).toBeNull()
    act(() => { queryButton('警戒线')?.click() })
    await act(async () => { await Promise.resolve() })
    expect(visibleModal()?.querySelector('.ant-modal-title')?.textContent).toContain('警戒线配置')
    const input = visibleModal()?.querySelector(
      'input.ant-input-number-input',
    ) as HTMLInputElement
    expect(input.value).toBe('92')
  })

  it('保存调用 onSave 一次', async () => {
    renderHarness()
    act(() => { queryButton('警戒线')?.click() })
    await act(async () => { await Promise.resolve() })
    const ok = modalOkButton()
    await act(async () => { ok?.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith('yield', 92)
  })

  it('保存失败不重复提交、弹窗仍在', async () => {
    const failing = vi.fn().mockResolvedValue(false)
    renderHarness({ onSave: failing })
    act(() => { queryButton('警戒线')?.click() })
    await act(async () => { await Promise.resolve() })
    const ok = modalOkButton()
    await act(async () => { ok?.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    expect(failing).toHaveBeenCalledTimes(1)
    expect(visibleModal()).not.toBeNull()
  })
})
