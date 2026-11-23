/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import MaintenanceBoundary from './MaintenanceBoundary'

vi.mock('./PlatformNotice', () => ({ default: ({ title, action, onLearnRules }: { title: string; action: React.ReactNode; onLearnRules: () => void }) =>
  <div role="status">{title}{action}<button onClick={onLearnRules}>了解访问规则</button></div> }))
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
    expect(host.querySelector('[data-dazah-maintenance-screen]')).not.toBeNull()
    expect(host.querySelector('[data-dazah-maintenance-boundary]')?.hasAttribute('inert')).toBe(true)
    expect(host.textContent).toContain('请停止操作')
    await click('了解访问规则')
    await click('我知道了，保留当前页面')
    expect(host.querySelector('[data-dazah-maintenance-screen]')).not.toBeNull()
    await click('保存表单')
    expect(submit).toHaveBeenCalledOnce()
    await expect(window.fetch('/api/v1/quality')).rejects.toThrow('请停止操作')
    phase = 'normal'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(host.textContent).not.toContain('系统更新维护')
    expect(host.querySelector('input')?.value).toBe('未提交内容')
    expect(host.querySelector('[data-dazah-maintenance-screen]')).toBeNull()
    expect(host.querySelector('[data-dazah-maintenance-boundary]')?.hasAttribute('inert')).toBe(false)
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
    expect(host.querySelector('[data-dazah-maintenance-screen]')?.textContent).toContain('系统维护中，请稍候')
    expect(host.querySelector('[data-dazah-maintenance-boundary]')?.hasAttribute('inert')).toBe(true)
    await expect(window.fetch('/settings', { method: 'POST' })).rejects.toThrow('请停止操作')
  } finally { act(() => root.unmount()); host.remove() }
})

it('backs off probing when the status endpoint is unavailable (dev 404)', async () => {
  vi.useFakeTimers()
  const fetcher = vi.fn(async (input: RequestInfo | URL) =>
    String(input).includes('__dazah_maintenance_status')
      ? new Response(null, { status: 404 })
      : new Response('{}'))
  vi.stubGlobal('fetch', fetcher)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<MaintenanceBoundary>原页面</MaintenanceBoundary>))
    await act(async () => vi.advanceTimersByTimeAsync(10_000))
    const probeCalls = fetcher.mock.calls.filter(call => String(call[0]).includes('__dazah_maintenance_status')).length
    // 退避节奏 1s→2s→4s→8s：10 秒内仅 4 次探测（旧行为为 11 次）
    expect(probeCalls).toBeLessThanOrEqual(4)
    expect(probeCalls).toBeGreaterThanOrEqual(2)
    expect(host.textContent).toBe('原页面')
  } finally { act(() => root.unmount()); host.remove() }
})

it('recovers to 1s probing once the status endpoint is healthy again', async () => {
  vi.useFakeTimers()
  let healthy = false
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    if (!String(input).includes('__dazah_maintenance_status')) return new Response('{}')
    return healthy ? new Response(null, { status: 204 }) : new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetcher)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const probeCount = () => fetcher.mock.calls.filter(call => String(call[0]).includes('__dazah_maintenance_status')).length
  try {
    await act(async () => root.render(<MaintenanceBoundary>原页面</MaintenanceBoundary>))
    await act(async () => vi.advanceTimersByTimeAsync(7_000)) // 退避中：0,1,3,7s → 4 次
    const duringBackoff = probeCount()
    healthy = true
    // 7s 末下一次探测排在 15s（退避 8s）；推进 12s 覆盖恢复后的 1s 节奏
    await act(async () => vi.advanceTimersByTimeAsync(12_000))
    const afterRecovery = probeCount() - duringBackoff
    expect(duringBackoff).toBeLessThanOrEqual(4)
    expect(afterRecovery).toBeGreaterThanOrEqual(3)
  } finally { act(() => root.unmount()); host.remove() }
})
