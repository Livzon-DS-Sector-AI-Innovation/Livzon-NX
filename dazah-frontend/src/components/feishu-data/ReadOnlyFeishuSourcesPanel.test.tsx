/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { expect, it, vi } from 'vitest'
import { ReadOnlyFeishuSourcesPanel } from './ReadOnlyFeishuSourcesPanel'

it('shows a safe error when the Feishu source catalog cannot be loaded', async () => {
  const technicalError = 'TypeError: internal source catalog failure'
  const fetchMock = vi.fn().mockRejectedValue(new Error(technicalError))
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(
      <App><ReadOnlyFeishuSourcesPanel moduleCode="quality" pageOptions={[]} /></App>,
    ))
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/quality/feishu-read/roots', expect.any(Object))
      expect(document.body.textContent).toContain('操作未完成，请稍后重试')
    })
    expect(document.body.textContent).not.toContain(technicalError)
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
