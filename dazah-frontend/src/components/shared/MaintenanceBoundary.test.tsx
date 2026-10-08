/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import MaintenanceBoundary from './MaintenanceBoundary'

vi.mock('./PlatformNotice', () => ({ default: ({ title, action }: { title: string; action: React.ReactNode }) => <div role="status">{title}{action}</div> }))
vi.mock('antd', () => ({
  Button: ({ children, onClick, disabled }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => <button disabled={disabled} onClick={onClick}>{children}</button>,
  Space: ({ children }: React.PropsWithChildren) => <div data-maintenance-control>{children}</div>,
  Modal: ({ children, footer, open }: React.PropsWithChildren<{ footer: React.ReactNode; open: boolean }>) => open ? <section className="dazah-maintenance-dialog">{children}{footer}</section> : null,
  Typography: { Paragraph: ({ children }: React.PropsWithChildren) => <p>{children}</p> },
}))

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it.each(['empty', 'other-operation', 'unknown', 'completed'])('only verified owner receipts permit reconciliation: %s', async mode => {
  const fetcher = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input)
    if (url.includes('__dazah_maintenance_status')) return new Response(null, { status: 204 })
    if (url.includes('/system/operations/')) {
      return new Response(JSON.stringify({ operation_id: mode === 'other-operation' ? 'another' : url.split('/').pop(),
        receipts: mode === 'empty' ? [] : [{ method: 'POST', state: mode === 'unknown' ? 'unknown' : 'completed' }] }))
    }
    return new Response('{}')
  })
  vi.stubGlobal('fetch', fetcher)
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  try {
    await act(async () => root.render(<MaintenanceBoundary>业务表单</MaintenanceBoundary>))
    await act(async () => { await window.fetch('/api/v1/quality/write', { method: 'POST', body: '{}' }) })
    // Direct successful API calls are acknowledged; simulate a successful Action
    // carrying a write step, whose overall business result still needs checking.
    await act(async () => { await window.fetch('/settings', { method: 'POST', body: '{}', headers: { 'Next-Action': 'fixture-write' } }) })
    await vi.waitFor(() => expect(container.textContent).toContain('处理记录编号'))
    const query = [...container.querySelectorAll('button')].find(button => button.textContent === '查询操作结果')!
    await act(async () => query.click())
    expect(container.textContent?.includes('已核对业务结果，允许新的提交')).toBe(mode === 'completed')
  } finally { act(() => root.unmount()); container.remove() }
})

it('warns before maintenance, keeps unsaved inputs mounted and preserves them after recovery', async () => {
  let phase = 'announced'
  const fetcher = vi.fn().mockImplementation(async () => phase === 'maintenance' ?
    new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } }) : phase === 'normal' ?
    new Response(null, { status: 204 }) : new Response(JSON.stringify({ phase, starts_at: Date.now() / 1000 + 300 })))
  vi.stubGlobal('fetch', fetcher)
  const submit = vi.fn()
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  try {
    await act(async () => root.render(<MaintenanceBoundary><form onSubmit={event => { event.preventDefault(); submit() }}>
      <input aria-label="未保存的工作" /><button type="submit">保存表单</button>
    </form></MaintenanceBoundary>))
    const input = container.querySelector('input') as HTMLInputElement
    input.value = '未提交内容'
    act(() => input.dispatchEvent(new Event('input', { bubbles: true })))
    expect(container.textContent).toContain('请及时保存当前工作')
    const save = container.querySelector('button[type=submit]') as HTMLButtonElement
    await act(async () => save.click())
    expect(submit).toHaveBeenCalledOnce()
    phase = 'maintenance'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(container.textContent).toContain('当前页面和输入已保留')
    expect(container.querySelector('input')).toBe(input)
    expect(input.value).toBe('未提交内容')
    await act(async () => save.click())
    expect(submit).toHaveBeenCalledOnce()
    const beforeUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(beforeUnload)
    expect(beforeUnload.defaultPrevented).toBe(true)
    phase = 'normal'
    await act(async () => document.dispatchEvent(new Event('visibilitychange')))
    expect(container.textContent).not.toContain('请及时保存当前工作')
    expect(input.value).toBe('未提交内容')
    await act(async () => save.click())
    expect(submit).toHaveBeenCalledTimes(2)
  } finally { act(() => root.unmount()); container.remove() }
})
