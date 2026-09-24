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
vi.mock('@/lib/api/agentAudit', () => ({
  fetchAgentAuditSessions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchAgentAuditSession: vi.fn(),
}))
vi.mock('@/lib/api/agent', () => ({
  fetchPlatformLivzonTasks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchPlatformLivzonTaskRuns: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchLivzonTaskVersions: vi.fn().mockResolvedValue([]),
  fetchLivzonTaskRun: vi.fn(),
}))

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
        summary: { target: 'item_id=123' },
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

  it('opens the user operation tab by default', async () => {
    await act(async () => root.render(createElement(App, null, createElement(AuditLogClient))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    const activeTab = host.querySelector('[role="tab"][aria-selected="true"]')
    expect(activeTab?.textContent).toContain('用户操作')
    expect(api.fetchGeneralAuditLogs).toHaveBeenCalledWith(expect.objectContaining({ category: 'operations' }))
    const topTabs = Array.from(host.querySelectorAll('[role="tab"]')).map((tab) => tab.textContent)
    expect(topTabs).toEqual(['用户操作', '权限与授权', 'Livzon助手', '业务与外部交互'])
  })

  it('groups Livzon and external audit views under their own entrances', async () => {
    await act(async () => root.render(createElement(App, null, createElement(AuditLogClient))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    const livzon = Array.from(host.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent === 'Livzon助手') as HTMLElement
    await act(async () => livzon.click())
    expect(host.textContent).toContain('自动化版本与运行')
    const business = Array.from(host.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent === '业务与外部交互') as HTMLElement
    await act(async () => business.click())
    expect(host.textContent).toContain('飞书交互')
  })

  it('shows actor, operation, module and time from the paged API', async () => {
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(api.fetchGeneralAuditLogs).toHaveBeenCalledWith(expect.objectContaining({ category: 'operations', page: 1, pageSize: 20 }))
    expect(host.textContent).toContain('质量员甲')
    expect(host.textContent).toContain('查看质量记录')
    expect(host.textContent).toContain('item_id=123')
    expect(host.textContent).toContain('质量管理')
    expect(host.textContent).toContain('2026-09-22')
  })

  it('shows Chinese descriptions for recorded route names, including historical entries', async () => {
    const operations = [
      ['list_automations', '查询自动化列表'],
      ['list_interaction_requests', '查询交互请求列表'],
      ['list_skills', '查询技能列表'],
      ['get_control_plane_runtime_overview', '查看控制平面运行概况'],
      ['unknown_agent_query', '查询智能助手信息'],
    ]
    api.fetchGeneralAuditLogs.mockResolvedValue({
      items: operations.map(([operation], index) => ({
        id: `operation-${index}`, category: 'operations', action: 'platform_api_request',
        operation, method: 'GET', path: '/api/v1/agent/unknown', resource_type: 'agent',
        status_code: 200, created_at: '2026-09-22T08:00:00Z',
      })),
      page: 1, page_size: 20, total: operations.length,
    })
    api.fetchGeneralAuditLog.mockResolvedValue({
      id: 'operation-0', category: 'operations', action: 'platform_api_request',
      operation: 'list_automations', method: 'GET', path: '/api/v1/agent/automations',
      resource_type: 'agent', status_code: 200, created_at: '2026-09-22T08:00:00Z',
    })
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    for (const [, label] of operations) expect(host.textContent).toContain(label)
    expect(host.textContent).not.toContain('list_automations')

    const viewButton = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
    await act(async () => viewButton?.click())
    expect(document.body.textContent).toContain('具体操作查询自动化列表')
  })

  it('opens the detail without a deprecated Drawer warning', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      await act(async () => {
        root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
      })
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
      const viewButton = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
      expect(viewButton).toBeDefined()
      await act(async () => viewButton?.click())

      expect(api.fetchGeneralAuditLog).toHaveBeenCalledWith('0a62d7e6-e1da-42ea-bcdb-3f82137a0ea1')
      expect(document.body.textContent).toContain('用户操作审计详情')
      expect(consoleError.mock.calls.flat().join(' ')).not.toContain("[antd: Drawer] `width` is deprecated")
    } finally {
      consoleError.mockRestore()
    }
  })

  it('shows request trace and response metadata in the operation detail', async () => {
    api.fetchGeneralAuditLog.mockResolvedValue({
      id: '0a62d7e6-e1da-42ea-bcdb-3f82137a0ea1',
      category: 'operations', actor_name: '质量员甲', action: 'platform_api_request',
      operation: '查看质量记录', method: 'GET', path: '/api/v1/quality/items/{item_id}',
      resource_type: 'quality', status_code: 200, summary: { target: 'item_id=123' },
      created_at: '2026-09-22T08:00:00Z', request_id: 'trace-123', duration_ms: 42,
      ip_address: '127.0.0.1', user_agent: 'audit-test-client',
      extra: {
        request: { path_params: { item_id: '123' }, query_params: { page: '2' } },
        response: { status_code: 200, content_length: 24 },
        related_events: [{ action: 'update_quality_item', old_value: { status: 'draft' }, new_value: { status: 'approved' } }],
      },
    })
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    const viewButton = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
    await act(async () => viewButton?.click())
    const content = document.body.textContent || ''
    expect(content).toContain('trace-123')
    expect(content).toContain('42 ms')
    expect(content).toContain('127.0.0.1')
    expect(content).toContain('audit-test-client')
    expect(content).toContain('请求参数与内容')
    expect(content).toContain('content_length')
    expect(content).toContain('关联业务变更')
    expect(content).toContain('update_quality_item')
    expect(content).toContain('操作描述')
    expect(content).toContain('记录质量管理操作')
  })

  it('shows an empty list after a successful empty response', async () => {
    api.fetchGeneralAuditLogs.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })
    await act(async () => {
      root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'operations' })))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(host.textContent).toContain('暂无操作记录')
  })

  it('shows Hermes Feishu outcome and external log ID', async () => {
    api.fetchGeneralAuditLogs.mockResolvedValue({
      items: [{
        id: 'feishu-1', category: 'feishu', actor_name: null,
        action: 'base.record.update', resource_type: 'feishu_resource', method: 'HERMES',
        summary: { result: 'succeeded', feishu_log_id: 'log-123' },
        created_at: '2026-09-22T08:00:00Z',
      }], page: 1, page_size: 20, total: 1,
    })
    await act(async () => root.render(createElement(App, null, createElement(GeneralAuditLogClient, { category: 'feishu' }))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    expect(api.fetchGeneralAuditLogs).toHaveBeenCalledWith(expect.objectContaining({ category: 'feishu' }))
    expect(host.textContent).toContain('修改飞书多维表格记录')
    expect(host.textContent).toContain('成功')
    expect(host.textContent).toContain('log-123')
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
