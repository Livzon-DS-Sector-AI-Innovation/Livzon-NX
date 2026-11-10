/* @vitest-environment happy-dom */
import React from 'react'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const businessMock = await (() => ({
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
  Button: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) =>
    React.createElement('button', { onClick }, children),
  Space: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
}))()
  return { ...actual, ...businessMock, Alert: actual.Alert, theme: actual.theme, Typography: actual.Typography }
})

describe('(dashboard) 全局错误边界', () => {
  it('渲染友好错误提示与重试按钮，而非默认崩溃页', async () => {
    const error = new Error('加载失败')
    ;(error as Error & { digest?: string }).digest = 'abc123'

    const { default: DashboardErrorPage } = await import('./error')
    const element = React.createElement(DashboardErrorPage, {
      error,
      retry: () => undefined,
    })
    const markup = renderToStaticMarkup(element)

    expect(markup).toContain('页面加载失败')
    expect(markup).toContain('加载失败')
    expect(markup).toContain('了解访问规则')
    expect(markup).toContain('重试')
    expect(markup).not.toContain('>刷新页面<')
  })

  it('不向用户展示英文运行时错误', async () => {
    const { default: DashboardErrorPage } = await import('./error')
    const markup = renderToStaticMarkup(React.createElement(DashboardErrorPage, {
      error: new Error('Failed to fetch'),
      retry: () => undefined,
    }))

    expect(markup).toContain('网络连接失败，请检查网络后重试')
    expect(markup).not.toContain('Failed to fetch')
  })

  it('通过路由错误边界重试而不重载浏览器文档', async () => {
    const { default: DashboardErrorPage } = await import('./error')
    const host = document.createElement('div')
    const root = createRoot(host)
    const retry = vi.fn()
    const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
    const logger = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      await act(async () => root.render(React.createElement(DashboardErrorPage, { error: new Error('加载失败'), retry })))
      const button = Array.from(host.querySelectorAll('button')).find(item => item.textContent === '重试')
      expect(button).toBeDefined()
      await act(async () => button?.click())
      expect(retry).toHaveBeenCalledOnce()
      expect(reload).not.toHaveBeenCalled()
    } finally {
      await act(async () => root.unmount())
      reload.mockRestore()
      logger.mockRestore()
    }
  })
})
