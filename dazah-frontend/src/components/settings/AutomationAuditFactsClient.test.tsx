/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchPlatformLivzonTasks: vi.fn(),
  fetchPlatformLivzonTaskRuns: vi.fn(),
  fetchLivzonTaskVersions: vi.fn(),
  fetchLivzonTaskRun: vi.fn(),
}))
vi.mock('@/lib/api/agent', () => api)

import AutomationAuditFactsClient from './AutomationAuditFactsClient'

describe('automation audit facts', () => {
  let host: HTMLDivElement
  let root: Root

  beforeEach(() => {
    host = document.createElement('div')
    document.body.append(host)
    root = createRoot(host)
    api.fetchPlatformLivzonTasks.mockResolvedValue({
      items: [{ id: 'automation-1', name: '偏差复核', owner_user_id: 'user-1', status: 'enabled', active_version: 2 }], total: 1,
    })
    api.fetchPlatformLivzonTaskRuns.mockResolvedValue({
      items: [{ id: 'run-1', automation_id: 'automation-1', status: 'failed', error_message: '工具超时' }], total: 1,
    })
    api.fetchLivzonTaskVersions.mockResolvedValue([
      { id: 'version-2', automation_id: 'automation-1', version: 2, change_summary: '调整检查步骤' },
    ])
    api.fetchLivzonTaskRun.mockResolvedValue({
      run: { id: 'run-1', automation_id: 'automation-1', status: 'failed', error_message: '工具超时' },
      steps: [{ id: 'step-1', step_key: 'check', operation: 'quality.list_deviations', status: 'failed', error_message: '工具超时' }],
    })
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    host.remove()
    vi.clearAllMocks()
  })

  it('shows real definition versions and run results', async () => {
    await act(async () => root.render(createElement(App, null, createElement(AutomationAuditFactsClient))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(api.fetchPlatformLivzonTasks).toHaveBeenCalledWith(1, 20)
    expect(host.textContent).toContain('偏差复核')
    const viewDefinition = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
    await act(async () => viewDefinition?.click())
    expect(api.fetchLivzonTaskVersions).toHaveBeenCalledWith('automation-1')
    expect(document.body.textContent).toContain('调整检查步骤')

    const runsTab = Array.from(host.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent === '运行记录') as HTMLElement
    await act(async () => runsTab.click())
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(api.fetchPlatformLivzonTaskRuns).toHaveBeenCalledWith(1, 20)
    expect(host.textContent).toContain('工具超时')
    expect(host.textContent).toContain('失败')
    const runRow = Array.from(host.querySelectorAll('tr')).find((row) => row.textContent?.includes('run-1'))
    const viewRun = Array.from(runRow?.querySelectorAll('button') || []).find((button) => button.textContent?.includes('查看'))
    await act(async () => viewRun?.click())
    expect(document.body.textContent).toContain('查询偏差记录')
  })

  it('keeps a visible retry action when loading fails', async () => {
    api.fetchPlatformLivzonTasks.mockRejectedValue(new Error('服务不可用'))
    await act(async () => root.render(createElement(App, null, createElement(AutomationAuditFactsClient))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(host.textContent).toContain('服务不可用')
    expect(host.textContent?.replace(/\s/g, '')).toContain('重试')
  })
})
