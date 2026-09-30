/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntdApp } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  fetchEmployeesAction: vi.fn(),
  syncFromFeishuAction: vi.fn(),
}))
vi.mock('@/actions/hr', () => actions)
const api = vi.hoisted(() => ({ fetchEmployees: vi.fn() }))
vi.mock('@/lib/api/hr', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api/hr')>(),
  fetchEmployees: api.fetchEmployees,
}))
vi.mock('@/lib/api/client/hr', () => ({
  fetchEmployeeDepartments: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/stores/hr', () => ({
  useHrStore: () => ({
    searchKeyword: '',
    setSearchKeyword: vi.fn(),
    filterStatus: '',
    setFilterStatus: vi.fn(),
  }),
}))
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canOperate: true, canDelete: false, canSync: false }),
}))
vi.mock('./EmployeeForm', () => ({ default: () => null }))
vi.mock('./EmployeeDetailDrawer', () => ({ default: () => null }))
vi.mock('./ContractAlertBanner', () => ({ default: () => null }))

import EmployeeProfileClient from './EmployeeProfileClient'
import { HrListReadError } from '@/lib/api/hr'
import type { Employee } from '@/types/hr'

const employee = { id: 'employee-1', name: '测试员工', employee_number: 'TEST-002' } as Employee

describe('employee profile department deep link', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  function mount(initialDepartment?: string, failure?: Error, initialEmployees: Employee[] = []) {
    window.history.replaceState(null, '', '/hr/profile')
    api.fetchEmployees.mockResolvedValue({ data: [], meta: { total: 0 } })
    if (failure) api.fetchEmployees.mockRejectedValue(failure)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <AntdApp>
          <EmployeeProfileClient
            initialEmployees={initialEmployees}
            initialTotal={initialEmployees.length}
            initialDepartment={initialDepartment}
          />
        </AntdApp>,
      )
    })
  }

  it('seeds the department filter from the URL parameter and fetches filtered', async () => {
    await act(async () => mount('质量部'))
    const filteredCall = api.fetchEmployees.mock.calls.find(
      (call) => call[0]?.department === '质量部',
    )
    expect(filteredCall).toBeTruthy()
    expect(actions.fetchEmployeesAction).not.toHaveBeenCalled()
  })

  it('fetches without a department filter when no parameter is given', async () => {
    await act(async () => mount())
    expect(
      api.fetchEmployees.mock.calls.every((call) => !call[0]?.department),
    ).toBe(true)
  })

  it('shows a safe message for a redacted transport exception and recovers on retry', async () => {
    await act(async () => mount(undefined, new Error('Minified React error #441')))
    expect(container.textContent).toContain('员工档案加载失败，请稍后重试')
    expect(container.textContent).not.toContain('Minified React')
    expect(container.textContent).not.toContain('No data')
    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '重试')
    expect(retry).toBeDefined()
    api.fetchEmployees.mockResolvedValue({ data: [employee], meta: { total: 1 } })
    await act(async () => retry?.click())
    expect(container.textContent).toContain('TEST-002')
    expect(container.textContent).not.toContain('员工档案加载失败')
  })

  it.each([401, 403])('shows an explicit access failure for HTTP %s', async status => {
    const message = status === 401 ? '登录已失效，请重新登录' : '没有执行此操作的权限，请联系管理员'
    await act(async () => mount(undefined, new HrListReadError(message, status), [employee]))
    expect(container.textContent).toContain(message)
    expect(container.querySelector('table')).toBeNull()
    expect(container.textContent).not.toContain('TEST-002')
  })

  it('preserves last loaded employees on a temporary service failure', async () => {
    await act(async () => mount(undefined, new HrListReadError('员工档案加载失败，请稍后重试', 500), [employee]))
    expect(container.textContent).toContain('员工档案加载失败，请稍后重试')
    expect(container.textContent).toContain('TEST-002')
  })
})
