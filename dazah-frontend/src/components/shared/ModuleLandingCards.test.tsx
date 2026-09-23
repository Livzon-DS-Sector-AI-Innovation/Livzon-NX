/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ModuleLandingCards } from './ModuleLandingCards'

vi.mock('next/link', () => ({ default: ({ href, children, ...props }: { href: string; children: ReactNode }) =>
  createElement('a', { href, ...props }, children) }))
vi.mock('antd', () => ({
  Row: ({ children }: { children: ReactNode }) => createElement('div', null, children),
  Col: ({ children }: { children: ReactNode }) => createElement('div', null, children),
  Card: ({ children }: { children: ReactNode }) => createElement('div', null, children),
}))

afterEach(() => document.body.replaceChildren())

describe('ModuleLandingCards', () => {
  it('labels dashboard links and keeps ordinary page links distinct', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(ModuleLandingCards, {
        title: '质量管理', description: '模块入口', entries: [
          { title: '偏差管理', description: '偏差统计', href: '/quality/deviations', icon: null, dashboard: true },
          { title: '质量检验', description: '检验分组', href: '/quality/inspection', icon: null },
        ],
      })))
      expect(host.querySelector('a[href="/quality/deviations"]')?.textContent).toContain('仪表盘')
      expect(host.querySelector('a[href="/quality/inspection"]')?.textContent).not.toContain('仪表盘')
      expect(host.querySelectorAll('h1')).toHaveLength(1)
    } finally {
      await act(async () => root.unmount())
    }
  })
})
