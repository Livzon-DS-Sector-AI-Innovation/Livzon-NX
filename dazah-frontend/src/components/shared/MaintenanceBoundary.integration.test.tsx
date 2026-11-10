/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import { expect, it, vi } from 'vitest'
import MaintenanceBoundary from './MaintenanceBoundary'

it.each(['light', 'dark'])('keeps maintenance separate from ordinary inputs and browser navigation in %s mode', async appearance => {
  let phase = 'normal'
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
    if (phase === 'maintenance') return new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } })
    if (phase === 'normal') return new Response(null, { status: 204 })
    return new Response(JSON.stringify({ phase, starts_at: Date.now() / 1000 + 180 }))
  }))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const button = (label: string) => [...document.querySelectorAll('button')].find(item => item.textContent?.replace(/\s/g, '') === label)!
  const checkPhase = async (next: string) => {
    phase = next
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  }
  const allowsUnload = () => window.dispatchEvent(new Event('beforeunload', { cancelable: true }))
  try {
    await act(async () => root.render(<ConfigProvider theme={{
      algorithm: appearance === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: { motion: false },
    }}>
      <MaintenanceBoundary>
        <input aria-label="搜索" />
        <input aria-label="已选筛选项" type="checkbox" />
      </MaintenanceBoundary>
    </ConfigProvider>))
    const search = host.querySelector<HTMLInputElement>('[aria-label="搜索"]')!
    search.value = '搜索关键词'
    await act(async () => search.dispatchEvent(new Event('input', { bubbles: true })))
    expect(allowsUnload()).toBe(true)

    await checkPhase('announced')
    await act(async () => host.querySelector<HTMLInputElement>('[type="checkbox"]')!.click())
    expect(allowsUnload()).toBe(true)
    expect(host.querySelector('[data-dazah-maintenance-boundary] [data-platform-notice]')).toBeNull()
    expect(host.querySelector('[data-platform-notice]')?.textContent).toContain('完成当前工作并停止操作')
    await act(async () => button('我知道了').click())
    expect(document.querySelector('[data-platform-notice]')).toBeNull()
    await checkPhase('maintenance')
    expect(host.querySelector('[data-dazah-maintenance-screen]')?.textContent).toContain('系统维护中，请稍候')
    expect(host.querySelector('[data-dazah-maintenance-boundary]')?.hasAttribute('inert')).toBe(true)
    expect(allowsUnload()).toBe(true)
    await act(async () => button('了解访问规则').click())
    expect(document.querySelector('.ant-modal')?.textContent).toContain('请停止操作')
    await act(async () => document.querySelector<HTMLButtonElement>('.dazah-maintenance-dialog .ant-modal-close')!.click())
    expect(document.querySelector<HTMLElement>('.dazah-maintenance-dialog')?.style.display).toBe('none')
    expect(search.value).toBe('搜索关键词')
    await expect(window.fetch('/api/v1/quality')).rejects.toThrow('请停止操作')
    expect(host.querySelector('[data-dazah-maintenance-screen]')).not.toBeNull()
    await act(async () => button('了解访问规则').click())
    expect(document.querySelector<HTMLElement>('.dazah-maintenance-dialog')?.style.display).not.toBe('none')
    expect(document.body.textContent).not.toContain('查询操作结果')

    await checkPhase('normal')
    expect(host.querySelector('[data-dazah-maintenance-screen]')).toBeNull()
    expect(search.value).toBe('搜索关键词')
    expect(allowsUnload()).toBe(true)
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
