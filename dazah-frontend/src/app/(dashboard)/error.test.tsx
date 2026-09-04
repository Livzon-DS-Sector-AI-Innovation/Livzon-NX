import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('antd', () => ({
  Alert: ({
    title,
    description,
  }: {
    title: React.ReactNode
    description: React.ReactNode
  }) =>
    React.createElement(
      'div',
      null,
      `alert:${String(title)}`,
      React.createElement('div', null, description)
    ),
  Button: ({ children }: { children: React.ReactNode }) =>
    React.createElement('button', null, children),
  Space: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
}))

describe('(dashboard) 全局错误边界', () => {
  it('渲染友好错误提示与重试按钮，而非默认崩溃页', async () => {
    const error = new Error('加载失败')
    ;(error as Error & { digest?: string }).digest = 'abc123'

    const { default: DashboardErrorPage } = await import('./error')
    const element = React.createElement(DashboardErrorPage, {
      error,
      unstable_retry: () => undefined,
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain('页面加载失败')
    expect(markup).toContain('加载失败')
    expect(markup).toContain('abc123')
    expect(markup).toContain('重试')
    expect(markup).toContain('刷新页面')
  })
})
