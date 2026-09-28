/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { Alert, ConfigProvider } from 'antd'
import { expect, it } from 'vitest'
import { antdTheme } from './antd-theme'

it.each(['info', 'success', 'warning', 'error'] as const)('renders %s notices with the shared soft surface and a semantic icon', async (type) => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(createElement(ConfigProvider, { theme: antdTheme },
      createElement(Alert, { type, showIcon: true, title: '操作说明', description: '保留业务语义' }))))
    const css = [...document.querySelectorAll('style')].map((style) => style.textContent).join('')
    expect(host.querySelector(`.ant-alert-${type}`)).toBeTruthy()
    expect(host.querySelector('.ant-alert-icon')).toBeTruthy()
    expect(host.textContent).toContain('操作说明')
    expect(css.includes(`--ant-color-${type}-border:transparent`)).toBe(true)
    expect(css.includes('--ant-border-radius-lg:12px')).toBe(true)
    expect(css).toContain('--ant-alert-with-description-padding:16px 20px')
    expect(css.includes(`--ant-color-${type}-bg:`)).toBe(true)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
