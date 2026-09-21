import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('antd', () => ({
  Alert: ({ title, description }: { title: React.ReactNode; description: React.ReactNode }) =>
    React.createElement('div', null, title, description),
  Button: ({ children }: { children: React.ReactNode }) => React.createElement('button', null, children),
  Space: ({ children }: { children: React.ReactNode }) => React.createElement('div', null, children),
}))

import EquipmentErrorPage from './error'
import AssetsErrorPage from './assets/error'

describe('equipment error pages', () => {
  it.each([
    ['设备模块加载失败', EquipmentErrorPage],
    ['设备台账加载失败', AssetsErrorPage],
  ])('shows a Chinese recovery message on %s', (title, ErrorPage) => {
    const markup = renderToStaticMarkup(React.createElement(ErrorPage, {
      error: new Error('Failed to fetch'),
      unstable_retry: () => undefined,
    }))

    expect(markup).toContain(title)
    expect(markup).toContain('网络连接失败，请检查网络后重试')
    expect(markup).toContain('重试')
    expect(markup).not.toContain('Failed to fetch')
  })
})
