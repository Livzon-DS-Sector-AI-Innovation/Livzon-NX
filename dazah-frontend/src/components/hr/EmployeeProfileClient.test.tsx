/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntdApp } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  fetchEmployees: vi.fn(),
  fetchEmployeesAction: vi.fn(),
  syncFromFeishuAction: vi.fn(),
}))
vi.mock('@/actions/hr', () => actions)
const api = vi.hoisted(() => ({ fetchEmployees: vi.fn(), fetchEmployeeFilterOptions: vi.fn() }))
vi.mock('@/lib/api/hr', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api/hr')>(),
  ...api,
}))
vi.mock('next/navigation', () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({
    replace: (href: string) => window.history.replaceState(null, '', href),
  }),
}))
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canOperate: true, canDelete: false, canSync: false }),
}))
vi.mock('./EmployeeForm', () => ({ default: () => null }))
vi.mock('./EmployeeDetailDrawer', () => ({ default: () => null }))
vi.mock('./ContractAlertBanner', () => ({ default: () => null }))

import EmployeeProfileClient from './EmployeeProfileClient'
import EmployeeProfilePage from '@/app/(dashboard)/hr/profile/page'
import { HrListReadError } from '@/lib/api/hr'
import type { Employee } from '@/types/hr'

const employee = { id: 'employee-1', name: '测试员工', employee_number: 'TEST-002' } as Employee
const options = {
  departments: [
    { department: '质量部', sub_department: '分析组' },
    { department: '生产部', sub_department: '制剂组' },
  ],
  levels: ['中级'],
  educations: ['本科', '大专'],
}

describe('employee profile server rendering', () => {
  it('uses the URL filters and pagination for the initial employee query', async () => {
    actions.fetchEmployees.mockResolvedValueOnce({ data: [employee], meta: { total: 101 } })
    const page = await EmployeeProfilePage({
      searchParams: Promise.resolve({
        department: ['质量部', '生产部'], sub_department: '分析组',
        education: ' 本科 ', page: '3', page_size: '50',
      }),
    })

    expect(actions.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      first_department: '质量部', sub_department: '分析组', education: '本科', page: 3, page_size: 50,
    }))
    expect(page.props).toMatchObject({ initialEmployees: [employee], initialTotal: 101 })
  })

  it('allows the client to retry when the initial employee query fails', async () => {
    actions.fetchEmployees.mockRejectedValueOnce(new Error('Service unavailable'))
    const page = await EmployeeProfilePage({ searchParams: Promise.resolve({}) })

    expect(page.props).toMatchObject({ initialEmployees: [], initialTotal: 0 })
  })
})

describe('employee profile filters', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  function render(initialEmployees: Employee[] = []) {
    root.render(
      <AntdApp>
        <EmployeeProfileClient
          initialEmployees={initialEmployees}
          initialTotal={initialEmployees.length}
        />
      </AntdApp>,
    )
  }

  function mount(query = '', failure?: Error, initialEmployees: Employee[] = []) {
    window.history.replaceState(null, '', `/hr/profile${query}`)
    api.fetchEmployees.mockResolvedValue({ data: [], meta: { total: 0 } })
    api.fetchEmployeeFilterOptions.mockResolvedValue(options)
    if (failure) api.fetchEmployees.mockRejectedValue(failure)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    render(initialEmployees)
  }

  it('restores submitted conditions and pagination from the URL', async () => {
    await act(async () => mount('?department=质量部&sub_department=分析组&position=分析&level=中级&education=本科&page=3&page_size=50'))
    expect(api.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      first_department: '质量部', sub_department: '分析组', position: '分析', level: '中级', education: '本科', page: 3, page_size: 50,
    }))
    expect(container.querySelector<HTMLInputElement>('input[placeholder="输入职务或岗位"]')?.value).toBe('分析')
    expect(container.textContent).toContain('没有符合筛选条件的员工')
    expect(actions.fetchEmployeesAction).not.toHaveBeenCalled()
  })

  it('falls back to default pagination for invalid URL parameters', async () => {
    await act(async () => mount('?page=invalid&page_size=201'))
    expect(api.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      first_department: undefined, page: 1, page_size: 20,
    }))
    expect(container.textContent).toContain('暂无员工档案')
  })

  it('applies trimmed input and clears all filters while preserving unrelated URL state', async () => {
    await act(async () => mount('?department=质量部&education=本科&page=4&page_size=50&tab=active'))
    const input = container.querySelector<HTMLInputElement>('input[placeholder="输入姓名或工号"]')
    if (!input) throw new Error('Employee search input missing')
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '  测试  ')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(api.fetchEmployees).toHaveBeenCalledTimes(1)
    await act(async () => {
      container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      render()
    })
    expect(api.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      keyword: '测试', first_department: '质量部', education: '本科', page: 1, page_size: 50,
    }))
    const reset = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '重置')
    expect(reset).toBeDefined()
    await act(async () => {
      reset?.click()
      render()
    })
    expect(Object.fromEntries(new URLSearchParams(window.location.search))).toEqual({ page_size: '50', tab: 'active' })
    expect(api.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      keyword: undefined, first_department: undefined, education: undefined, page: 1, page_size: 50,
    }))
  })

  it('allows option failures to be retried independently of the employee list', async () => {
    api.fetchEmployeeFilterOptions.mockRejectedValueOnce(new Error('unavailable'))
    await act(async () => mount())
    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('重试加载筛选选项'))
    expect(retry).toBeDefined()
    await act(async () => retry?.click())
    expect(api.fetchEmployeeFilterOptions).toHaveBeenCalledTimes(2)
    expect(api.fetchEmployees).toHaveBeenCalledTimes(1)
    expect(container.textContent).not.toContain('重试加载筛选选项')
  })

  it('keeps the submitted filters when changing page', async () => {
    api.fetchEmployees.mockResolvedValueOnce({ data: [employee], meta: { total: 130 } })
    await act(async () => mount('?department=质量部&page=2&page_size=50'))
    const next = container.querySelector<HTMLButtonElement>('.ant-pagination-next button')
    expect(next?.disabled).toBe(false)
    await act(async () => {
      next?.click()
      render()
    })
    expect(api.fetchEmployees).toHaveBeenLastCalledWith(expect.objectContaining({
      first_department: '质量部', page: 3, page_size: 50,
    }))
  })

  it('ignores a previous request that returns after a new filter is applied', async () => {
    let resolvePrevious = () => {}
    api.fetchEmployees.mockImplementationOnce(() => new Promise(resolve => {
      resolvePrevious = () => resolve({ data: [employee], meta: { total: 1 } })
    }))
    await act(async () => mount('?keyword=旧条件'))
    await act(async () => {
      window.history.replaceState(null, '', '/hr/profile?keyword=新条件')
      render()
    })
    await act(async () => resolvePrevious())
    expect(container.textContent).toContain('没有符合筛选条件的员工')
    expect(container.textContent).not.toContain('TEST-002')
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
