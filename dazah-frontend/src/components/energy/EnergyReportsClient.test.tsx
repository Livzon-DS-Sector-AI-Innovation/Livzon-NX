/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  usePathname: () => '/energy/reports',
  useSearchParams: () => new URLSearchParams('year=2026&month=7&dataset=饮用水码'),
}))
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined, isFetching: false }) }))
vi.mock('./EnergyWorkbookClient', () => ({ EnergyWorkbookClient: () => <div>原表结果</div> }))
vi.mock('@/components/shared/ThemedEChart', () => ({ default: () => null }))

import { EnergyReportsClient } from './EnergyReportsClient'

afterEach(() => { document.body.innerHTML = ''; window.history.replaceState(null, '', '/') })

it.each([false, true])('applies and resets client report filters without server navigation (dark=%s)', async dark => {
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient mode="reports" /></App></ConfigProvider>))
  const button = (label: string) => Array.from(node.querySelectorAll('button')).find(item => item.textContent?.replaceAll(' ', '') === label)
  await act(async () => button('查询')?.click())
  const params = new URLSearchParams(window.location.search)
  expect(params.get('dataset')).toBe('饮用水码')
  expect(params.get('year')).toBe('2026')
  expect(params.get('month')).toBe('7')
  expect(params.get('page')).toBe('1')
  expect(node.textContent).toContain('原表结果')
  await act(async () => button('重置')?.click())
  expect(window.location.pathname).toBe('/energy/reports')
  expect(window.location.search).toBe('')
  await act(async () => root.unmount())
})
