/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchGeneralAuditLogs: vi.fn(),
  fetchGeneralAuditLog: vi.fn(),
}))
vi.mock('@/lib/api/generalAudit', () => api)

import AuditLogClient from './AuditLogClient'
import GeneralAuditLogClient from './GeneralAuditLogClient'

describe('user operation audit tab', () => {
  let host: HTMLDivElement
  let root: Root

  beforeEach(() => {
    host = document.createElement('div')
    document.body.append(host)
    root = createRoot(host)
    api.fetchGeneralAuditLogs.mockResolvedValue({
      items: [{
        id: '0a62d7e6-e1da-42ea-bcdb-3f82137a0ea1',
        category: 'operations',
        actor_name: '质量员甲',
        actor_user_id: 'b27a2871-890b-4544-879d-151d5af842b3',
        action: 'platform_api_request',
        operation: '查看质量记录',
        method: 'GET',
        path: '/api/v1/quality/items/{item_id}',
        resource_type: 'quality',
        status_code: 200,
        summary: {},
        created_at: '2026-09-22T08:00:00Z',
      }],
      page: 1,
      page_size: 20,
      total: 1,
    })
    api.fetchGeneralAuditLog.mockResolvedValue({})
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    host.remove()
    vi.clearAllMocks()
  })

  it('adds the user operation tab to audit logs', async () => {
    await act(async () => root.render(createElement(App, null, createElement(AuditLogClient))))
    expect(host.textContent).toContain('用户操作')
  })

  it('shows actor, operation, module and time from the paged API', async () => {
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(api.fetchGeneralAuditLogs).toHaveBeenCalledWith(expect.objectContaining({ category: 'operations', page: 1, pageSize: 20 }))
    expect(host.textContent).toContain('质量员甲')
    expect(host.textContent).toContain('查看质量记录')
    expect(host.textContent).toContain('质量管理')
    expect(host.textContent).toContain('2026-09-22')
  })

  it('shows an empty list after a successful empty response', async () => {
    api.fetchGeneralAuditLogs.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(host.textContent).toContain('暂无操作记录')
  })

  it('shows a retry action when loading fails', async () => {
    api.fetchGeneralAuditLogs.mockRejectedValue(new Error('审计服务不可用'))
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(host.textContent).toContain('审计日志加载失败')
    expect(host.textContent?.replace(/\s/g, '')).toContain('重试')
  })
})
