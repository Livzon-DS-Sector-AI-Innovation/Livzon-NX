/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { Alert, Button, Card, ConfigProvider, Input, Modal, Table, theme } from 'antd'
import { expect, it } from 'vitest'
import { antdTheme, getAntdTheme } from './antd-theme'

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

it('derives dark semantic colors while preserving component sizes and readable surfaces', async () => {
  const config = getAntdTheme('dark')
  const token = theme.getDesignToken(config)
  expect(config.algorithm).toBe(theme.darkAlgorithm)
  expect(token.colorBgContainer).toBe('#222225')
  expect(token.colorText).toBe('#eeedf1')
  expect(token.controlHeight).toBe(44)
  expect(token.colorErrorBg).not.toBe(antdTheme.token?.colorErrorBg)
  expect(token.colorSuccessBg).not.toBe(antdTheme.token?.colorSuccessBg)
  expect(config.components?.Table?.headerBg).toBe(token.colorBgContainer)
  expect(config.components?.Tabs?.itemSelectedColor).toBe(token.colorText)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(createElement(ConfigProvider, { theme: config },
      createElement(Card, { title: '深色工作区' },
        createElement(Input, { placeholder: '输入内容' }),
        createElement(Button, { type: 'primary' }, '保存'),
        createElement(Table, { dataSource: [{ key: '1', name: '物料' }], columns: [{ title: '名称', dataIndex: 'name' }], pagination: false }),
        createElement(Modal, { open: true, title: '确认', footer: null }, '操作内容')))))
    expect(host.textContent).toContain('物料')
    expect(document.querySelector('.ant-modal')?.textContent).toContain('操作内容')
    const css = [...document.querySelectorAll('style')].map((style) => style.textContent).join('')
    expect(css).toContain('--ant-color-bg-container:#222225')
    expect(css).toContain('--ant-color-text:#eeedf1')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
