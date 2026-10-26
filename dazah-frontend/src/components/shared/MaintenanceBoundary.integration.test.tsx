/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import { expect, it, vi } from 'vitest'
import MaintenanceBoundary from './MaintenanceBoundary'

it('automatically shows a persistent maintenance screen and retains input when the rules modal closes', async () => {
  let phase = 'announced'
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => phase === 'maintenance' ?
    new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } }) :
    new Response(JSON.stringify({ phase, starts_at: Date.now() / 1000 + 180 }))))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const button = (label: string) => [...document.querySelectorAll('button')].find(item => item.textContent?.replace(/\s/g, '') === label)!
  try {
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
      <MaintenanceBoundary><input defaultValue="未保存输入" /></MaintenanceBoundary>
    </ConfigProvider>))
    expect(host.querySelector('[data-dazah-maintenance-boundary] [data-platform-notice]')).toBeNull()
    expect(host.querySelector('[data-platform-notice]')?.textContent).toContain('完成当前工作并停止操作')
    await act(async () => button('我知道了').click())
    expect(document.querySelector('[data-platform-notice]')).toBeNull()
    phase = 'maintenance'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(host.querySelector('[data-dazah-maintenance-screen]')?.textContent).toContain('系统维护中，请稍候')
    expect(host.querySelector('[data-dazah-maintenance-boundary]')?.hasAttribute('inert')).toBe(true)
    await act(async () => button('了解访问规则').click())
    expect(document.querySelector('.ant-modal')?.textContent).toContain('请停止操作')
    await act(async () => document.querySelector<HTMLButtonElement>('.dazah-maintenance-dialog .ant-modal-close')!.click())
    expect(document.querySelector<HTMLElement>('.dazah-maintenance-dialog')?.style.display).toBe('none')
    expect(host.querySelector('input')?.value).toBe('未保存输入')
    await expect(window.fetch('/api/v1/quality')).rejects.toThrow('请停止操作')
    expect(host.querySelector('[data-dazah-maintenance-screen]')).not.toBeNull()
    await act(async () => button('了解访问规则').click())
    expect(document.querySelector<HTMLElement>('.dazah-maintenance-dialog')?.style.display).not.toBe('none')
    expect(document.body.textContent).not.toContain('查询操作结果')
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
