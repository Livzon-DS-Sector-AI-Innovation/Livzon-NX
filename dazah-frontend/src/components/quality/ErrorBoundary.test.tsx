/* @vitest-environment happy-dom */
import { act, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

vi.mock('@/components/shared/PlatformNotice', () => ({
  default: ({ title, action }: { title: string; action: ReactNode }) => <div>{title}{action}</div>,
}))

it('retries the CAPA content in place and lets the user retry persistent errors', async () => {
  const host = document.createElement('div')
  const root = createRoot(host)
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  const logger = vi.spyOn(console, 'error').mockImplementation(() => {})
  let available = false
  function Content() {
    if (!available) throw new Error('加载失败')
    return <p>CAPA 已恢复</p>
  }
  const retry = () => Array.from(host.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '重试')
  try {
    await act(async () => root.render(<ErrorBoundary><Content /></ErrorBoundary>))
    expect(host.textContent).toContain('页面出错了')
    await act(async () => retry()?.click())
    expect(host.textContent).toContain('页面出错了')
    available = true
    await act(async () => retry()?.click())
    expect(host.textContent).toBe('CAPA 已恢复')
    expect(reload).not.toHaveBeenCalled()
  } finally {
    await act(async () => root.unmount())
    reload.mockRestore()
    logger.mockRestore()
  }
})
