import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createEmployee,
  fetchEmployeeById,
  fetchEmployees,
  fetchEmployeesAction,
  updateCandidateAction,
} from './hr'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('hr actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists employees with query params via action', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchEmployeesAction({ department: '102一车间', page: 2, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/employees?department=102%E4%B8%80%E8%BD%A6%E9%97%B4&page=2&page_size=50`,
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('creates an employee via action', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'e-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '张三', department_id: 'd-1' }
    await createEmployee(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/employees`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('fetches a single employee by id', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'e-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchEmployeeById('e-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/hr/employees/e-1`,
      expect.anything(),
    )
  })

  it('lists employees via fetchEmployees wrapper', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [{ id: 'e-1' }], total: 1 } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchEmployees({ page: 1, page_size: 20 })
    expect(fetchMock).toHaveBeenCalled()
  })

  it('candidate action stubs do not throw', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateCandidateAction('c-1', { note: 'x' })).rejects.toThrow('功能尚未实现')
  })
})
