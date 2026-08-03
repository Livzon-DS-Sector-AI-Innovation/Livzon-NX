/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AuthCompletion,
  getAuthCompletionPresentation,
} from './AuthCompletion'

const routerReplace = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace }),
}))

vi.mock('./AuthLayout', () => ({
  AuthLayout: ({ children }: { children: ReactNode }) => children,
}))

describe('AuthCompletion', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.useFakeTimers()
    routerReplace.mockReset()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it.each([
    ['checking', '正在验证身份', '正在读取企业身份和访问权限，请稍候。'],
    ['ready', '身份验证成功', '企业身份和访问权限已确认。'],
    ['entering', '正在进入系统', '工作台准备完成，即将为你打开。'],
    ['error', '身份验证未完成', '请检查认证状态后重新登录。'],
  ] as const)(
    'provides clear user-facing copy for the %s state',
    (state, title, description) => {
      expect(getAuthCompletionPresentation(state)).toMatchObject({
        title,
        description,
      })
    },
  )

  it('renders the verification state and retries a failed identity check', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: vi.fn().mockResolvedValue(null),
    })
    vi.stubGlobal('fetch', fetchMock)

    act(() => root.render(<AuthCompletion nextPath="/production" />))
    expect(container.textContent).toContain('正在验证身份')

    await act(async () => {
      await vi.runOnlyPendingTimersAsync()
    })

    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      '登录状态未生效，请重新发起飞书认证。',
    )

    const retryButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '重新验证',
    )
    expect(retryButton).toBeDefined()

    await act(async () => {
      retryButton?.click()
      await Promise.resolve()
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
