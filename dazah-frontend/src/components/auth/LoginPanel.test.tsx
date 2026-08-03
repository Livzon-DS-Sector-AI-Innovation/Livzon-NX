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

      act(() => feishuButton?.click())
      expect(feishuButton?.disabled).toBe(true)
      expect(feishuButton?.textContent).toContain('正在打开飞书认证')

      act(() => localLoginButton?.click())
      expect(localLoginButton?.getAttribute('aria-expanded')).toBe('true')
      expect(container.querySelector('input[name="username"]')).not.toBeNull()
    } finally {
      act(() => root.unmount())
      container.remove()
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })
})
