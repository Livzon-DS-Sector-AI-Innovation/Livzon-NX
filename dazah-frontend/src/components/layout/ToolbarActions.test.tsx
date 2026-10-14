/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { useQueryClient } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import type { User } from '@/types/user'

vi.mock('./MyTodos', () => ({ MyTodos: () => {
  const client = useQueryClient()
  return createElement('button', null, client ? '我的待办已连接' : '缺少查询客户端')
} }))
vi.mock('./FeedbackEntry', () => ({ FeedbackEntry: () => {
  const client = useQueryClient()
  return createElement('button', null, client ? '反馈已连接' : '缺少查询客户端')
} }))
import { ToolbarActions } from './ToolbarActions'

it('supplies a query client to both toolbar features outside module providers', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const user: User = { id: 'test-user', name: '测试用户', role: 'user', status: 'active', auth_source: 'local', grant_version: 1, page_permission_rollouts: {}, page_permissions: [] }
  try {
    await act(async () => root.render(createElement(ToolbarActions, { user, modules: [] })))
    expect(host.textContent).toContain('我的待办已连接')
    expect(host.textContent).toContain('反馈已连接')
  } finally { await act(async () => root.unmount()); host.remove() }
})
