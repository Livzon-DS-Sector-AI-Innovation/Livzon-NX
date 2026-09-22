/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import {
  buildFeishuLoginHref,
  getLoginErrorMessage,
  LoginPanel,
} from './LoginPanel'

vi.mock('./AuthLayout', () => ({
  AuthLayout: ({ children }: { children: ReactNode }) => children,
}))

describe('LoginPanel', () => {
  it('builds the Feishu login URL with an encoded completion destination', () => {
    expect(buildFeishuLoginHref('/quality?tab=todo')).toBe(
      '/auth/login?next=%2Flogin%2Fcomplete%3Fnext%3D%252Fquality%253Ftab%253Dtodo',
    )
  })

  it('keeps local access hidden when local login is disabled', () => {
    const markup = renderToStaticMarkup(
      <LoginPanel
        nextPath="/production"
        localLoginMode="disabled"
      />,
    )

    expect(markup).toContain('使用飞书企业账号登录')
    expect(markup).not.toContain('本地账号登录')
    expect(markup).not.toContain('管理员应急登录')
    expect(markup).not.toContain('name="username"')
  })

  it('shows a collapsed local login entry when local login is enabled', () => {
    const markup = renderToStaticMarkup(
      <LoginPanel nextPath="/production" localLoginMode="enabled" />,
    )

    expect(markup).toContain('本地账号登录')
    expect(markup).toContain('aria-expanded="false"')
    expect(markup).not.toContain('name="username"')
  })

  it('expands administrator recovery access for a local login error', () => {
    const markup = renderToStaticMarkup(
      <LoginPanel
        error="local_login_failed"
        nextPath="/quality"
        localLoginMode="admin_only"
      />,
    )

    expect(markup).toContain('管理员应急登录')
    expect(markup).toContain('aria-expanded="true"')
    expect(markup).toContain('账号或密码不正确，请重新输入。')
    expect(markup).toContain('普通本地账号无法登录')
    expect(markup).toContain('name="next" value="/quality"')
    expect(markup).toContain('name="username"')
    expect(markup).toContain('name="password"')
  })

  it('falls back to a generic message for an unknown error', () => {
    expect(getLoginErrorMessage('unexpected_error')).toBe(
      '登录失败，请重新尝试。',
    )
    expect(getLoginErrorMessage()).toBeNull()
  })

  it('starts Feishu authentication and expands local login on demand', () => {
    vi.useFakeTimers()
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)

    try {
      act(() => {
        root.render(
          <LoginPanel nextPath="/production" localLoginMode="enabled" />,
        )
      })

      const buttons = Array.from(container.querySelectorAll('button'))
      const feishuButton = buttons.find((button) =>
        button.textContent?.includes('使用飞书企业账号登录'),
      )
      const localLoginButton = buttons.find(
        (button) => button.textContent?.trim() === '▶本地账号登录',
      )

      expect(feishuButton).toBeDefined()
      expect(localLoginButton).toBeDefined()

      act(() => localLoginButton?.click())
      expect(localLoginButton?.getAttribute('aria-expanded')).toBe('true')
      expect(container.querySelector('input[name="username"]')).not.toBeNull()

      act(() => feishuButton?.click())
      expect(feishuButton?.disabled).toBe(true)
      expect(localLoginButton?.disabled).toBe(true)
      expect(feishuButton?.textContent).toContain('正在打开飞书认证')
      expect(container.querySelector('[role="status"]')?.textContent).toContain('正在前往飞书')

      act(() => window.dispatchEvent(new Event('pageshow')))
      expect(feishuButton?.disabled).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      act(() => root.unmount())
      container.remove()
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('navigates once, recovers after timeout and allows retry', () => {
    vi.useFakeTimers()
    const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => {})
    const container = document.createElement('div')
    const root = createRoot(container)
    try {
      act(() => root.render(<LoginPanel nextPath="/quality" localLoginMode="disabled" error="access_denied" />))
      const button = container.querySelector('button')!
      act(() => { button.click(); button.click() })
      expect(container.querySelector('[role="alert"]')).toBeNull()
      act(() => vi.advanceTimersByTime(240))
      expect(assign).toHaveBeenCalledExactlyOnceWith(buildFeishuLoginHref('/quality'))
      act(() => vi.advanceTimersByTime(12000))
      expect(button.disabled).toBe(false)
      expect(container.querySelector('[role="alert"]')?.textContent).toContain('检查网络后重试')
      act(() => button.click())
      expect(container.querySelector('[role="alert"]')).toBeNull()
      act(() => root.unmount())
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      assign.mockRestore()
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('keeps the local POST and fields intact while preventing duplicate submissions', () => {
    const container = document.createElement('div')
    const root = createRoot(container)
    try {
      act(() => root.render(<LoginPanel nextPath="/quality" localLoginMode="enabled" error="local_login_failed" />))
      const form = container.querySelector('form')!
      expect(form.getAttribute('action')).toBe('/auth/local-login')
      expect(form.getAttribute('method')).toBe('post')
      const first = new Event('submit', { bubbles: true, cancelable: true })
      const second = new Event('submit', { bubbles: true, cancelable: true })
      act(() => { form.dispatchEvent(first); form.dispatchEvent(second) })
      expect(first.defaultPrevented).toBe(false)
      expect(second.defaultPrevented).toBe(true)
      expect(container.querySelector('button[type="submit"]')?.textContent).toContain('正在验证账号')
      expect(container.querySelector<HTMLInputElement>('input[name="username"]')?.disabled).toBe(false)
      act(() => window.dispatchEvent(new Event('pageshow')))
      expect(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(false)
    } finally {
      act(() => root.unmount())
    }
  })
})
