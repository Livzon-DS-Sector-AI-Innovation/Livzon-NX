/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it, vi } from 'vitest'
import { ConfigProvider, theme } from 'antd'
import { SEARCH_DELAY_MS } from '@/hooks/useSearchFilter'
import { listImpersonationTargets, startImpersonation } from '@/lib/api/client/impersonation'
import { finishImpersonationListReturn, saveImpersonationListState } from '@/lib/impersonationListState'
import ImpersonationPanel from './ImpersonationPanel'

vi.mock('@/lib/api/client/impersonation', () => ({
  listImpersonationTargets: vi.fn().mockResolvedValue({
    total: 3,
    items: [
      {
        id: 'with-roles', name: '角色验收用户', username: 'reviewer',
        department: '采购部', employee_no: null,
        roles: [{ id: 'reader', name: '采购查询员' }, { id: 'reviewer', name: '供应商审核员' }],
      },
      {
        id: 'with-extra-roles', name: '多角色用户', username: 'multi-role',
        department: '质量部', employee_no: null,
        roles: [
          { id: 'product-qa', name: '产品QA' }, { id: 'system-qa', name: '体系QA' },
          { id: 'change-qa', name: '变更QA' }, { id: 'material-qa', name: '物料QA' },
        ],
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
  it.each([theme.defaultAlgorithm, theme.darkAlgorithm])('默认最多显示两个角色，悬停查看更多角色', async algorithm => {
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

      const more = [...host.querySelectorAll<HTMLButtonElement>('tbody button')]
        .filter(button => button.textContent?.startsWith('更多'))
      expect(more.map(button => button.textContent)).toEqual(['更多（2+）'])
      const [trigger] = more
      const row = trigger.closest('tr')
      expect(row?.textContent).toContain('产品QA')
      expect(row?.textContent).toContain('体系QA')
      expect(row?.textContent).not.toContain('变更QA')
      expect(row?.textContent).not.toContain('物料QA')
      await act(async () => {
        trigger.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
        await vi.advanceTimersByTimeAsync(300)
      })
      const tooltip = document.querySelector('[role="tooltip"]')
      expect(tooltip?.textContent).toContain('变更QA')
      expect(tooltip?.textContent).toContain('物料QA')
      expect(tooltip?.textContent).not.toContain('产品QA')
      expect(tooltip?.textContent).not.toContain('体系QA')
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

it('searches after Chinese composition ends, resets pagination and restores the list on clear', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.useFakeTimers()
  const list = vi.mocked(listImpersonationTargets)
  list.mockClear()
  list.mockResolvedValueOnce({ total: 22, items: [] })
  list.mockResolvedValueOnce({ total: 22, items: [] })
  list.mockResolvedValueOnce({ total: 0, items: [] })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
      <ImpersonationPanel roles={[]} />
    </ConfigProvider>))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    await act(async () => host.querySelector<HTMLButtonElement>('.ant-pagination-next button')!.click())
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(list.mock.lastCall?.[0]).toEqual({ keyword: '', role_id: undefined, offset: 20, limit: 20 })

    const input = host.querySelector<HTMLInputElement>('input[role="searchbox"]')!
    const write = (value: string) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    }
    await act(async () => {
      input.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }))
      write('cai')
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS) })
    expect(list).toHaveBeenCalledTimes(2)

    await act(async () => {
      write('  采购  ')
      input.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }))
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS) })
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    expect(list.mock.lastCall?.[0]).toEqual({ keyword: '采购', role_id: undefined, offset: 0, limit: 20 })
    expect(host.textContent).toContain('暂无可模拟的用户')

    await act(async () => host.querySelector('[aria-label="清空搜索"]')!.closest('button')!.click())
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(input.value).toBe('')
    expect(list.mock.lastCall?.[0]).toEqual({ keyword: '', role_id: undefined, offset: 0, limit: 20 })
  } finally {
    await act(async () => root.unmount())
    host.remove()
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

it('keeps the confirmation open and permits retry after a failed identity switch', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.useFakeTimers()
  const start = vi.mocked(startImpersonation)
  start.mockRejectedValueOnce(new Error('目标用户已停用'))
  const navigate = vi.spyOn(window.location, 'replace').mockImplementation(() => {})
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
      <ImpersonationPanel roles={[]} />
    </ConfigProvider>))
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    const target = host.querySelector<HTMLButtonElement>('[aria-label="模拟登录 角色验收用户"]')
    if (!target) throw new Error('缺少模拟登录操作')
    await act(async () => target.click())
    const dialog = document.querySelector('[role="dialog"]')
    const confirm = [...(dialog?.querySelectorAll('button') ?? [])].find(button => button.textContent?.includes('切换身份'))
    if (!confirm) throw new Error('缺少切换身份操作')
    expect(start).not.toHaveBeenCalled()
    await act(async () => confirm.click())
    expect(start).toHaveBeenCalledWith('with-roles')
    expect(dialog?.querySelector('[aria-live="assertive"]')?.textContent).toBe('目标用户已停用')
    expect(confirm.disabled).toBe(false)
    expect(navigate).not.toHaveBeenCalled()

    await act(async () => confirm.click())
    expect(start).toHaveBeenCalledTimes(2)
    expect(navigate).toHaveBeenCalledWith('/')
  } finally {
    await act(async () => root.unmount())
    host.remove()
    navigate.mockRestore()
    sessionStorage.clear()
    localStorage.clear()
    delete document.documentElement.dataset.workspaceIdentityDeparting
    vi.useRealTimers()
    vi.unstubAllGlobals()
  }
})
