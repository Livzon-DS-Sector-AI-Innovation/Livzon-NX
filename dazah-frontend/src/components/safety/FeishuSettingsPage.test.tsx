/* @vitest-environment happy-dom */

import type { CSSProperties, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyFeishuSettings: vi.fn(async () => ({ code: 200, data: null })),
  saveSafetyFeishuSettings: vi.fn(async () => ({ code: 200, data: null })),
  testSafetyFeishuSettings: vi.fn(async () => ({ code: 200, data: null })),
  getSafetyFeishuWsStatus: vi.fn(async () => ({ code: 200, data: null })),
  restartSafetyFeishuWs: vi.fn(async () => ({ code: 200, data: null })),
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ApiOutlined: Icon,
    ArrowUpOutlined: Icon,
    ReloadOutlined: Icon,
    SaveOutlined: Icon,
    SecurityScanOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type Props = {
    children?: ReactNode
    style?: CSSProperties
    title?: ReactNode
    extra?: ReactNode
    placeholder?: string
  }

  const Box = ({ children, style, title, extra, placeholder }: Props) =>
    createElement(
      'div',
      { style, 'data-placeholder': placeholder },
      title,
      extra,
      children
    )
  const Text = ({ children, style }: Props) => createElement('span', { style }, children)
  const Title = ({ children, style }: Props) => createElement('h1', { style }, children)

  return {
    Alert: Box,
    App: { useApp: () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }) },
    Button: Box,
    Card: Box,
    Input: Object.assign(Box, { Password: Box }),
    Modal: Box,
    Space: Object.assign(Box, { Compact: Box }),
    Switch: Box,
    Tag: Text,
    Typography: { Paragraph: Text, Text, Title },
    theme: { useToken: () => ({ token: {} }) },
  }
})

import FeishuSettingsPage from './FeishuSettingsPage'

describe('FeishuSettingsPage', () => {
  it('渲染应用凭证、多维表格绑定与事件订阅三块配置', () => {
    const markup = renderToStaticMarkup(<FeishuSettingsPage initialSettings={null} initialWsStatus={null} />)

    expect(markup).toContain('飞书应用信息')
    expect(markup).toContain('App ID')
    expect(markup).toContain('App Secret')
    expect(markup).toContain('隐患多维表格绑定')
    expect(markup).toContain('飞书事件订阅（WebSocket）')
    expect(markup).toContain('保存配置')
    expect(markup).toContain('测试连接')
    expect(markup).toContain('重连事件订阅')
  })

  it('说明 Secret 掩码回显且留空保持不变', () => {
    const markup = renderToStaticMarkup(<FeishuSettingsPage initialSettings={null} initialWsStatus={null} />)

    expect(markup).toContain('留空则保持当前 Secret 不变')
    expect(markup).toContain('加密存储')
  })
})
