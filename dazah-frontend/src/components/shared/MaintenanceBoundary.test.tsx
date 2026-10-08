/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import MaintenanceBoundary from './MaintenanceBoundary'

vi.mock('./PlatformNotice', () => ({ default: ({ title, action }: { title: string; action: React.ReactNode }) => <div role="status">{title}{action}</div> }))
vi.mock('antd', () => ({
  Button: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => <button onClick={onClick}>{children}</button>,
  Modal: ({ children, footer, open, onCancel }: React.PropsWithChildren<{ footer: React.ReactNode; open: boolean; onCancel: () => void }>) => open ?
    <section className="dazah-maintenance-dialog"><button onClick={onCancel}>关闭</button>{children}{footer}</section> : null,
  Typography: { Paragraph: ({ children }: React.PropsWithChildren) => <p>{children}</p> },
}))

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('never adds failed read-only Actions to result reconciliation', async () => {
  const fetcher = vi.fn().mockImplementation(async (input: RequestInfo | URL) => String(input).includes('__dazah_maintenance_status') ?
    new Response(null, { status: 204 }) : new Response('{}', { status: 500 }))
  vi.stubGlobal('fetch', fetcher)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<MaintenanceBoundary>原页面</MaintenanceBoundary>))
    await act(async () => {
      await window.fetch('/production', { method: 'POST', headers: { 'Next-Action': 'fixture-read' } })
      await window.fetch('/production', { method: 'POST', headers: { 'Next-Action': 'fixture-read' } })
    })
    expect(host.textContent).toBe('原页面')
    expect(fetcher.mock.calls.some(call => String(call[0]).includes('/system/operations/'))).toBe(false)
  } finally { act(() => root.unmount()); host.remove() }
})

it('gives three minutes to save, cancels requests, preserves input and resumes without reconciliation', async () => {
  let phase = 'announced'
  let activeSignal: AbortSignal | undefined
  const fetcher = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    if (String(input).includes('__dazah_maintenance_status')) return phase === 'maintenance' ?
      new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } }) : phase === 'normal' ?
      new Response(null, { status: 204 }) : new Response(JSON.stringify({ phase, starts_at: Date.now() / 1000 + 180 }))
    activeSignal = (input as Request).signal
    return new Response('{}')
  })
  vi.stubGlobal('fetch', fetcher)
  const submit = vi.fn()
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const click = async (label: string) => act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === label)!.click())
  try {
    await act(async () => root.render(<MaintenanceBoundary><form onSubmit={event => { event.preventDefault(); submit() }}>
      <input defaultValue="未提交内容" /><button type="submit">保存表单</button>
    </form></MaintenanceBoundary>))
    expect(host.textContent).toContain('3 分 0 秒')
    await click('保存表单')
    expect(submit).toHaveBeenCalledOnce()
    await act(async () => { await window.fetch('/api/v1/quality') })
    expect(activeSignal?.aborted).toBe(false)
    await click('我知道了')
    expect(host.textContent).not.toContain('3 分 0 秒')
    phase = 'maintenance'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(activeSignal?.aborted).toBe(true)
    expect(host.textContent).toContain('请停止操作')
    await click('我知道了，保留当前页面')
    await click('保存表单')
    expect(submit).toHaveBeenCalledOnce()
    await expect(window.fetch('/api/v1/quality')).rejects.toThrow('请停止操作')
    phase = 'normal'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(host.textContent).not.toContain('系统更新维护')
    expect(host.querySelector('input')?.value).toBe('未提交内容')
    await click('保存表单')
    expect(submit).toHaveBeenCalledTimes(2)
    await act(async () => { await window.fetch('/api/v1/quality') })
    expect(activeSignal?.aborted).toBe(false)
  } finally { act(() => root.unmount()); host.remove() }
})

it('closes requests at the announced deadline even if subsequent probes fail', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(1_000_000)
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ phase: 'announced', starts_at: 1180 })))
    .mockRejectedValue(new Error('offline'))
  vi.stubGlobal('fetch', fetcher)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<MaintenanceBoundary>原页面</MaintenanceBoundary>))
    await act(async () => vi.advanceTimersByTimeAsync(180_000))
    expect(host.textContent).toContain('系统正在更新发布')
    await expect(window.fetch('/settings', { method: 'POST' })).rejects.toThrow('请停止操作')
  } finally { act(() => root.unmount()); host.remove() }
})
