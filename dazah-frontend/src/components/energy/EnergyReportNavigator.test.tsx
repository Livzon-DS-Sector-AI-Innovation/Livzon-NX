/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import { EnergyReportNavigator } from './EnergyReportNavigator'

afterEach(() => document.body.replaceChildren())
it('searches grouped reports and preserves the target period when selecting a result', async () => {
  const node = document.createElement('div'); document.body.append(node); const root = createRoot(node)
  const select = vi.fn()
  await act(async () => root.render(<EnergyReportNavigator datasets={[{ name: '日总量', kind: 'usage' }, { name: '电量', kind: 'mixed' }, { name: '203-1车间', kind: 'usage' }, { name: '203-2车间', kind: 'usage' }]} selected="日总量" year={2026} month={8} loading={false} onSelect={select} />))
  const input = node.querySelector<HTMLInputElement>('[aria-label="搜索报表"]')!
  async function search(value: string) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }
  await search('203')
  expect(node.querySelectorAll('nav a')).toHaveLength(2)
  const link = node.querySelector<HTMLAnchorElement>('nav a')!
  expect(link.href).toContain('year=2026&month=8&dataset=')
  await act(async () => link.click())
  expect(select).toHaveBeenCalledWith('203-1车间')
  await search('不存在')
  expect(node.textContent).toContain('没有匹配的报表')
  await act(async () => root.unmount())
})
