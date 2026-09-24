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

describe('employee profile department deep link', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  function mount(initialDepartment?: string) {
    actions.fetchEmployeesAction.mockResolvedValue({ data: [], meta: { total: 0 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <AntdApp>
          <EmployeeProfileClient
            initialEmployees={[]}
            initialTotal={0}
            initialDepartment={initialDepartment}
          />
        </AntdApp>,
      )
    })
  }

  it('seeds the department filter from the URL parameter and fetches filtered', async () => {
    await act(async () => mount('质量部'))
    const filteredCall = actions.fetchEmployeesAction.mock.calls.find(
      (call) => call[0]?.department === '质量部',
    )
    expect(filteredCall).toBeTruthy()
  })

  it('fetches without a department filter when no parameter is given', async () => {
    await act(async () => mount())
    expect(
      actions.fetchEmployeesAction.mock.calls.every((call) => !call[0]?.department),
    ).toBe(true)
  })
})
