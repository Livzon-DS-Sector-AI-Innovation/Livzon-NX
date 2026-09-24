/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchAgentAuditSessions: vi.fn(),
  fetchAgentAuditSession: vi.fn(),
}))
vi.mock('@/lib/api/agentAudit', () => api)

import AgentAuditLogClient from './AgentAuditLogClient'

describe('Livzon conversation audit detail', () => {
  let host: HTMLDivElement
  let root: Root

  beforeEach(() => {
    host = document.createElement('div')
    document.body.append(host)
    root = createRoot(host)
    const session = {
      id: 'session-1',
      user_name: '审计员甲',
      title: '测试对话',
      channel: 'web',
      status: 'completed',
      message_count: 0,
      tool_call_count: 0,
      failed_operation_count: 0,
      created_at: '2026-09-22T08:00:00Z',
      updated_at: '2026-09-22T08:00:00Z',
    }
    api.fetchAgentAuditSessions.mockResolvedValue({ items: [session], total: 1 })
    api.fetchAgentAuditSession.mockResolvedValue({
      session, messages: [], operations: [], confirmations: [], context: null,
    })
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    host.remove()
    vi.clearAllMocks()
  })

  it('opens the detail without a deprecated Drawer warning', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      await act(async () => root.render(createElement(App, null, createElement(AgentAuditLogClient))))
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
      const viewButton = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
      expect(viewButton).toBeDefined()
      await act(async () => viewButton?.click())

      expect(api.fetchAgentAuditSession).toHaveBeenCalledWith('session-1')
      expect(document.body.textContent).toContain('Livzon 对话审计详情')
      expect(consoleError.mock.calls.flat().join(' ')).not.toContain("[antd: Drawer] `width` is deprecated")
    } finally {
      consoleError.mockRestore()
    }
  })

  it('shows Chinese tool descriptions while retaining original identifiers in detail', async () => {
    const session = (await api.fetchAgentAuditSessions()).items[0]
    api.fetchAgentAuditSession.mockResolvedValue({
      session, messages: [], context: null,
      operations: [{ id: 'operation-1', operation: 'quality.list_deviations', status: 'failed', correlation_id: 'trace-1', created_at: '2026-09-22T08:00:00Z' }],
      confirmations: [{ id: 'confirmation-1', operation: 'agent.run_automation', summary: '立即运行', status: 'executed', risk_level: 'high', created_at: '2026-09-22T08:00:00Z' }],
    })
    await act(async () => root.render(createElement(App, null, createElement(AgentAuditLogClient))))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
    const view = Array.from(host.querySelectorAll('button')).find((button) => button.textContent?.includes('查看'))
    await act(async () => view?.click())
    const operationTab = Array.from(document.body.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent?.includes('操作明细')) as HTMLElement
    await act(async () => operationTab.click())
    expect(document.body.textContent).toContain('查询偏差记录')
    const confirmationTab = Array.from(document.body.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent?.includes('确认记录')) as HTMLElement
    await act(async () => confirmationTab.click())
    expect(document.body.textContent).toContain('高风险')
    expect(document.body.textContent).toContain('原始工具标识：')
    expect(document.body.textContent).toContain('agent.run_automation')
  })
})
