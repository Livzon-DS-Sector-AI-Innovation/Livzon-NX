/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AuthCompletion,
  getAuthCompletionPresentation,
} from './AuthCompletion'

const { routerReplace, routerPrefetch, beginWorkspaceEntry, router } = vi.hoisted(() => {
  const routerReplace = vi.fn()
  const routerPrefetch = vi.fn()
  return { routerReplace, routerPrefetch, beginWorkspaceEntry: vi.fn(), router: { replace: routerReplace, prefetch: routerPrefetch } }
})

vi.mock('next/navigation', () => ({
  useRouter: () => router,
}))

vi.mock('./WorkspaceEntryTransition', () => ({
  useWorkspaceEntryTransition: () => beginWorkspaceEntry,
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
    routerPrefetch.mockReset()
    beginWorkspaceEntry.mockReset()
    Object.defineProperty(document, 'startViewTransition', { configurable: true, value: undefined })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    Reflect.deleteProperty(document, 'startViewTransition')
    vi.unstubAllGlobals()
  })

  it.each([
    ['checking', '正在验证身份', '正在读取企业身份和访问权限，请稍候。'],
    ['ready', '身份验证成功', '企业身份和访问权限已确认。'],
    ['entering', '身份验证成功', '正在为你打开工作台。'],
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
      '登录状态已失效，请返回登录后重试。',
    )

    const retryButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '重新验证',
    )
    expect(retryButton).toBeDefined()

    const loginButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('返回登录'),
    )
    expect(loginButton).toBeDefined()
    act(() => loginButton?.click())
    expect(routerReplace).toHaveBeenCalledWith('/login?next=%2Fproduction')

    await act(async () => {
      retryButton?.click()
      await Promise.resolve()
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(beginWorkspaceEntry).not.toHaveBeenCalled()
    expect(routerPrefetch).not.toHaveBeenCalled()
  })

  it('enters the first visible module after identity verification', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        data: {
          id: 'user-1',
          name: '普通用户',
          role: 'user',
          module_codes: ['quality', 'administration', 'research'],
          page_permissions: [{
            page_key: 'rd:project-initiation',
            module_code: 'research',
            permissions: ['access'],
          }],
          page_permission_rollouts: {},
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    act(() => root.render(<AuthCompletion nextPath="/production" />))

    await act(async () => {
      await vi.runAllTimersAsync()
    })

    expect(routerReplace).toHaveBeenCalledWith('/rd/project-initiation')
  })

  it('prefetches the authorized destination and retains the success screen for the route reveal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {
        id: 'energy-owner', name: '能源填报人', role: 'user',
        page_permissions: [{ page_key: 'energy:entry', module_code: 'energy', permissions: ['access'] }],
      } }),
    }))
    act(() => root.render(<AuthCompletion nextPath="/production" />))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(container.textContent).toContain('身份验证成功')
    expect(routerPrefetch).toHaveBeenCalledExactlyOnceWith('/energy/entry')
    expect(beginWorkspaceEntry).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(650) })
    expect(beginWorkspaceEntry).toHaveBeenCalledExactlyOnceWith('/energy/entry', expect.anything())
    const frame = renderToStaticMarkup(beginWorkspaceEntry.mock.calls[0][1])
    expect(frame).toContain('身份验证成功')
    expect(frame).toContain('能源填报人')
    expect(frame).not.toContain('正在打开工作台')
    expect(container.querySelector('[data-state="entering"]')).not.toBeNull()
    expect(routerReplace).toHaveBeenCalledExactlyOnceWith('/energy/entry')
  })

  it('cancels entry when the verification page unmounts before navigation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ data: { id: 'admin', role: 'admin' } }),
    }))
    act(() => root.render(<AuthCompletion nextPath="/production" />))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    act(() => root.render(null))
    await act(async () => { await vi.runAllTimersAsync() })
    expect(beginWorkspaceEntry).not.toHaveBeenCalled()
    expect(routerReplace).not.toHaveBeenCalled()
  })

  it('returns to an authorized energy task with its Feishu source after SSO', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {
        id: 'energy-owner', name: '填报人', role: 'user',
        page_permissions: [{ page_key: 'energy:entry', module_code: 'energy', permissions: ['access', 'query', 'operate'] }],
      } }),
    }))
    const target = '/energy/entry?task=11111111-1111-4111-8111-111111111111&source=feishu'
    act(() => root.render(<AuthCompletion nextPath={target} />))
    await act(async () => { await vi.runAllTimersAsync() })
    expect(routerReplace).toHaveBeenCalledWith(target)
  })

  it.each(['animated', 'hidden', 'unsupported', 'start-failed', 'hidden-during-capture'])(
    'enters the authorized page once without snapshot animation when the API is %s',
    async (scenario) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ data: {
          id: 'energy-owner', role: 'user',
          page_permissions: [{ page_key: 'energy:entry', module_code: 'energy', permissions: ['access'] }],
        } }),
      }))
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue(scenario === 'hidden' ? 'hidden' : 'visible')
      const start = vi.fn<Document['startViewTransition']>((callback) => {
        if (scenario === 'start-failed') throw new DOMException('Document hidden', 'InvalidStateError')
        // Visibility can change after the initial check. The browser still runs
        // the update callback, but rejects ready when it skips the animation.
        const updateCallbackDone = Promise.resolve().then(() => {
          if (typeof callback === 'function') return callback()
        })
        const ready = updateCallbackDone.then(() => {
          if (scenario === 'hidden-during-capture') {
            throw new DOMException('Transition was aborted because of invalid state. Document hidden', 'InvalidStateError')
          }
        })
        return { ready, updateCallbackDone, finished: updateCallbackDone, skipTransition: vi.fn(), types: new Set<string>() }
      })
      if (scenario !== 'unsupported') {
        Object.defineProperty(document, 'startViewTransition', { configurable: true, value: start })
      }

      act(() => root.render(<AuthCompletion nextPath="/energy/entry" />))
      await act(async () => { await vi.runAllTimersAsync() })

      expect(routerReplace).toHaveBeenCalledExactlyOnceWith('/energy/entry')
      expect(start).not.toHaveBeenCalled()
    },
  )

  it('offers recovery when identity verification never responds', async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}))
    vi.stubGlobal('fetch', fetchMock)
    act(() => root.render(<AuthCompletion nextPath="/production" />))
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    expect(container.textContent).toContain('身份验证未完成')
    expect(container.textContent).toContain('身份验证超时，请重新验证或返回登录。')
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true)
    expect(routerReplace).not.toHaveBeenCalled()
  })
})
