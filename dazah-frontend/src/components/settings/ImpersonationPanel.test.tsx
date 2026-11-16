/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it, vi } from 'vitest'
import { ConfigProvider, theme } from 'antd'
import { listImpersonationTargets } from '@/lib/api/client/impersonation'
import { finishImpersonationListReturn, saveImpersonationListState } from '@/lib/impersonationListState'
import ImpersonationPanel from './ImpersonationPanel'

vi.mock('@/lib/api/client/impersonation', () => ({
  listImpersonationTargets: vi.fn().mockResolvedValue({
    total: 2,
    items: [
      {
        id: 'with-roles', name: '角色验收用户', username: 'reviewer',
        department: '采购部', employee_no: null,
        roles: [{ id: 'reader', name: '采购查询员' }, { id: 'reviewer', name: '供应商审核员' }],
      },
      {
        id: 'without-roles', name: '未授权用户', username: 'unassigned',
        department: null, employee_no: null, roles: [],
      },
    ],
  }),
  startImpersonation: vi.fn(),
}))

describe('模拟登录角色列', () => {
  it.each([theme.defaultAlgorithm, theme.darkAlgorithm])('呈现全部角色及未分配状态', async algorithm => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    vi.useFakeTimers()
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(<ConfigProvider theme={{ algorithm, token: { motion: false } }}>
        <ImpersonationPanel roles={[{ id: 'reader', name: '采购查询员' }]} />
      </ConfigProvider>))
      await act(async () => { await vi.advanceTimersByTimeAsync(100) })
      expect(host.querySelector('thead')?.textContent).toContain('角色')
      expect(host.querySelector('[data-row-key="with-roles"]')?.textContent).toContain('采购查询员')
      expect(host.querySelector('[data-row-key="with-roles"]')?.textContent).toContain('供应商审核员')
      expect(host.querySelector('[data-row-key="without-roles"]')?.textContent).toContain('未分配角色')
      expect(host.querySelector('[aria-label="按角色筛选"]')).not.toBeNull()
      expect(host.textContent).toContain('全部角色')
    } finally {
      await act(async () => root.unmount())
      host.remove()
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })
})

it('restores the filters and moves to the last available page if results shrank', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.useFakeTimers()
  const list = vi.mocked(listImpersonationTargets)
  list.mockClear()
  list.mockResolvedValueOnce({ total: 22, items: [] })
  list.mockResolvedValueOnce({ total: 22, items: [] })
  saveImpersonationListState({ keyword: '采购', roleId: 'reader', page: 3 })
  finishImpersonationListReturn(true)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
      <ImpersonationPanel roles={[{ id: 'reader', name: '采购查询员' }]} />
    </ConfigProvider>))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(host.querySelector<HTMLInputElement>('input[aria-label="搜索姓名、账号或工号"]')?.value).toBe('采购')
    expect(list.mock.calls.map(([query]) => query)).toEqual([
      { keyword: '采购', role_id: 'reader', offset: 40, limit: 20 },
      { keyword: '采购', role_id: 'reader', offset: 20, limit: 20 },
    ])
  } finally {
    await act(async () => root.unmount())
    host.remove()
    sessionStorage.clear()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  }
})

it('shows and recovers from a target list request failure', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.useFakeTimers()
  vi.mocked(listImpersonationTargets).mockRejectedValueOnce(new Error('暂时无法获取模拟用户'))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
      <ImpersonationPanel roles={[]} />
    </ConfigProvider>))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    const notice = host.querySelector('[data-platform-notice="error"]')
    expect(notice?.textContent).toContain('暂时无法获取模拟用户')
    const retry = [...host.querySelectorAll('button')].find(button => button.textContent?.replace(/\s/g, '') === '重试')
    if (!retry) throw new Error('缺少重试操作')
    await act(async () => {
      retry.click()
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(host.querySelector('[data-platform-notice="error"]')).toBeNull()
    expect(host.querySelector('[data-row-key="with-roles"]')).not.toBeNull()
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  }
})
