import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import {
  buildFeishuLoginHref,
  getLoginErrorMessage,
  LoginPanel,
} from './LoginPanel'

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
})
